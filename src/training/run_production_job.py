
import sys
import logging
import json
import argparse
from pathlib import Path
import time

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.detection.pole_detector import PoleDetector
from src.config import CONFIDENCE_THRESHOLD, IOU_THRESHOLD, PROCESSED_DATA_DIR

# Setup logging to stderr so stdout is reserved for JSON stream
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format='[JOB] %(message)s')
logger = logging.getLogger(__name__)

def run_production_job(limit_tiles=None, task="full"):
    logger.info(f"Initializing Production Pipeline (Task: {task})...")
    
    # 1. Initialize Detector
    # If detect-only, we should ideally disable CLIP loading to save resources.
    # Currently PoleDetector loads it automatically. 
    detector = PoleDetector(
        confidence=CONFIDENCE_THRESHOLD,
        iou=IOU_THRESHOLD
    )
    
    # TODO: Modify PoleDetector to allow disabling classifier via init arg if needed for performance.
    # For now, we will perform the task logic by filtering results.
    
    # 2. Find Tiles
    tile_dir = Path("data/imagery/naip_tiles")
    if not tile_dir.exists():
        logger.error(f"Imagery directory not found: {tile_dir}")
        return
        
    all_tiles = list(tile_dir.glob("*.tif"))
    if not all_tiles:
        logger.error("No imagery tiles found to process.")
        return
        
    if limit_tiles:
        all_tiles = all_tiles[:limit_tiles]
        
    logger.info(f"Processing {len(all_tiles)} tiles...")
    
    # 3. Storage for Results
    total_poles = 0
    defects = {
        "pole_good": 0,
        "pole_rust": 0, 
        "pole_attachment": 0,
        "pole_nest": 0,
        "pole_vegetation": 0,
        "pole_leaning": 0,
        "pole_damage": 0
    }
    
    # 4. Run Inference
    results = []
    start_time = time.time()
    
    for i, tile_path in enumerate(all_tiles):
        logger.info(f"Scanning Tile {i+1}/{len(all_tiles)}: {tile_path.name}")
        
        # Detect & Classify
        detections = detector.detect_tiles([tile_path], crop_size=640, stride=512)
        
        for d in detections:
            cls = d.get('class_name', 'pole_good')
            defects[cls] = defects.get(cls, 0) + 1
            results.append(d)
        
        total_poles += len(detections)
        
        # Stream progress update to stdout for Backend API
        progress = {
            "type": "progress",
            "tiles_processed": i + 1,
            "total_tiles": len(all_tiles),
            "poles_found": total_poles,
            "defects": defects
        }
        print(json.dumps(progress), flush=True)

    runtime = time.time() - start_time
    logger.info(f"Job Complete. Found {total_poles} poles in {runtime:.1f}s.")
    
    # 5. Save Results
    output_file = PROCESSED_DATA_DIR / f"production_run_{int(time.time())}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
        
    logger.info(f"Results saved to {output_file}")
    
    # Final Result
    final_output = {
        "type": "complete",
        "total_poles": total_poles,
        "defects": defects,
        "output_file": str(output_file)
    }
    print(json.dumps(final_output), flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=3, help="Limit number of tiles for demo speed")
    parser.add_argument("--task", default="full", choices=["full", "detect-only"], help="Job mode")
    args = parser.parse_args()
    
    run_production_job(limit_tiles=args.limit, task=args.task)
