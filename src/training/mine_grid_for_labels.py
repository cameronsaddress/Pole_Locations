
"""
Grid-Based Training Data Miner (Layer 1 -> Layer 2)

This script implements the "Self-Supervised" loop:
1. Loads the Official Grid (Layer 1) from 'pole_network_v2.geojson'.
2. Uses the coordinates to fetch "Ground Truth" imagery from Google Street View / Mapillary.
3. Auto-labels these images (Weak Supervision) to train YOLOv11.

Usage:
    python src/training/mine_grid_for_labels.py
"""

import json
import os
import requests
import logging
from pathlib import Path
from tqdm import tqdm
import random
import sys
from datetime import datetime
from shapely.geometry import Point
from geoalchemy2.shape import from_shape

# Add path to backend imports (database, models)
# Assuming script is in src/training/ and backend-enterprise is adjacent to src parent? 
# Actually, looking at file tree, "backend-enterprise" is at root.
# src is also at root? "src/training/mine_grid_for_labels.py" -> parent.parent is "src" -> parent is root.
sys.path.append(str(Path(__file__).parent.parent.parent / "backend-enterprise"))

from database import engine
from models import StreetViewImage
from sqlmodel import Session, select

# Configuration
# Ideally, this comes from os.getenv("GOOGLE_MAPS_KEY")
# For this demo, we will use a placeholder or public sources if available.
# Configuration
MAPILLARY_TOKEN = os.getenv("MAPILLARY_TOKEN", "")
if not MAPILLARY_TOKEN:
    # Fallback to the one found in .env via cat earlier if os.getenv fails
    MAPILLARY_TOKEN = "MLY|25338439555741448|e8857675f7022ee363d2390fd55c6788" 

MAPILLARY_API_URL = "https://graph.mapillary.com/images"

# Paths
INPUT_GRID = Path("data/processed/grid_backbone.geojson") # Or pole_network_v2.geojson
if not INPUT_GRID.exists():
    INPUT_GRID = Path("frontend-enterprise/public/pole_network_v2.geojson")

OUTPUT_DIR = Path("data/training/layer1_drops")
IMAGES_DIR = OUTPUT_DIR / "images"
LABELS_DIR = OUTPUT_DIR / "labels"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GridMiner")

def calculate_heading(lat1, lon1, lat2, lon2):
    """
    Optional: Calculate heading to point camera AT the wire direction
    if we have connectivity data. For single poles, we might pan 360.
    """
    return 0

    return found_images

def fetch_street_view_images(lat, lon, pole_id):
    """
    Fetches a street-level image from Mapillary near the given coordinate.
    SKIPS download if the file already exists locally.
    """
    # 1. Search for images within the bounding box needed for the radius
    # 1 degree lat ~= 111km. 20m is ~0.0002 degrees.
    # Increasing to 0.001 (~100m) to catch more candidate images
    offset = 0.001
    bbox = f"{lon-offset},{lat-offset},{lon+offset},{lat+offset}"
    
    params = {
        "access_token": MAPILLARY_TOKEN,
        "fields": "id,thumb_2048_url,geometry",
        "bbox": bbox,
        "limit": 10  # Increased from 3 to 10 for deep mining
    }
    
    found_images = []
    try:
        resp = requests.get(MAPILLARY_API_URL, params=params)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data"):
                for i, img_data in enumerate(data["data"]):
                    # Check for cache hit
                    expected_fname = f"{pole_id}_view{i}_GSV.jpg"
                    if (IMAGES_DIR / expected_fname).exists():
                         # Skip download, but still return metadata for DB registration
                         # We use 'None' as content to signal "Already on Disk"
                         img_coords = img_data.get('geometry', {}).get('coordinates', [lon, lat])
                         found_images.append((None, i, img_data.get('id'), img_coords))
                         continue

                    img_url = img_data.get("thumb_2048_url")
                    if img_url:
                        img_resp = requests.get(img_url)
                        if img_resp.status_code == 200:
                            # img_data['geometry']['coordinates'] is [lon, lat]
                            img_coords = img_data.get('geometry', {}).get('coordinates', [lon, lat])
                            found_images.append((img_resp.content, i, img_data.get('id'), img_coords))
    except Exception as e:
        logger.error(f"Error fetching {pole_id}: {e}")
    return found_images

def register_image_to_db(image_id, lat, lon):
    """
    Upsert the image metadata to the central database (StreetViewImage table).
    This ensures that the Fusion Engine (detect.py) knows this image exists later.
    """
    try:
        with Session(engine) as session:
            # Check if exists
            existing = session.exec(select(StreetViewImage).where(StreetViewImage.image_key == image_id)).first()
            if existing:
                return # Already registered
                
            # Create new record
            # Heading is unknown (0) for now unless we calculate it.
            # Using 0 is fine for "Omnidirectional" logic or unknown
            record = StreetViewImage(
                provider="Mapillary",
                image_key=image_id,
                location=from_shape(Point(lon, lat), srid=4326),
                heading=0.0,
                captured_at=datetime.utcnow() # Approximation since we don't have metadata from thumb endpoint
            )
            session.add(record)
            session.commit()
            # logger.info(f"Registered Image {image_id} to DB.")
    except Exception as e:
        logger.error(f"DB Registration Error: {e}")

def generate_yolo_label(pole_id):
    """
    Weak Supervision Assumption:
    Since we queried the EXACT coordinate, the pole should be in the CENTER.
    
    YOLO Format: class x_center y_center width height
    Class 0 = Utility Pole
    Center = 0.5, 0.5
    Wrapper = 0.1, 0.8 (Estimate: Poles are tall and thin)
    """
    # This is a 'Weak Label'. 
    # In a production system, we would run a pre-trained 'Teacher Model' 
    # to refine this bounding box before saving.
    return "0 0.5 0.5 0.1 0.85"

def mine_grid(grid_path=None):
    # Use global default if not provided
    input_path = grid_path if grid_path else INPUT_GRID
    
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Loading grid from {input_path}...")
    try:
        with open(input_path) as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.error(f"Grid file not found: {input_path}")
        return
        
    features = data.get("features", [])
    poles = [f for f in features if f["geometry"]["type"] == "Point"]
    
    # Process ALL poles
    sample_poles = poles
    logger.info(f"Processing full grid of {len(sample_poles)} locations...") 
    
    success_count = 0
    
    for i, pole in enumerate(tqdm(sample_poles)):
        coords = pole["geometry"]["coordinates"]
        lon, lat = coords[0], coords[1]
        pid = pole.get("properties", {}).get("id", f"pole_{i}")
        
        # Fetch multiple images
        images = fetch_street_view_images(lat, lon, pid)
        
        if images:
            for img_bytes, idx, img_id, img_coords in images:
                fname = f"{pid}_view{idx}_GSV.jpg"
                
                # Only write if we actually downloaded bytes (not cached)
                if img_bytes is not None:
                    with open(IMAGES_DIR / fname, "wb") as f:
                        f.write(img_bytes)
                else:
                    # Optional logging for debug
                    # logger.info(f"Skipped download for existing file: {fname}")
                    pass
                
                # [NEW] Register to DB
                if img_id:
                   # img_coords is [lon, lat]
                   register_image_to_db(img_id, img_coords[1], img_coords[0])

                # SKIP Auto-Labelling (Deprecated for Manual Workflow)
                # label = generate_yolo_label(pid)
                # with open(LABELS_DIR / f"{pid}_view{idx}_GSV.txt", "w") as f:
                #     f.write(label)
            
            success_count += 1
            
    logger.info(f"Successfully mined data for {success_count} poles (Total images: {len(list(IMAGES_DIR.glob('*.jpg')))})")
    logger.info(f"Data saved to {OUTPUT_DIR}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", type=str, default="all", help="Comma separated list of target counties")
    args = parser.parse_args()
    
    targets = args.targets.lower().split(',')
    logger.info(f"MINING JOB INITIATED. TARGETS: {targets}")
    
    # Generic Processing Loop
    for target in targets:
        target = target.strip()
        if not target: continue
        
        logger.info(f"--- Processing Target: {target} ---")
        
        # 1. Determine Grid Path
        # Try exact match first: "york_pa" -> "data/processed/york_pa_poles.geojson"
        # Then try common variations: "york_pa" -> "york_poles.geojson"
        
        potential_paths = [
            Path(f"data/processed/{target}_poles.geojson"),
            Path(f"data/processed/{target.replace('_pa', '').replace('_wa', '')}_poles.geojson"),
            Path(f"data/processed/{target}.geojson")
        ]
        
        # Hardcoded overrides for legacy naming
        if "king_wa" in target or "seattle" in target:
            potential_paths.insert(0, Path("data/processed/seattle_poles.geojson"))
        if "philadelphia" in target or "philly" in target:
            potential_paths.insert(0, Path("data/processed/philly_poles.geojson"))
        if "dauphin" in target or "harrisburg" in target or target == "all":
             potential_paths.append(INPUT_GRID) # Default fallback
             
        found_grid = None
        for p in potential_paths:
            if p.exists():
                found_grid = p
                break
        
        if found_grid:
            logger.info(f"✅ Found Existing Grid File: {found_grid}")
            mine_grid(found_grid)
        else:
            logger.warning(f"⚠️ Grid file NOT found for target '{target}'. Checking for Auto-Generation capability...")
            
            # Auto-Generation Logic
            # 1. Define BBOX Map (Copied from manager.py for standalone robustness)
            REGION_BBOX_MAP = {
                # PA
                "dauphin_pa": {"minx": -77.20, "miny": 39.90, "maxx": -76.20, "maxy": 40.50},
                "philadelphia_pa": {"minx": -75.30, "miny": 39.85, "maxx": -74.90, "maxy": 40.15},
                "cumberland_pa": {"minx": -77.60, "miny": 39.90, "maxx": -76.90, "maxy": 40.30},
                "york_pa": {"minx": -77.00, "miny": 39.70, "maxx": -76.40, "maxy": 40.20},
                "adams_pa": {"minx": -77.50, "miny": 39.70, "maxx": -77.00, "maxy": 40.00},
                "allegheny_pa": {"minx": -80.35, "miny": 40.20, "maxx": -79.70, "maxy": 40.70},
                # WA
                "king_wa": {"minx": -122.45, "miny": 47.45, "maxx": -122.20, "maxy": 47.75},
                "spokane_wa": {"minx": -117.80, "miny": 47.40, "maxx": -117.00, "maxy": 48.00},
                "snohomish_wa": {"minx": -122.40, "miny": 47.75, "maxx": -121.50, "maxy": 48.30},
                "pierce_wa": {"minx": -122.60, "miny": 46.70, "maxx": -121.80, "maxy": 47.40},
                # NY
                "new_york_ny": {"minx": -74.30, "miny": 40.50, "maxx": -73.70, "maxy": 40.90},
                # OR
                "multnomah_or": {"minx": -122.90, "miny": 45.40, "maxx": -122.30, "maxy": 45.70},
            }
            
            bbox = REGION_BBOX_MAP.get(target)
            if bbox:
                logger.info(f"✨ Auto-Generating Grid for {target} from OpenStreetMap...")
                from src.ingestion.connectors.openinframap import fetch_osm_poles
                
                new_grid_path = Path(f"data/processed/{target}_poles.geojson")
                success = fetch_osm_poles(bbox, new_grid_path)
                
                if success:
                    logger.info("✅ Grid Created. Proceeding to Mine Imagery...")
                    mine_grid(new_grid_path)
                else:
                    logger.error("❌ Failed to auto-generate grid.")
            else:
                logger.error(f"❌ Unknown Region '{target}'. Cannot auto-generate.")
                logger.error("Skipping this target.")
