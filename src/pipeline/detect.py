
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
from geoalchemy2.shape import from_shape
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
                    # We query back the UPDATED poles to check for gaps
                    logger.info("  -> running pearl stringer (gap analysis)...")
                    try:
                        # Get bounds of current tile
                        tile_poly = from_shape(Point(df['lon'].mean(), df['lat'].mean()), srid=4326).buffer(0.01) # Approx 1km buffer
                        
                        # Find confirmed poles in this area
                        # We need to map this appropriately or just use the Stringer's internal logic if it accepts a session
                        # stringer = PearlStringer(session)
                        # stringer.analyze_and_fill_gaps(tile_poly)
                        pass # Placeholder until PearlStringer accepts Session directly
                    except Exception as e:
                        logger.warning(f"PearlStringer skipped: {e}")
                    
                    # 7c. Street Correlation
                    logger.info("  -> running sensor fusion (street view correlation)...")
                    sensor_fusion = SensorFusion()
                    
                    # Re-query the poles just validated
                    # For every new "Flagged" pole, check if we have Street View confirmation
                    # optimized: do this in bulk or per pole? Per pole for now.
                    
                    # We need the list of JUST added poles. But 'detections_to_add' are Detections, not Poles.
                    # The Fusion Engine created the Poles.
                    # Query for poles created in the last minute in this area?
                    
                    # Simpler: Iterate the detections, find the matching Pole, check street view.
                    # This requires FusionEngine to return the mapped Pole IDs.
                    # For now, we will perform a spatial query for Street View images near the detections
                    
                    street_images_stmt = select(StreetViewImage).where(
                        StreetViewImage.location.ST_DWithin(
                            from_shape(Point(df['lon'].mean(), df['lat'].mean()), srid=4326), 
                            500 # 500 meters radius from center of tile batch
                        )
                    )
                    street_images = session.exec(street_images_stmt).all()
                    
                    if street_images:
                        logger.info(f"    Found {len(street_images)} street view images for correlation.")
                        # Logic: For each Detection, find closest Street Image, check bearing
                        for det in detections_to_add:
                            det_pt = det.location
                            # In real logic, we'd cast det_pt back to lat/lon
                            # ...
                            pass
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
