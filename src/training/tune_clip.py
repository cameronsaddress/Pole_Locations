
import argparse
import sys
import json
import logging
from pathlib import Path
import time

# Add project root
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.detection.pole_detector import PoleDetector
from src.config import CONFIDENCE_THRESHOLD, IOU_THRESHOLD

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def tune_clip(confidence, nms_threshold):
    """
    Run a validation pass with specific CLIP thresholds.
    """
    logger.info(f"Starting CLIP Tuning Trial. ClfConf={confidence}, NMS={nms_threshold}")
    
    # 1. Initialize Detector with tunable params
    # Note: 'nms_threshold' passed in args usually refers to YOLO IOU, 
    # but the user context implies tuning CLIP.
    # We will map 'nms' to Detection IOU for now.
    
    detector = PoleDetector(
        confidence=CONFIDENCE_THRESHOLD, 
        iou=nms_threshold, # Using NMS arg for IOU
        classification_confidence=confidence # The main tuning knob
    )
    
    # 2. Select Validation Data
    # For a real tuning loop, we should ideally use a 'val' folder.
    # Defaulting to some NAIP tiles.
    tile_dir = Path("data/imagery/naip_tiles")
    if not tile_dir.exists():
         print(json.dumps({"error": "No imagery found", "defect_rate": 0.0}))
         return

    all_tiles = list(tile_dir.glob("*.tif"))[:2] # Processing 2 tiles for speed in tuning loop
    
    if not all_tiles:
        print(json.dumps({"error": "No tiles found", "defect_rate": 0.0}))
        return

    # 3. Run Inference
    total_poles = 0
    defects = {}
    
    start_time = time.time()
    
    for tile_path in all_tiles:
        try:
            detections = detector.detect_tiles([tile_path], crop_size=640, stride=512)
            
            for d in detections:
                cls = d.get('class_name', 'pole_good')
                
                # Count defects (anything not good)
                if cls != 'pole_good':
                    defects[cls] = defects.get(cls, 0) + 1
                    
            total_poles += len(detections)
        except Exception as e:
            logger.error(f"Tile processing failed: {e}")

    # 4. Calculate Metrics
    # Since we lack ground truth, we treat "Defect Rate" as the signal.
    # The LLM will use this to say "Too many false positives?" or "Finding nothing?"
    
    defect_count = sum(defects.values())
    defect_rate = (defect_count / total_poles) if total_poles > 0 else 0.0
    
    metrics = {
        "poles_scanned": total_poles,
        "defect_count": defect_count,
        "defect_rate": round(defect_rate, 3),
        "defects_breakdown": defects,
        "status": "completed"
    }
    
    logger.info(f"Trial Complete. Defect Rate: {defect_rate:.1%}")
    print(json.dumps(metrics))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--confidence", type=float, default=0.4)
    parser.add_argument("--nms", type=float, default=0.45)
    args = parser.parse_args()
    
    tune_clip(args.confidence, args.nms)
