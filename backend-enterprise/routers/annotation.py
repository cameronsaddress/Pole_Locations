
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlmodel import Session, select, func
from database import get_session
from models import StreetViewImage
from typing import Dict, Any, List
from pathlib import Path
import random

router = APIRouter(tags=["Annotation"])

# Paths
# Paths
# Paths - Dynamic resolution
def get_dataset_paths(dataset: str = "street"):
    """
    Returns (images_dir, labels_dir, skipped_dir)
    """
    base = Path("/data/training")
    if dataset == "satellite":
        root = base / "satellite_drops"
    else:
        root = base / "layer1_drops" # street view
        
    img_dir = root / "images"
    # Ensure standard structure
    if dataset == "layer1_drops": # legacy check
        img_dir = root / "images" # existing structure
    
    # Satellite miner uses standard structure. 
    # Street miner uses root/images.
    # We will standardize on:
    # ROOT/images
    # ROOT/labels
    # ROOT/skipped
    
    return img_dir, root / "labels", root / "skipped"

@router.get("/next")
def get_next_image(dataset: str = "street", session: Session = Depends(get_session)):
    """
    Fetches the next pending image for annotation.
    """
    img_dir, lbl_dir, skip_dir = get_dataset_paths(dataset)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    
    # File-Based Source of Truth
    annotated_stems = {p.stem for p in lbl_dir.glob("*.txt")}
    skipped_stems = {p.stem for p in skip_dir.glob("*.txt")} if skip_dir.exists() else set()
    
    candidates = []
    count = 0
    
    # Optimization: If thousands of files, this glob is slow.
    # Future: Cache or DB.
    if not img_dir.exists():
         return {"status": "complete", "message": f"No data directory for {dataset}"}

    for p in img_dir.glob("*.jpg"):
        if p.stem not in annotated_stems and p.stem not in skipped_stems:
            candidates.append(p)
            count += 1
            if count > 100: break 
            
    if not candidates:
        return {"status": "complete"}
        
    choice = random.choice(candidates)
    
    return {
        "status": "active",
        "image_id": choice.stem, 
        "image_url": f"/api/v2/pipeline/serve_image/{choice.name}?dataset={dataset}", 
        "filename": choice.name
    }

@router.post("/save")
def save_annotation(data: Dict[str, Any], session: Session = Depends(get_session)):
    """
    Saves the annotation.
    Data: { "image_id": str, "boxes": [{x,y,w,h}, ...], "dataset": "street" }
    """
    image_id = data["image_id"]
    boxes = data.get("boxes", [])
    
    # Backward compat for single box
    if "box" in data:
        boxes.append(data["box"])

    dataset = data.get("dataset", "street")
    
    _, lbl_dir, _ = get_dataset_paths(dataset)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    
    label_path = lbl_dir / f"{image_id}.txt"
    with open(label_path, "w") as f:
        for box in boxes:
            # Class 0 = Pole
            # Ensure we have w/h defaults if just points are sent
            w = box.get("w", 0.02)
            h = box.get("h", 0.02)
            f.write(f"0 {box['x']} {box['y']} {w} {h}\n")
        
    return {"status": "saved", "count": len(boxes)}

@router.post("/skip")
def skip_image(data: Dict[str, Any]):
    image_id = data["image_id"]
    dataset = data.get("dataset", "street")
    
    _, _, skip_dir = get_dataset_paths(dataset)
    skip_dir.mkdir(parents=True, exist_ok=True)
    
    with open(skip_dir / f"{image_id}.txt", "w") as f:
        f.write("skipped")
        
    return {"status": "skipped"}

@router.get("/stats")
def get_stats(dataset: str = "street"):
    img_dir, lbl_dir, skip_dir = get_dataset_paths(dataset)
    
    if not img_dir.exists():
         return {"count": 0, "target": 0, "pending": 0, "skipped": 0}

    annotated = len(list(lbl_dir.glob("*.txt"))) if lbl_dir.exists() else 0
    skipped = len(list(skip_dir.glob("*.txt"))) if skip_dir.exists() else 0
    total_images = len(list(img_dir.glob("*.jpg")))
    
    pending = max(0, total_images - annotated - skipped)
    
    return {
        "count": annotated, 
        "target": 2000, 
        "pending": pending,
        "skipped": skipped
    }

@router.post("/populate")
def populate_feed(data: Dict[str, Any], background_tasks: BackgroundTasks):
    """
    Triggers the background script.
    """
    import subprocess
    dataset = data.get("dataset", "street")
    
    def run_mining():
        try:
            subprocess.run([
                "python3", "src/training/populate_manual_feed.py", 
                "--count", "30",
                "--dataset", dataset
            ], check=True)
        except Exception as e:
            print(f"Populate failed: {e}")

    background_tasks.add_task(run_mining)
    return {"status": "started", "message": f"Mining 180+ new {dataset} poles..."}

@router.post("/clear")
def clear_unprocessed(data: Dict[str, Any]):
    dataset = data.get("dataset", "street")
    img_dir, lbl_dir, skip_dir = get_dataset_paths(dataset)
    
    annotated_stems = {p.stem for p in lbl_dir.glob("*.txt")} if lbl_dir.exists() else set()
    skipped_stems = {p.stem for p in skip_dir.glob("*.txt")} if skip_dir.exists() else set()
    
    kept = 0
    deleted = 0
    
    if img_dir.exists():
        for img_path in img_dir.glob("*.jpg"):
            if img_path.stem in annotated_stems or img_path.stem in skipped_stems:
                kept += 1
                continue
                
            try:
                img_path.unlink()
                deleted += 1
            except Exception as e:
                print(f"Failed to delete {img_path}: {e}")
            
    return {"status": "cleared", "deleted": deleted, "kept": kept}

# --- LLM Annotation Feature ---

import os
import base64
import json
import requests
import re
from fastapi.responses import StreamingResponse

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

@router.get("/llm-stream")
def annotate_with_llm(image_id: str, dataset: str = "street"):
    """
    Streams the LLM process for a single image.
    Uses GET to easily support EventSource if needed, but we will use raw fetch reader.
    """
    
    def event_stream():
        yield json.dumps({"log": f"🚀 Starting AI Analysis for {image_id}..."}) + "\n"
        
        # 1. Locate Image
        img_dir, lbl_dir, skip_dir = get_dataset_paths(dataset)
        img_path = img_dir / f"{image_id}.jpg"
        # Try diff extensions if needed, but for now strict
        if not img_path.exists():
             # Try finding it
             candidates = list(img_dir.glob(f"{image_id}.*"))
             if candidates:
                 img_path = candidates[0]
             else:
                 yield json.dumps({"error": f"Image not found: {image_id}"}) + "\n"
                 return

        yield json.dumps({"log": f"📸 Image Found: {img_path.name}"}) + "\n"
        
        # 2. Encode & Get Dims
        try:
            import struct
            
            with open(img_path, "rb") as f:
                img_bytes = f.read()
                b64_img = base64.b64encode(img_bytes).decode('utf-8')

            # Manual Image Size Parsing (No PIL dependency)
            def get_image_dimensions(data):
                # PNG
                if data[:8] == b'\x89PNG\r\n\x1a\n':
                    w, h = struct.unpack('>II', data[16:24])
                    return w, h
                # JPEG
                elif data[:2] == b'\xff\xd8':
                    size = len(data)
                    offset = 2
                    while offset < size:
                        try:
                            marker, = struct.unpack('>H', data[offset:offset+2])
                            offset += 2
                            if marker == 0xFFD9: break # EOI
                            length, = struct.unpack('>H', data[offset:offset+2])
                            # SOF0 (Start of Frame 0) - FFC0 or FFC2
                            if marker >= 0xFFC0 and marker <= 0xFFCF and marker not in [0xFFC4, 0xFFC8, 0xFFCC]:
                                h, w = struct.unpack('>HH', data[offset+1:offset+5])
                                return w, h
                            offset += length
                        except:
                            break
                return 1024, 768 # Fallback default

            img_w, img_h = get_image_dimensions(img_bytes)
                
            yield json.dumps({"log": f"🔢 Image Loaded: {img_w}x{img_h}"}) + "\n"
        except Exception as e:
            yield json.dumps({"error": f"Encoding failed: {e}"}) + "\n"
            return

        # ... (Prompt construction unchanged) ...

        # ... (LLM Call unchanged) ...

            # 4. Save Logic
            if not boxes:
                # No poles -> Mark as Skipped
                _, _, skip_dir = get_dataset_paths(dataset)
                skip_dir.mkdir(parents=True, exist_ok=True)
                with open(skip_dir / f"{image_id}.txt", "w") as f:
                    f.write("no_pole_llm")
                yield json.dumps({"log": "🗑️ Marked as Skipped (No Pole)"}) + "\n"
                yield json.dumps({"action": "skipped"}) + "\n"
            else:
                # Save Labels
                _, lbl_dir, _ = get_dataset_paths(dataset)
                lbl_dir.mkdir(parents=True, exist_ok=True)
                
                label_path = lbl_dir / f"{image_id}.txt"
                with open(label_path, "w") as f:
                    for box in boxes:
                        if len(box) == 4:
                             x, y, w, h = box
                             
                             # AUTO-FIX: Normalize if pixels provided
                             if x > 1.0: x = x / img_w
                             if y > 1.0: y = y / img_h
                             
                             # Width/Height might also be pixels
                             # Logic: if > 1.0, definitely pixels. 
                             # If < 1.0, likely normalized (unless pole is tiny 1px wide? rare)
                             if w > 1.0: w = w / img_w
                             if h > 1.0: h = h / img_h
                             
                             # Clamp to [0,1] just in case
                             x = max(0.0, min(1.0, x))
                             y = max(0.0, min(1.0, y))
                             w = max(0.0, min(1.0, w))
                             h = max(0.0, min(1.0, h))

                             f.write(f"0 {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n")
                
                yield json.dumps({"log": f"💾 Saved {len(boxes)} labels to disk."}) + "\n"
                yield json.dumps({"action": "saved", "count": len(boxes)}) + "\n"
                
        except Exception as e:
            yield json.dumps({"error": f"LLM Processing Failed: {e}"}) + "\n"
            return
            
    return StreamingResponse(event_stream(), media_type="application/x-ndjson")

@router.get("/recent")
def get_recent_annotations(dataset: str = "street", limit: int = 10):
    _, lbl_dir, _ = get_dataset_paths(dataset)
    
    if not lbl_dir.exists():
        return []
        
    # Get all txt files sorted by modification time (newest first)
    files = list(lbl_dir.glob("*.txt"))
    # Sort by mtime
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    files = files[:limit]
    
    results = []
    for p in files:
        image_id = p.stem
        # Read boxes
        boxes = []
        try:
            with open(p, "r") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        # YOLO: class x y w h
                        cls, x, y, w, h = map(float, parts[:5])
                        boxes.append({"x": x, "y": y, "w": w, "h": h})
        except:
            pass
            
        results.append({
            "image_id": image_id,
            "filename": f"{image_id}.jpg", 
            "image_url": f"/api/v2/pipeline/serve_image/{image_id}.jpg?dataset={dataset}",
            "boxes": boxes
        })
        
    return results

# --- Map-Based Annotation (Active Learning) ---
@router.post("/from_map")
def annotate_from_map(data: Dict[str, Any], session: Session = Depends(get_session)):
    """
    Active Learning: User clicks on map -> We crop tile -> Save as training sample.
    Input: { "lat": float, "lon": float, "dataset": "satellite" }
    """
    from models import Tile
    from geoalchemy2.shape import from_shape
    from shapely.geometry import Point
    import rasterio
    from rasterio.windows import Window
    import numpy as np
    from PIL import Image
    import uuid
    from datetime import datetime

    lat = data.get("lat")
    lon = data.get("lon")
    dataset = data.get("dataset", "satellite")
    
    if not lat or not lon:
        return {"status": "error", "message": "Missing lat/lon"}

    # 1. Find Tile
    # Using SQLModel with PostGIS
    # Note: Ensure SRID 4326 matches DB
    point = from_shape(Point(lon, lat), srid=4326)
    
    # Simple check: BBox overlap (fastest)
    stmt = select(Tile).where(func.ST_Intersects(Tile.bbox, point)).limit(1)
    tile = session.exec(stmt).first()
    
    if not tile:
        return {"status": "error", "message": "No imagery tile found at this location."}
        
    # 2. Open Tile
    tile_path = Path(tile.path)
    if not tile_path.exists():
         return {"status": "error", "message": "Tile file missing."}

    try:
        with rasterio.open(tile_path) as src:
            # 3. Convert Lat/Lon to Pixel
            # src.index(lon, lat) returns (row, col)
            row, col = src.index(lon, lat)
            
            # 4. Crop (640x640)
            crop_size = 640
            half = crop_size // 2
            
            # Calculate window (clamped)
            r_start = max(0, row - half)
            c_start = max(0, col - half)
            
            window = Window(c_start, r_start, crop_size, crop_size)
            
            # Read
            data_arr = src.read([1, 2, 3], window=window)
            
            # Check if crop is full size (edge case)
            if data_arr.shape[1] != crop_size or data_arr.shape[2] != crop_size:
                 # TODO: Pad? For now, just reject edge clicks if too close
                 pass
                 
            # Convert to HWC
            img = np.transpose(data_arr, (1, 2, 0))
            
            # 5. Save
            img_dir, lbl_dir, _ = get_dataset_paths("satellite") # Force satellite drops
            img_dir.mkdir(parents=True, exist_ok=True)
            lbl_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate ID
            new_id = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
            
            # Save Image (RGB)
            pil_img = Image.fromarray(img)
            pil_img.save(img_dir / f"{new_id}.jpg")
            
            # 6. Create Label (Center Point)
            # Since we cropped CENTERED on the lat/lon (mostly), 
            # the pole is at (0.5, 0.5) relative to the crop!
            
            # Refine Center:
            # We requested crop at (row-half, col-half).
            # The click was at (row, col).
            # So the click is at (row - r_start, col - c_start) inside the crop.
            
            rel_y = (row - r_start) / data_arr.shape[1] # Height is shape[1]
            rel_x = (col - c_start) / data_arr.shape[2] # Width is shape[2]
            
            label_path = lbl_dir / f"{new_id}.txt"
            with open(label_path, "w") as f:
                # Class 0, X, Y, W, H
                # Using small box 0.02
                f.write(f"0 {rel_x:.6f} {rel_y:.6f} 0.02 0.02\n")
            
            # 7. Reset Tile Status to Pending (Trigger Re-Inference)
            tile.status = "pending"
            session.add(tile)
            session.commit()
                
            return {
                "status": "success", 
                "image_id": new_id, 
                "tile_id": tile.id,
                "message": "Sample saved. Tile marked for re-scan."
            }
            
    except Exception as e:
        return {"status": "error", "message": str(e)}
