
import logging
from pathlib import Path
from sqlmodel import Session, select
from database import engine
from models import Tile, Detection
# Import from src if running from root
from src.detection.pole_detector import PoleDetector
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_detection_service(limit: int = 10):
    logger.info("Starting detection service...")
    
    # Initialize detector (loads YOLO + CLIP)
    detector = PoleDetector() 
    
    with Session(engine) as session:
        # Get pending tiles
        tiles = session.exec(select(Tile).where(Tile.status == "Pending").limit(limit)).all()
        
        if not tiles:
            logger.info("No pending tiles found.")
            return

        for tile in tiles:
            logger.info(f"Processing tile {tile.id}: {tile.path}")
            try:
                # Update status to Running
                tile.status = "Running"
                session.add(tile)
                session.commit()
                
                # Run Inference
                # detect_tiles expects a list of Path objects
                tile_path = Path(tile.path)
                if not tile_path.exists():
                     logger.error(f"File not found: {tile_path}")
                     tile.status = "Failed"
                     session.add(tile)
                     session.commit()
                     continue

                # Run actual detection
                results = detector.detect_tiles([tile_path])
                
                logger.info(f"Found {len(results)} detections.")
                
                for r in results:
                    # Convert to DB Model
                    # Ensure lat/lon are floats
                    lat = float(r['lat'])
                    lon = float(r['lon'])
                    point = Point(lon, lat)
                    
                    det = Detection(
                        confidence=float(r['ai_confidence']),
                        class_name=r.get('class_name', "Unknown"),
                        image_path=str(tile.path), 
                        run_id=f"tile_{tile.id}",
                        location=from_shape(point, srid=4326),
                        created_at=datetime.utcnow()
                    )
                    session.add(det)
                
                tile.status = "Processed"
                tile.last_processed_at = datetime.utcnow()
                session.add(tile)
                session.commit()
                logger.info(f"✅ Tile {tile.id} processed successfully.")
                
            except Exception as e:
                logger.error(f"❌ Failed tile {tile.id}: {e}", exc_info=True)
                tile.status = "Failed"
                session.add(tile)
                session.commit()

if __name__ == "__main__":
    run_detection_service()
