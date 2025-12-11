
import logging
from pathlib import Path
from typing import List
import rasterio
from rasterio.warp import transform_bounds
from shapely.geometry import box
from geoalchemy2.shape import from_shape
from sqlmodel import Session, select
from database import engine
from models import Tile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_tile_bbox(tile_path: Path):
    with rasterio.open(tile_path) as src:
        bounds = src.bounds
        crs = src.crs or "EPSG:4326"
        minx, miny, maxx, maxy = bounds
        
        # Transform to WGS84 if needed
        if crs.to_string() != "EPSG:4326":
            minx, miny, maxx, maxy = transform_bounds(crs, "EPSG:4326", minx, miny, maxx, maxy)
            
        return box(minx, miny, maxx, maxy)

def ingest_imagery_tiles(directories: List[str]):
    """
    Scans directories for GeoTIFFs and indexes them in the DB.
    """
    logger.info(f"Scanning directories: {directories}")
    
    with Session(engine) as session:
        new_count = 0
        total_count = 0
        
        # 1. Collect all potential file paths first
        all_files = []
        for dir_path in directories:
            p = Path(dir_path)
            if not p.exists():
                logger.warning(f"Directory not found: {p}")
                continue
            all_files.extend(list(p.rglob("*.tif")))
            
        if not all_files:
            logger.info("No files found.")
            return

        logger.info(f"Found {len(all_files)} potential files. Checking database for existing records...")

        # 2. Bulk check existence
        # We'll do this by getting all known paths. 
        # For huge datasets, we might want to do this in chunks, but for <100k files this is fine.
        existing_paths = set(session.exec(select(Tile.path)).all())
        
        # 3. Filter new files
        new_files = [f for f in all_files if str(f) not in existing_paths]
        
        logger.info(f"Identified {len(new_files)} new files to ingest.")
        
        # 4. Bulk Insert
        for i, tile_path in enumerate(new_files):
            try:
                bbox = get_tile_bbox(tile_path)
                
                tile = Tile(
                    path=str(tile_path),
                    bbox=from_shape(bbox, srid=4326),
                    status="Pending"
                )
                session.add(tile)
                new_count += 1
                
                if new_count % 100 == 0:
                    session.commit()
                    logger.info(f"Ingested {new_count}/{len(new_files)} new tiles...")
                    
            except Exception as e:
                logger.error(f"Failed to ingest {tile_path}: {e}")
                
        session.commit()
        logger.info(f"✅ Ingestion complete. Scanned {total_count} files, Added {new_count} new tiles.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("dirs", nargs="+", help="Directories to scan")
    args = parser.parse_args()
    
    ingest_imagery_tiles(args.dirs)
