
import logging
import sys
from pathlib import Path
from sqlalchemy import text # fixed import
from sqlmodel import Session, select, delete

# Add src to path
PROJECT_ROOT = Path("/workspace")
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "backend-enterprise"))

from src.ingestion.connectors.openinframap import fetch_grid_backbone
from database import engine
from models import Tile, Detection, Pole

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SystemRestore")

def restore_grid_data():
    logger.info("🔄 Restoring Grid Backbone Data (downloading real data)...")
    # Use Harrisburg/Tri-County BBox to ensure success and speed
    # This prevents timeouts on the massive East Coast query
    harrisburg_bbox = {
        "minx": -77.5,
        "miny": 39.8,
        "maxx": -76.0, 
        "maxy": 40.8
    }
    success = fetch_grid_backbone(bbox=harrisburg_bbox)
    if success:
        logger.info("✅ Grid Backbone restored successfully.")
    else:
        logger.error("❌ Failed to restore Grid Backbone.")

def purge_test_data():
    logger.info("🧹 Purging Test Data from Database...")
    with Session(engine) as session:
        # 1. Find Test Tile
        test_path_pattern = "%test_tile_01%"
        
        # Get Tile IDs
        statement = select(Tile).where(Tile.path.like(test_path_pattern))
        tiles = session.exec(statement).all()
        
        if not tiles:
            logger.info("No test tiles found.")
        else:
            logger.info(f"Found {len(tiles)} test tiles. Deleting...")
            
            for tile in tiles:
                # Delete Detections linked to this tile (if not cascaded)
                # Detections link via image_path usually
                # But safer to just delete by path match
                pass
                
        # Bulk Delete Detections
        # Note: Detection.image_path is the link
        del_det = delete(Detection).where(Detection.image_path.like(test_path_pattern))
        result = session.exec(del_det)
        logger.info(f"Deleted {result.rowcount} test detections.")
        
        # Bulk Delete Tiles
        del_tile = delete(Tile).where(Tile.path.like(test_path_pattern))
        result = session.exec(del_tile)
        logger.info(f"Deleted {result.rowcount} test tiles.")
        
        # Delete Poles created by test
        # Identify by logic? Or maybe just manual cleanup of the specific test coordinate?
        # The test pole was at 40.2732, -76.8867
        # Let's delete poles within 1 meter of that point
        
        # Using PostGIS to find the test pole
        # ST_DWithin(location, ST_MakePoint(-76.8867, 40.2732), 0.0001)
        
        query_pole = text("""
            DELETE FROM poles 
            WHERE ST_DWithin(
                location::geometry, 
                ST_SetSRID(ST_MakePoint(-76.8867, 40.2732), 4326), 
                0.0001
            )
        """)
        result = session.exec(query_pole)
        logger.info(f"Deleted {result.rowcount} test poles near test origin.")
        
        session.commit()
        logger.info("✅ Database purged of test artifacts.")

if __name__ == "__main__":
    restore_grid_data()
    purge_test_data()
