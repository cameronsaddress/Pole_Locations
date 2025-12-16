
import os
import cv2
import torch
import requests
import numpy as np
import json
from pathlib import Path
from tqdm import tqdm
from PIL import Image

# Dummy placeholder for Grounding DINO to prevent import errors if not installed in the dev container
# Real execution happens inside the GPU container which will have it installed.
try:
    from groundingdino.util.inference import load_model, load_image, predict, annotate
    import groundingdino.datasets.transforms as T
except ImportError:
    pass

# Configuration
INPUT_GRID = Path('data/processed/grid_backbone.geojson')
if not INPUT_GRID.exists():
    INPUT_GRID = Path('frontend-enterprise/public/pole_network_v2.geojson')

OUTPUT_DIR = Path('frontend-enterprise/public') # Save directly to public for review

# Constants
ZOOM_LEVEL = 19
TILE_SERVER_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'

def lat_lon_to_tile(lat, lon, zoom):
    import math
    n = 2.0 ** zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return xtile, ytile

def fetch_satellite_tile(lat, lon, pole_id):
    x, y = lat_lon_to_tile(lat, lon, ZOOM_LEVEL)
    z = ZOOM_LEVEL
    url = TILE_SERVER_URL.format(z=z, x=x, y=y)
    try:
        headers = {'User-Agent': 'PoleDetectorBot/1.0'}
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            return True, resp.content
        return False, None
    except Exception as e:
        return False, None

def run_smart_mining():
    print('Starting Smart Mining on GPU...', flush=True)
    
    # Check GPU
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f'Using device: {device}', flush=True)

    # Load Model (Grounding DINO)
    # Weights path assumed inside container
    config_path = 'GroundingDINO/groundingdino/config/GroundingDINO_SwinT_OGC.py'
    weights_path = 'weights/groundingdino_swint_ogc.pth'
    
    # Minimal check to ensure we are in the right env
    if not os.path.exists(weights_path):
        print(f'Weights not found at {weights_path}, downloading...', flush=True)
        os.makedirs('weights', exist_ok=True)
        url = 'https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth'
        r = requests.get(url)
        with open(weights_path, 'wb') as f:
            f.write(r.content)

    try:
        model = load_model(config_path, weights_path)
    except Exception as e:
        print(f'Failed to load Grounding DINO: {e}. Ensure repo is cloned.', flush=True)
        return

    # Load Grid
    with open(INPUT_GRID) as f:
        data = json.load(f)
    features = data.get('features', [])
    poles = [f for f in features if f['geometry']['type'] == 'Point']
    
    # Sample 5
    sample_poles = poles[:5]
    
    print(f'Processing {len(sample_poles)} samples for user verification...', flush=True)

    TEXT_PROMPT = 'utility pole'
    BOX_TRESHOLD = 0.35
    TEXT_TRESHOLD = 0.25

    for i, pole in enumerate(tqdm(sample_poles)):
        coords = pole['geometry']['coordinates']
        lon, lat = coords[0], coords[1]
        pid = pole.get('properties', {}).get('id', f'pole_{i}')
        
        ok, img_bytes = fetch_satellite_tile(lat, lon, pid)
        if not ok:
            continue
            
        # Save temp image for processing
        temp_path = f'temp_{pid}.jpg'
        with open(temp_path, 'wb') as f:
            f.write(img_bytes)
            
        # Inference
        image_source, image = load_image(temp_path)
        
        boxes, logits, phrases = predict(
            model=model,
            image=image,
            caption=TEXT_PROMPT,
            box_threshold=BOX_TRESHOLD,
            text_threshold=TEXT_TRESHOLD
        )
        
        # Annotation
        annotated_frame = annotate(image_source=image_source, boxes=boxes, logits=logits, phrases=phrases)
        cv2.imwrite(str(OUTPUT_DIR / f'smart_check_{i}.jpg'), annotated_frame)
        
        # Cleanup
        os.remove(temp_path)

    print('Smart Mining Complete. Check frontend-enterprise/public/smart_check_*.jpg', flush=True)

if __name__ == '__main__':
    run_smart_mining()

