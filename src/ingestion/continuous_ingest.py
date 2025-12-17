
import time
import os
import shutil
import logging
from pathlib import Path
from datetime import datetime
import sys

# [NEW] GIS & DB Imports
import rasterio
from rasterio.warp import transform_bounds
from shapely.geometry import box
from geoalchemy2.shape import from_shape
from sqlmodel import Session, select

# [NEW] Path Setup for Backend Imports
sys.path.append(str(Path(__file__).parent.parent.parent / "backend-enterprise"))
from database import engine
from models import Tile

# Config
INCOMING_DIR = Path("data/incoming")
PROCESSING_DIR = Path("data/processing")
ARCHIVE_DIR = Path("data/archive")
REJECTED_DIR = Path("data/rejected")
POLL_INTERVAL = 5  # Seconds

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ingestion.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("IngestService")

def setup_dirs():
    for d in [INCOMING_DIR, PROCESSING_DIR, ARCHIVE_DIR, REJECTED_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def get_tile_bbox(tile_path: Path):
    """
    Extracts the bounding box from a GeoTIFF.
    """
    try:
        with rasterio.open(tile_path) as src:
            bounds = src.bounds
            crs = src.crs or "EPSG:4326"
            minx, miny, maxx, maxy = bounds
            
            # Transform to WGS84 if needed
            if crs.to_string() != "EPSG:4326":
                minx, miny, maxx, maxy = transform_bounds(crs, "EPSG:4326", minx, miny, maxx, maxy)
                
            return box(minx, miny, maxx, maxy)
    except Exception as e:
        logger.error(f"Error reading GeoTIFF {tile_path}: {e}")
        return None

def validate_image(file_path):
    """
    Check extension and basic header validity.
    """
    valid_exts = {'.jpg', '.jpeg', '.png', '.tif', '.tiff'}
    if file_path.suffix.lower() not in valid_exts:
        return False, "Invalid Extension"
    
    if file_path.stat().st_size < 1024:
        return False, "File too small (Corrupt?)"
        
    return True, "Valid"

def process_file(file_path):
    logger.info(f"Detected new file: {file_path.name}")
    
    # 1. Move to Processing (Atomic-ish)
    processing_path = PROCESSING_DIR / file_path.name
    try:
        shutil.move(str(file_path), str(processing_path))
    except Exception as e:
        logger.error(f"Failed to move {file_path.name} to processing: {e}")
        return

    # 2. Validation
    is_valid, reason = validate_image(processing_path)
    if not is_valid:
        logger.warning(f"Rejected {file_path.name}: {reason}")
        shutil.move(str(processing_path), str(REJECTED_DIR / file_path.name))
        return

    # 3. DB Registration (The "Real" Trigger)
    logger.info(f"🌍 Registering {file_path.name} to Database...")
    
    try:
        bbox = get_tile_bbox(processing_path)
        if not bbox:
            raise ValueError("Could not determine BBOX (is it a valid GeoTIFF?)")

        with Session(engine) as session:
            # Check if exists (by path suffix to avoid full path issues)
            # Actually, let's use the filename as unique identifier for this ingest
            # or just insert. The `path` column in Tile is unique.
            
            # We need to decide where the file *lives* permanently.
            # It goes to ARCHIVE_DIR.
            timestamp = datetime.now().strftime("%Y%m%d")
            archive_day_dir = ARCHIVE_DIR / timestamp
            archive_day_dir.mkdir(exist_ok=True)
            final_path = archive_day_dir / file_path.name
            
            # Check DB
            existing = session.exec(select(Tile).where(Tile.path == str(final_path))).first()
            if existing:
                logger.warning(f"Tile already exists in DB: {final_path}")
                # We overwrite the file but maybe don't need to touch DB?
                # Or set it to pending again?
                existing.status = "Pending"
                session.add(existing)
            else:
                # Create New
                tile = Tile(
                    path=str(final_path),
                    bbox=from_shape(bbox, srid=4326),
                    status="Pending"  # <--- Triggers Runner/Detect
                )
                session.add(tile)
            
            session.commit()
            
            # 4. Move to Final Archive
            shutil.move(str(processing_path), str(final_path))
            logger.info(f"✅ Successfully Ingested: {final_path}")

    except Exception as e:
        logger.error(f"Ingestion Failed for {file_path.name}: {e}")
        # Move to Rejected
        try:
             shutil.move(str(processing_path), str(REJECTED_DIR / file_path.name))
        except: pass

def run_ingest_loop():
    logger.info("Starting Continuous Ingestion Service (Real DB Mode)...")
    logger.info(f"Watching {INCOMING_DIR.absolute()}")
    
    setup_dirs()
    
    while True:
        try:
            # List files
            files = list(INCOMING_DIR.glob("*"))
            if not files:
                time.sleep(POLL_INTERVAL)
                continue
                
            for f in files:
                if f.is_file():
                    process_file(f)
                    
        except KeyboardInterrupt:
            logger.info("Stopping Ingestion Service.")
            break
        except Exception as e:
            logger.error(f"Critical Loop Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_ingest_loop()
