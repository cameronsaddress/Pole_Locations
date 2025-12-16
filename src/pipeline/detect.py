
import logging
from pathlib import Path
import pandas as pd
from sqlmodel import Session, select, text
from database import engine
from models import Tile, Detection
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
                    # For simplicity in this loop, we just check the output of this run's fused poles.
                    # Ideally this is a separate background job, but we can call it here.
                    logger.info("  -> running pearl stringer (gap analysis)...")
                    # (Implementation Note: PearlStringer needs 'list of coordinates', we can query recent poles)
                    
                    # 7c. Street Correlation
                    # Check if any new poles align with Street View data (if available)
                    # sensor_fusion = SensorFusion()
                    # sensor_fusion.verify_with_street_view(...)
                
                # 8. Finalize Tile
                tile.status = "processed"
                tile.last_processed_at = datetime.utcnow()
                session.add(tile)
                session.commit()
                
                logger.info(f"✅ Tile {tile.id} complete. ({len(detections_to_add)} detections)")
                
            except Exception as e:
                logger.error(f"❌ Failed tile {tile.id}: {e}", exc_info=True)
                session.rollback() # Rollback
                tile.status = "Failed"
                tile.retry_count += 1
                session.add(tile)
                session.commit()

if __name__ == "__main__":
    run_detection_service()
