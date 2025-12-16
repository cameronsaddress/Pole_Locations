
import os
import cv2
import glob
from pathlib import Path
from tqdm import tqdm
from autodistill_grounding_dino import GroundingDINO
from autodistill.detection import CaptionOntology
import supervision as sv

# Configuration
INPUT_DIR = Path('data/training/layer1_drops/images')
OUTPUT_DIR = Path('frontend-enterprise/public')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def run_smart_street_mining():
    print('Starting Smart Street Mining on GPU...', flush=True)
    
    # Initialize Grounding DINO
    # RESTRICTED ONTOLOGY: User feedback indicated "utility line" caused hallucinations on road markings.
    # NEGATIVE PROMPTING: We explicitly map 'windshield wiper' so we can IGNORE it.
    print('Initializing Grounding DINO...', flush=True)
    ontology = CaptionOntology({
        'utility pole': 'utility_pole',
        'wooden pole': 'utility_pole',
        'windshield wiper': 'obstruction',
        'car mirror': 'obstruction',
        'dashboard': 'obstruction'
    })
    
    base_model = GroundingDINO(ontology=ontology)
    print('Model Initialized.', flush=True)

    # Find Images
    image_paths = sorted(list(INPUT_DIR.glob('*_GSV.jpg')))
    print(f"Found {len(image_paths)} Street View images.", flush=True)
    
    if not image_paths:
        print("No images found! Check generation script.", flush=True)
        return

    # Process ALL Images (Continuous Loop)
    print(f'Starting Continuous Smart Street Mining (Threaded Load)...', flush=True)

    # Setup Training Output
    TRAIN_DIR = Path('data/training/street_smart_drops')
    TRAIN_DIR.mkdir(parents=True, exist_ok=True)
    
    import concurrent.futures
    import queue
    import threading
    import time
    
    # Seen set to avoid re-processing
    seen_files = set()
    
    while True:
        # Find New Images
        all_images = set(INPUT_DIR.glob('*_GSV.jpg'))
        new_images = list(all_images - seen_files)
        
        if not new_images:
            print("No new images... sleeping 10s", flush=True)
            time.sleep(10)
            continue
            
        print(f"Found {len(new_images)} NEW images to process...", flush=True)
        
        # Load Queue
        load_queue = queue.Queue(maxsize=50)

        def producer_load_images(paths):
            for p in paths:
                img = cv2.imread(str(p))
                if img is not None:
                    load_queue.put((p, img))
            load_queue.put(None)

        # Start Loader
        threading.Thread(target=producer_load_images, args=(new_images,), daemon=True).start()

        hits = 0
        pbar = tqdm(total=len(new_images))

        while True:
            try:
                item = load_queue.get(timeout=10)
                if item is None: break
                
                img_path, image = item
                h_img, w_img = image.shape[:2]
                
                # Mark as seen
                seen_files.add(img_path)
                
                try:
                    result = base_model.predict(str(img_path))
                    result = result.with_nms(threshold=0.3) 
                except Exception as e:
                    print(f'Prediction failed: {e}', flush=True)
                    pbar.update(1)
                    continue
                    
                # Filter Detections
                valid_detections = []
                
                for xyxy, confidence, class_id in zip(result.xyxy, result.confidence, result.class_id):
                    if confidence < 0.40: continue 
                    
                    detected_class_name = ontology.classes()[class_id]
                    if detected_class_name == 'obstruction':
                        continue # IGNORE OBSTRUCTIONS
                    
                    # If utility_pole (Yellow)
                    valid_detections.append((xyxy, confidence, class_id))
                
                if len(valid_detections) > 0:
                    hits += 1
                    pid = img_path.stem 
                    
                    # 1. SAVE IMAGE (Clean Copy)
                    clean_path = TRAIN_DIR / f'{pid}.jpg'
                    cv2.imwrite(str(clean_path), image)
                    
                    # 2. SAVE LABEL (YOLO .txt)
                    label_path = TRAIN_DIR / f'{pid}.txt'
                    with open(label_path, 'w') as f:
                        for xyxy, conf, cls_id in valid_detections:
                            x1, y1, x2, y2 = xyxy
                            
                            w = x2 - x1
                            h = y2 - y1
                            cx = x1 + (w / 2)
                            cy = y1 + (h / 2)
                            
                            nx = cx / w_img
                            ny = cy / h_img
                            nw = w / w_img
                            nh = h / h_img
                            
                            f.write(f"0 {nx:.6f} {ny:.6f} {nw:.6f} {nh:.6f}\n")
                
                pbar.update(1)
                
            except queue.Empty:
                break
        
        print(f"Batch Complete. Valid Hits: {hits}", flush=True)

if __name__ == '__main__':
    run_smart_street_mining()
