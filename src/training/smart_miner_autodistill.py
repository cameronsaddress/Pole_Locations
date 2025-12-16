
import os
import cv2
import torch
import requests
import numpy as np
import json
from pathlib import Path
from tqdm import tqdm
from PIL import Image

# Import AutoDistill which handles the heavy lifting
from autodistill_grounding_dino import GroundingDINO
from autodistill.detection import CaptionOntology

# Configuration
INPUT_GRID = Path('data/processed/philly_poles.geojson')
OUTPUT_DIR = Path('frontend-enterprise/public')

# PASDA PEMA 2021 - Elite Resolution (Dynamic Export)
# Service does NOT support tiles. We must use the dynamic 'export' endpoint.
EXPORT_URL = 'https://imagery.pasda.psu.edu/arcgis/rest/services/pasda/PEMAImagery2021/MapServer/export'

def get_bbox_for_pole(lat, lon, size_meters=35): # Increased to 35m for context
    # Approx degrees per meter
    lat_deg = size_meters / 111320.0
    lon_deg = size_meters / (111320.0 * 0.75) # Approx at PA latitude
    return f"{lon-lon_deg},{lat-lat_deg},{lon+lon_deg},{lat+lat_deg}"

def fetch_satellite_tile(lat, lon, pole_id):
    bbox = get_bbox_for_pole(lat, lon)
    params = {
        'bbox': bbox,
        'bboxSR': '4326', # Input Lat/Lon
        'imageSR': '4326', # Output Lat/Lon
        'size': '512,512', # High Res 512px tile
        'format': 'jpg',
        'f': 'image'
    }
    
    try:
        headers = {'User-Agent': 'PoleDetectorBot/1.0'}
        # Timeout to prevent hanging
        resp = requests.get(EXPORT_URL, params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            return True, resp.content
        print(f"Fetch failed {resp.status_code}: {resp.text[:100]}", flush=True)
        return False, None
    except Exception as e:
        print(f'Error fetching export: {e}', flush=True)
        return False, None

def run_smart_mining():
    print('Starting Smart Mining on GPU (AutoDistill)...', flush=True)
    
    # Initialize Grounding DINO - BROADENED ONTOLOGY
    print('Initializing Grounding DINO...', flush=True)
    ontology = CaptionOntology({
        'utility pole': 'utility_pole',
        'telegraph pole': 'utility_pole',
        'wooden pole': 'utility_pole',
        'street light': 'utility_pole',
        'pole': 'utility_pole'
    })
    
    base_model = GroundingDINO(ontology=ontology)
    print('Model Initialized.', flush=True)

    # Load Grid
    print('Loading Grid...', flush=True)
    with open(INPUT_GRID) as f:
        data = json.load(f)
    features = data.get('features', [])
    
    # Philly Data
    poles = [f for f in features if f['geometry']['type'] == 'Point']
    
    print(f"Loaded Grid: {len(poles)} Philly Poles", flush=True)
    
    # Run on FULL GRID
    sample_poles = poles # PROCESS ALL
    print(f'Processing ALL {len(sample_poles)} poles with Threaded Fetching...', flush=True)
    
    import supervision as sv
    import concurrent.futures
    import queue
    import threading
    import time

    # Setup Training Output
    TRAIN_DIR = Path('data/training/satellite_smart_drops')
    TRAIN_DIR.mkdir(parents=True, exist_ok=True)
    
    # Queue for decoupling Network (Producer) from GPU (Consumer)
    # Size 200 to have a healthy buffer
    img_queue = queue.Queue(maxsize=200)
    
    # Producer Function
    def producer_fetch_images(pole_list):
        print("Producer started...", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            # Helper to fetch and put in queue
            def fetch_and_enqueue(p_idx, p_obj):
                coords = p_obj['geometry']['coordinates']
                lon, lat = coords[0], coords[1]
                pid = p_obj.get('properties', {}).get('id', f'pole_{p_idx}')
                
                # Fetch
                ok, img_content = fetch_satellite_tile(lat, lon, pid)
                if ok:
                    img_queue.put((pid, img_content))
                # If fail, we just verify nothing content
            
            # Submit all tasks
            # caution: submitting 200k tasks might blow up memory if we aren't careful.
            # Better to iterate and submit in chunks or just use map but handle flow control.
            # Simple approach: standard loop with executor.submit, but we need to block if queue is full.
            # Actually, executor.submit is non-blocking to the queue, but we want to throttle creation.
            
            # Better Pattern: Manual Threaded Workers that pull from a task list?
            # Or just a simple loop in the producer thread that calls fetch (which is blocking) 
            # but we want MULTIPLE fetchers.
            
            # Let's effectively use the Executor as the parallelizer, but we need to iterate the list.
            futures = []
            for i, pole in enumerate(pole_list):
                while img_queue.full():
                    time.sleep(0.1)
                
                # Submit a task (async)
                fut = executor.submit(fetch_and_enqueue, i, pole)
                futures.append(fut)
                
                # Cleanup completed futures to save RAM
                # (Simple optimization: keep list small)
                if len(futures) > 100:
                    futures = [f for f in futures if not f.done()]
        
        # Signal End
        img_queue.put(None)
        print("Producer finished queuing.", flush=True)

    # Start Producer Thread
    prod_thread = threading.Thread(target=producer_fetch_images, args=(sample_poles,))
    prod_thread.daemon = True
    prod_thread.start()

    hits = 0
    pbar = tqdm(total=len(sample_poles))
    
    # Consumer Loop (Main Thread - GPU)
    while True:
        try:
            # Get from queue (wait up to 5s)
            item = img_queue.get(timeout=60) 
            if item is None:
                break # Sentinel
            
            pid, img_bytes = item
            
            # Save temp for AutoDistill file-based API
            # Ideally AutoDistill accepts numpy/TIL, but let's stick to file for stability
            temp_path = f'temp_{pid}.jpg'
            with open(temp_path, 'wb') as f:
                f.write(img_bytes)
            
            # Inference
            try:
                result = base_model.predict(temp_path)
                result = result.with_nms(threshold=0.5)
            except Exception as e:
                # print(f'Pred err: {e}')
                if os.path.exists(temp_path): os.remove(temp_path)
                pbar.update(1)
                continue

            # Filtering and Saving
            valid_detections = []
            for xyxy, conf, cls_id in zip(result.xyxy, result.confidence, result.class_id):
                if conf > 0.20:
                    valid_detections.append((xyxy, conf, cls_id))
            
            if len(valid_detections) > 0:
                hits += 1
                
                # Clean Image
                clean_path = TRAIN_DIR / f'{pid}.jpg'
                with open(clean_path, 'wb') as f:
                    f.write(img_bytes)
                    
                # YOLO Label
                img_w, img_h = 512, 512
                label_path = TRAIN_DIR / f'{pid}.txt'
                with open(label_path, 'w') as f:
                    for xyxy, conf, cls_id in valid_detections:
                        x1, y1, x2, y2 = xyxy
                        # Normalize
                        w = x2 - x1
                        h = y2 - y1
                        cx = x1 + (w / 2)
                        cy = y1 + (h / 2)
                        
                        f.write(f"0 {cx/img_w:.6f} {cy/img_h:.6f} {w/img_w:.6f} {h/img_h:.6f}\n")

            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            pbar.update(1)
            
        except queue.Empty:
            # If queue is empty for 60s, assume done or hung
            print("Queue empty for 60s, exiting...", flush=True)
            break
            
    pbar.close()
    print(f"Mining Complete. Hits: {hits}", flush=True)

    print('Smart Mining Complete. Check frontend-enterprise/public/smart_check_*.jpg', flush=True)

if __name__ == '__main__':
    run_smart_mining()
