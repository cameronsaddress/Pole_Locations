
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
    Data: { "image_id": str, "box": {}, "dataset": "street" }
    """
    image_id = data["image_id"]
    box = data["box"] 
    dataset = data.get("dataset", "street")
    
    _, lbl_dir, _ = get_dataset_paths(dataset)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    
    label_path = lbl_dir / f"{image_id}.txt"
    with open(label_path, "w") as f:
        # Class 0 = Pole
        f.write(f"0 {box['x']} {box['y']} {box['w']} {box['h']}\n")
        
    return {"status": "saved"}

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
        
        # 2. Encode
        try:
            with open(img_path, "rb") as f:
                b64_img = base64.b64encode(f.read()).decode('utf-8')
            yield json.dumps({"log": "🔢 Base64 Encoding Complete"}) + "\n"
        except Exception as e:
            yield json.dumps({"error": f"Encoding failed: {e}"}) + "\n"
            return
            
        # 3. Construct Prompt
        model = "google/gemini-2.0-flash-001"
        yield json.dumps({"log": f"🤖 Model: {model}"}) + "\n"
        
        system_prompt = ""
        if dataset == "street":
            system_prompt = """You are an expert utility asset surveyor. 
Analyze this Street View image to detect UTILITY POLES.
- IGNORE: Traffic lights, lamp posts (unless on a utility pole), sign posts, trees.
- TARGET: Wooden or concrete vertical utility poles carrying wires.
- OUTPUT: A JSON object with a list of bounding boxes for ALL visible poles.
- FORMAT: {"boxes": [[x_center, y_center, width, height], ...]} (Normalized 0-1, 0.5 center).
- If NO poles are clearly visible, return {"boxes": []}."""
        else:
            system_prompt = """You are an expert geospatial analyst.
Analyze this Satellite Orthophoto to detect UTILITY POLES.
- VISUAL CUES: Look for small circular/rectangular dots with distinct SHADOWS.
- CONTEXT: Usually located along roads or property lines.
- OUTPUT: A JSON object with a list of bounding boxes.
- FORMAT: {"boxes": [[x_center, y_center, width, height], ...]} (Normalized 0-1).
- NOTE: Satellite poles are small. Bounding boxes should be tight (approx 0.02-0.05 size).
- If uncertain or no poles, return {"boxes": []}."""

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": "Detect poles in this image. Return strictly JSON."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                    ]
                }
            ],
            "response_format": {"type": "json_object"}
        }
        
        yield json.dumps({"log": "📡 Sending to OpenRouter..."}) + "\n"
        
        try:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://polevision.ai",
                "X-Title": "PoleVision AI"
            }
            resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
            
            if resp.status_code != 200:
                yield json.dumps({"error": f"API Error {resp.status_code}: {resp.text}"}) + "\n"
                return
                
            data = resp.json()
            content = data['choices'][0]['message']['content']
            yield json.dumps({"log": "📩 Response Received"}) + "\n"
            
            # Clean Markdown wrappers
            clean_content = content.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean_content)
            
            boxes = result.get("boxes", [])
            yield json.dumps({"log": f"🔎 Detected {len(boxes)} poles."}) + "\n"
            
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
                        # Safety check format
                        if len(box) == 4:
                             # YOLO: class x y w h
                             f.write(f"0 {box[0]:.6f} {box[1]:.6f} {box[2]:.6f} {box[3]:.6f}\n")
                
                yield json.dumps({"log": f"💾 Saved {len(boxes)} labels to disk."}) + "\n"
                yield json.dumps({"action": "saved", "count": len(boxes)}) + "\n"
                
        except Exception as e:
            yield json.dumps({"error": f"LLM Processing Failed: {e}"}) + "\n"
            return
            
    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
