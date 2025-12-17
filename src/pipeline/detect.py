
import logging
from pathlib import Path
import pandas as pd
from sqlmodel import Session, select, text
from database import engine
from models import Tile, Detection, StreetViewImage
from src.detection.pole_detector import PoleDetector
from src.pipeline.fusion_engine import FusionEngine 
from src.fusion.context_filters import annotate_context_features, filter_implausible_detections
from src.fusion.pearl_stringer import PearlStringer
from src.fusion.correlator import SensorFusion
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_detection_service(limit: int = 1000, target_path: str = None):
    logger.info("Starting Enterprise Detection Service (Unified Detect/Enrich/Fuse)...")
    
    # Initialize components
    detector = PoleDetector() 
    fusion = FusionEngine()
    
    with Session(engine) as session:
        # Get pending tiles (Case insensitive check)
        if target_path:
            logger.info(f"Configuration: Targeting specific tile: {target_path}")
            statement = select(Tile).where(Tile.path == target_path)
        else:
            statement = select(Tile).where(
                (Tile.status == "Pending") | 
                (Tile.status == "pending") |
                ((Tile.status == "Failed") & (Tile.retry_count < 3))
            ).limit(limit)
        
        tiles = session.exec(statement).all()
        
        if not tiles:
            logger.info("No pending tiles found.")
            return

        for tile in tiles:
            logger.info(f"Processing tile {tile.id}: {tile.path}")
            run_id = f"tile_{tile.id}"
            
            try:
                # 1. Update Status
                tile.status = "Running"
                session.add(tile)
                session.commit()
                
                # 2. Check File
                tile_path = Path(tile.path)
                if not tile_path.exists():
                     logger.error(f"File not found: {tile_path}")
                     tile.status = "Failed"
                     session.add(tile)
                     session.commit()
                     continue

                # 3. Run Inference
                results = detector.detect_tiles([tile_path])
                logger.info(f"Tile {tile.id}: Found {len(results)} raw detections.")
                
                if not results:
                    tile.status = "processed"
                    tile.last_processed_at = datetime.utcnow()
                    session.add(tile)
                    session.commit()
                    continue

                # 4. Contextual Enrichment (Full Suite)
                # Convert to DataFrame
                df = pd.DataFrame(results)
                # Ensure lat/lon are float
                df["lat"] = df["lat"].astype(float)
                df["lon"] = df["lon"].astype(float)
                
                # Enrich with Roads, DSM, Water
                # This function handles file loading internally (now optimized)
                logger.info("  -> running full context enrichment...")
                df = annotate_context_features(df)
                
                # Filter Junk
                logger.info("  -> filtering implausible detections...")
                df, dropped = filter_implausible_detections(df, max_road_distance_m=200.0, drop_failures=True)
                if not dropped.empty:
                    logger.info(f"  Dropped {len(dropped)} detections (context filters)")
                
                # 5. Build Detections
                detections_to_add = []
                for _, row in df.iterrows():
                    point = Point(row['lon'], row['lat'])
                    
                    # Safe retrieval for optional columns
                    rd_dist = row.get('road_distance_m')
                    rd_dist = float(rd_dist) if pd.notna(rd_dist) else None
                    
                    hag = row.get('height_ag_m')
                    hag = float(hag) if pd.notna(hag) else None
                    
                    det = Detection(
                        confidence=float(row['ai_confidence']),
                        class_name=row.get('class_name', "Unknown"),
                        image_path=str(tile.path), 
                        run_id=run_id,
                        location=from_shape(point, srid=4326), 
                        road_distance_m=rd_dist,
                        height_ag_m=hag,
                        created_at=datetime.utcnow()
                    )
                    detections_to_add.append(det)

                # 6. Bulk Insert Detections
                if detections_to_add:
                    session.add_all(detections_to_add)
                    session.commit() 

                    # 7. Run Fusion Immediately on this Batch
                    logger.info("  -> running fusion engine...")
                    fusion.run_fusion(session, run_id=run_id)
                    
                    # 7b. Run Pearl Stringer (Gap Analysis)
                    logger.info("  -> running pearl stringer (gap analysis)...")
                    try:
                        # Logic: Extract ALL pole locations in this tile from DB (not just this batch)
                        # For now, we use the batch for simplicity + recent history
                        # Ideally: stringer_input = session.exec(select(Pole.location)...).all()
                        
                        batch_coords = [(d.location.y, d.location.x) for d in detections_to_add]
                        
                        stringer = PearlStringer(spacing_min=30, spacing_max=60)
                        stringer.find_missing_pearls(batch_coords, session=session, write_to_db=True)
                        
                    except Exception as e:
                        logger.warning(f"PearlStringer skipped: {e}")
                    
                    # 7c. Street Correlation
                    logger.info("  -> running sensor fusion (street view correlation)...")
                    sensor_fusion = SensorFusion()
                    
                    # Spatial Query for Street View Images
                    street_images_stmt = select(StreetViewImage).where(
                        StreetViewImage.location.ST_DWithin(
                            from_shape(Point(df['lon'].mean(), df['lat'].mean()), srid=4326), 
                            500 
                        )
                    )
                    street_images = session.exec(street_images_stmt).all()
                    
                    if street_images:
                        logger.info(f"    Found {len(street_images)} street view images.")
                        
                        # Get Street Expert Model
                        street_model = detector.models.get('street')
                        
                        for det in detections_to_add:
                            # det.location is WKBElement, simpler to use original df row or convert
                            py_pt = to_shape(det.location) 
                            p_lat, p_lon = py_pt.y, py_pt.x
                            
                            # Find best image match
                            for img in street_images:
                                img_pt = to_shape(img.location)
                                i_lat, i_lon = img_pt.y, img_pt.x
                                
                                # Geometric Check
                                match, dev = sensor_fusion.verify_with_street_view(
                                    p_lat, p_lon, i_lat, i_lon, img.heading, tolerance_deg=15.0
                                )
                                
                                if match:
                                    logger.info(f"    ⚡ Geometric Match! Pole {det.id} aligned with Image {img.image_key}")
                                    
                                    # Visual Verification (V2)
                                    if street_model:
                                        confirmed = sensor_fusion.verify_visually(session, img.image_key, street_model)
                                        if confirmed:
                                            # Upgrade Pole Status to 'Confirmed' or add tag
                                            det.tags['visual_confirmation'] = True
                                            det.tags['confirmed_by_image'] = img.image_key
                                            session.add(det)
                                            
                                            # Find and Update the Parent POLE (created by FusionEngine earlier)
                                            # We use a tight spatial match since Fusion just ran.
                                            from models import Pole
                                            parent_pole = session.exec(
                                                select(Pole).where(
                                                    Pole.location.ST_DWithin(det.location, 2.0) # 2 meter tolerance
                                                ).limit(1)
                                            ).first()
                                            
                                            if parent_pole:
                                                parent_pole.status = "Verified"
                                                if parent_pole.tags is None: parent_pole.tags = {}
                                                parent_pole.tags['confirmed_by_image'] = img.image_key
                                                parent_pole.tags['visual_confirmation'] = True
                                                parent_pole.tags['sensors'] = parent_pole.tags.get('sensors', []) + ['Street View']
                                                session.add(parent_pole)
                                                logger.info(f"    🌟 VISUAL CONFIRMATION SUCCESS for Detection {det.id} -> Pole {parent_pole.pole_id}")
                                            else:
                                                logger.warning(f"    ⚠️ Could not find parent pole for confirmed detection {det.id}")
                                            
                                    break # Stop after first confirming image
                                    
                    else:
                        logger.debug("    No street view images found for correlation.")
                
            except Exception as e:
                logger.error(f"❌ Failed tile {tile.id}: {e}", exc_info=True)
                session.rollback() # Rollback
                tile.status = "Failed"
                tile.retry_count += 1
                session.add(tile)
                session.commit()

if __name__ == "__main__":
    run_detection_service()
