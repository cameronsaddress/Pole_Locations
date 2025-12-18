
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

# PASDA PEMA 2018-2020 Statewide Orthoimagery (6-inch)
# Best available high-res for PA (Confirmed 53KB+).
WMS_URL = "https://imagery.pasda.psu.edu/arcgis/services/pasda/PEMAImagery2018_2020/MapServer/WMSServer"
LAYER_NAME = "0"

# Fallback/Primary logic
# We want to fetch a bounding box (e.g. 50x50m or 40x40m) around the pole.
# At 6-inch (0.15m) res: 40m = 266 pixels. 640px request = ~0.06m/px (upsampled) or larger area.
# Let's request 640x640 pixels covering ~100m (0.15m/px * 640 = 96m).
# 100m window is good for context.

# 0.1524m/px * 640px ~= 97.5m
METERS_PER_WINDOW = 97.5 
PIXEL_WIDTH = 640

# Paths
INPUT_GRID = Path("data/processed/grid_backbone.geojson")
if not INPUT_GRID.exists():
    INPUT_GRID = Path("frontend-enterprise/public/pole_network_v2.geojson")

OUTPUT_DIR = Path("/data/training/satellite_drops")
IMAGES_DIR = OUTPUT_DIR / "images"
LABELS_DIR = OUTPUT_DIR / "labels"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SatMiner")

def fetch_wms_bbox(lat, lon, pole_id):
    """
    Fetches a WMS Bounding Box centered on lat/lon.
    """
    try:
        # 1. Calculate BBox (approx meters to degrees)
        # 1 deg lat ~= 111,000 meters
        # 1 deg lon ~= 111,000 * cos(lat) meters
        
        half_side_m = METERS_PER_WINDOW / 2.0
        
        lat_delta = half_side_m / 111132.0
        lon_delta = half_side_m / (111132.0 * math.cos(math.radians(lat)))
        
        min_lon = lon - lon_delta
        min_lat = lat - lat_delta
        max_lon = lon + lon_delta
        max_lat = lat + lat_delta
        
        bbox_str = f"{min_lon},{min_lat},{max_lon},{max_lat}"
        
        # WMS 1.1.1 is safer for axis order (always Lon, Lat)
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.1.1",
            "REQUEST": "GetMap",
            "BBOX": bbox_str,
            "SRS": "EPSG:4326", 
            "WIDTH": str(PIXEL_WIDTH),
            "HEIGHT": str(PIXEL_WIDTH),
            "LAYERS": LAYER_NAME,
            "STYLES": "",
            "FORMAT": "image/jpeg",
        }
        
        # User-Agent strictly required
        headers = {"User-Agent": "PoleDetectorBot/1.0"}
        
        # Requests will URL-encode params automatically
        resp = requests.get(WMS_URL, params=params, headers=headers, timeout=10)
        
        if resp.status_code == 200:
            # Simple check if it's an image
            if resp.headers.get("Content-Type", "").startswith("image"):
                 return True, resp.content
            else:
                 logger.warning(f"WMS returned non-image: {resp.content[:100]}")
                 return False, None
        else:
            logger.warning(f"Failed WMS fetch {pole_id}: {resp.status_code} - {resp.text}")
            return False, None
            
    except Exception as e:
        logger.error(f"Error fetching sat {pole_id}: {e}")
        return False, None

def mine_satellite():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Loading grid for High-Res PASDA Mining (PEMA 2018-2020)...")
    with open(INPUT_GRID) as f:
        data = json.load(f)
        
    features = data.get("features", [])
    poles = [f for f in features if f["geometry"]["type"] == "Point"]
    
    # Filter out transmission towers if the data supports it
    dist_poles = []
    for p in poles:
        props = p.get("properties", {})
        p_type = props.get("power", "pole")
        if p_type != "tower":
            dist_poles.append(p)
            
    logger.info(f"Proceeding with {len(dist_poles)} distribution poles.")
    
    # Full Run
    sample_poles = dist_poles 
    logger.info(f"Mining High-Res Imagery for {len(sample_poles)} locations...")
    
    success_count = 0
    
    for i, pole in enumerate(tqdm(sample_poles)):
        coords = pole["geometry"]["coordinates"]
        lon, lat = coords[0], coords[1]
        pid = pole.get("properties", {}).get("id", f"pole_{i}")
        
        ok, img_bytes = fetch_wms_bbox(lat, lon, pid)
        
        if ok:
            fname = f"{pid}_SAT.jpg"
            with open(IMAGES_DIR / fname, "wb") as f:
                f.write(img_bytes)
            success_count += 1
            
    logger.info(f"High-Res Mining Complete. Captured {success_count} aerial views.")
    logger.info(f"Saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    mine_satellite()
