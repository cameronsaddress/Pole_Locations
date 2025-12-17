
"""
Layer 1 Satellite Miner (Parallel Model)

This script mines Satellite/Aerial imagery for the "Satellite YOLOv11" model.
It uses the same Layer 1 grid (pole_network_v2.geojson) but fetches
top-down imagery instead of street-level.

Use Case:
    - Multi-state scalability (where street view is unavailable).
    - Finding new poles not on the map (using the trained model).

Usage:
    python src/training/mine_satellite_for_labels.py
"""

import json
import os
import requests
import logging
from pathlib import Path
from tqdm import tqdm
import math

# Configuration
# USGS National Map (Free, High Res Orthoimagery)
# or generic tile server (OSM/ESRI) for training. 
# For elite resolution, we often need a paid key (Google/Bing) or careful use of USGS.
# Using ESRI World Imagery (High Res, Free for non-com research, checking license for Ent)
# or potentially USGS via MapProxy.
# For simplicity and speed in this prototype: ESRI World Imagery via REST or standard Tile XYZ.

TILE_SERVER_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ZOOM_LEVEL = 19 # Reverting to 19 (high res) to ensure coverage. 20 was too deep for ESRI in this area.

# Paths
# Paths
INPUT_GRID = Path("data/processed/grid_backbone.geojson")
if not INPUT_GRID.exists():
    INPUT_GRID = Path("frontend-enterprise/public/pole_network_v2.geojson")

OUTPUT_DIR = Path("/data/training/satellite_drops")
IMAGES_DIR = OUTPUT_DIR / "images"
LABELS_DIR = OUTPUT_DIR / "labels"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SatMiner")

def lat_lon_to_tile(lat, lon, zoom):
    """
    Standard Web Mercator projection to find tile coordinates.
    """
    n = 2.0 ** zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return xtile, ytile

def lat_lon_to_pixel_in_tile(lat, lon, zoom):
    """
    Returns pixel offset (x, y) within the 256x256 tile.
    Useful if we were cropping perfectly, but for now we just want the tile containing the pole.
    Ideally, we center crop 640x640 from a stitched neighborhood of tiles.
    """
    n = 2.0 ** zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    
    # Calculate global pixel coordinates
    # Total pixels = 256 * n
    # Current x pixel = ((lon + 180.0) / 360.0 * n) * 256
    
    x_float = (lon + 180.0) / 360.0 * n * 256.0
    y_float = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n * 256.0
    
    # Local pixel in tile is (x_float % 256, y_float % 256)
    pixel_x = x_float % 256.0
    pixel_y = y_float % 256.0
    
    return pixel_x, pixel_y

def fetch_satellite_tile(lat, lon, pole_id):
    """
    Fetches the satellite tile containing the pole.
    In a real prod system, we would stitch 4 adjacent tiles and crop 640x640 center.
    Here we grab the single tile for the speed of the prototype.
    """
    x, y = lat_lon_to_tile(lat, lon, ZOOM_LEVEL)
    z = ZOOM_LEVEL
    
    url = TILE_SERVER_URL.format(z=z, x=x, y=y)
    
    try:
        # User-Agent strictly required by some tile servers
        headers = {"User-Agent": "PoleDetectorBot/1.0"}
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            return True, resp.content
        else:
            logger.warning(f"Failed tile fetch {z}/{x}/{y}: {resp.status_code}")
            return False, None
    except Exception as e:
        logger.error(f"Error fetching sat {pole_id}: {e}")
        return False, None

def generate_sat_yolo_label(pixel_x, pixel_y):
    """
    Generate label based on exact pixel location.
    YOLO expects normalized coordinates (0.0 to 1.0)
    """
    norm_x = pixel_x / 256.0
    norm_y = pixel_y / 256.0
    
    # 0.02 is fairly small (approx 5 pixels width), good for aerial dots
    return f"0 {norm_x:.6f} {norm_y:.6f} 0.02 0.02" 

def mine_satellite():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Loading grid for Satellite Mining...")
    with open(INPUT_GRID) as f:
        data = json.load(f)
        
    features = data.get("features", [])
    poles = [f for f in features if f["geometry"]["type"] == "Point"]
    
    # Filter out transmission towers if the data supports it
    # We only want "distribution poles"
    dist_poles = []
    for p in poles:
        props = p.get("properties", {})
        # Check power tag if available
        p_type = props.get("power", "pole")
        # Explicitly skip towers
        if p_type != "tower":
            dist_poles.append(p)
            
    logger.info(f"Filtered {len(poles) - len(dist_poles)} towers. Proceeding with {len(dist_poles)} distribution poles.")
    
    # Sample a subset to start building the dataset alongside the street view one
    sample_poles = dist_poles[:2000] # Increased limit for distribution poles 
    logger.info(f"Mining Satellite Imagery for {len(sample_poles)} locations...")
    
    success_count = 0
    
    for i, pole in enumerate(tqdm(sample_poles)):
        coords = pole["geometry"]["coordinates"]
        lon, lat = coords[0], coords[1]
        pid = pole.get("properties", {}).get("id", f"pole_{i}")
        
        ok, img_bytes = fetch_satellite_tile(lat, lon, pid)
        
        if ok:
            fname = f"{pid}_SAT.jpg"
            with open(IMAGES_DIR / fname, "wb") as f:
                f.write(img_bytes)
                           
            # For Manual Annotation Feed, we do NOT want to auto-label.
            # We want the user to click.
            # However, we could save a "proposal" if the UI supported it.
            # For now, we just skip writing the label file so it appears as "Pending".
            
            # px, py = lat_lon_to_pixel_in_tile(lat, lon, ZOOM_LEVEL)
            # label = generate_sat_yolo_label(px, py)
            # 
            # with open(LABELS_DIR / f"{pid}_SAT.txt", "w") as f:
            #     f.write(label)
                
            success_count += 1
            
    logger.info(f"Satellite Mining Complete. Captured {success_count} aerial views.")
    logger.info(f"Saved to {OUTPUT_DIR}")

if __name__ == "__main__":
    mine_satellite()
