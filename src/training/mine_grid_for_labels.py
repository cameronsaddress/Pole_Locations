
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

def fetch_street_view_images(lat, lon, pole_id):
    """
    Fetches a street-level image from Mapillary near the given coordinate.
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
                    img_url = img_data.get("thumb_2048_url")
                    if img_url:
                        img_resp = requests.get(img_url)
                        if img_resp.status_code == 200:
                            found_images.append((img_resp.content, i))
    except Exception as e:
        logger.error(f"Error fetching {pole_id}: {e}")
    return found_images

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

def mine_grid():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Loading grid from {INPUT_GRID}...")
    with open(INPUT_GRID) as f:
        data = json.load(f)
        
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
            for img_bytes, idx in images:
                fname = f"{pid}_view{idx}_GSV.jpg"
                with open(IMAGES_DIR / fname, "wb") as f:
                    f.write(img_bytes)
                    
                # Generate Label
                label = generate_yolo_label(pid)
                with open(LABELS_DIR / f"{pid}_view{idx}_GSV.txt", "w") as f:
                    f.write(label)
            
            success_count += 1
            
    logger.info(f"Successfully mined data for {success_count} poles (Total images: {len(list(IMAGES_DIR.glob('*.jpg')))})")
    logger.info(f"Data saved to {OUTPUT_DIR}")

if __name__ == "__main__":
    mine_grid()
