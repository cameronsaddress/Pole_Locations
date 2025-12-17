
import logging
import random
import json
from pathlib import Path
from tqdm import tqdm
import sys

# Add path to root for imports (project root is two levels up from src/training?)
# Actually, the file is in src/training/
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.training.mine_grid_for_labels import fetch_street_view_images, register_image_to_db, IMAGES_DIR as STREET_IMAGES_DIR
from src.ingestion.connectors.openinframap import fetch_osm_poles
from src.training.mine_satellite_for_labels import mine_satellite

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PopulateFeed")

# Configuration
PA_COUNTIES = [
    "dauphin_pa", "philadelphia_pa", "cumberland_pa", 
    "york_pa", "adams_pa", "allegheny_pa"
]

REGION_BBOX_MAP = {
    "dauphin_pa": {"minx": -77.20, "miny": 39.90, "maxx": -76.20, "maxy": 40.50},
    "philadelphia_pa": {"minx": -75.30, "miny": 39.85, "maxx": -74.90, "maxy": 40.15},
    "cumberland_pa": {"minx": -77.60, "miny": 39.90, "maxx": -76.90, "maxy": 40.30},
    "york_pa": {"minx": -77.00, "miny": 39.70, "maxx": -76.40, "maxy": 40.20},
    "adams_pa": {"minx": -77.50, "miny": 39.70, "maxx": -77.00, "maxy": 40.00},
    "allegheny_pa": {"minx": -80.35, "miny": 40.20, "maxx": -79.70, "maxy": 40.70},
}

DATA_DIR = Path("data/processed")

def ensure_grid(target):
    grid_path = DATA_DIR / f"{target}_poles.geojson"
    if grid_path.exists():
        return grid_path
    
    logger.info(f"Grid missing for {target}. Auto-generating...")
    bbox = REGION_BBOX_MAP.get(target)
    if not bbox:
        logger.error(f"No BBOX for {target}")
        return None
        
    if fetch_osm_poles(bbox, grid_path):
        return grid_path
    return None

def populate_feed(images_per_county=50, dataset_type="street"):
    if dataset_type == "satellite":
        logger.info("Starting Satellite Mining Job...")
        mine_satellite()
        return

    # Street View Logic
    STREET_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    total_added = 0
    
    for target in PA_COUNTIES:
        logger.info(f"--- Scanning {target} ---")
        grid_path = ensure_grid(target)
        if not grid_path: continue
        
        try:
            with open(grid_path) as f:
                data = json.load(f)
            features = [f for f in data.get("features", []) if f["geometry"]["type"] == "Point"]
            
            if not features:
                logger.warning(f"No poles in {target} grid.")
                continue
                
            # Random Sample
            sample_size = min(len(features), images_per_county * 3) # Over-sample to account for missing GSV
            selection = random.sample(features, sample_size)
            
            county_added = 0
            for pole in tqdm(selection, desc=f"Mining {target}"):
                if county_added >= images_per_county:
                    break
                    
                coords = pole["geometry"]["coordinates"]
                pid = pole.get("properties", {}).get("id", "unknown")
                
                # Check if we already have images for this pole to avoid duplication in feed
                # (Simple check: file existence)
                # But fetch_street_view_images does this check!
                
                images = fetch_street_view_images(coords[1], coords[0], pid)
                
                if images:
                    has_new = False
                    for img_bytes, idx, img_id, img_coords in images:
                        fname = f"{pid}_view{idx}_GSV.jpg"
                        if img_bytes is not None:
                            with open(STREET_IMAGES_DIR / fname, "wb") as f:
                                f.write(img_bytes)
                            has_new = True
                            
                        # Register (idempotent)
                        if img_id:
                            register_image_to_db(img_id, img_coords[1], img_coords[0])
                            
                    if has_new:
                        county_added += 1
                        total_added += 1
                        
        except Exception as e:
            logger.error(f"Error processing {target}: {e}")
            
    logger.info(f"Job Complete. Added {total_added} new images to Manual Feed.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=50, help="Images per county")
    parser.add_argument("--dataset", type=str, default="street", choices=["street", "satellite"], help="Dataset type to populate")
    args = parser.parse_args()
    
    populate_feed(args.count, args.dataset)
