import time
import shutil
import logging
from pathlib import Path
from datetime import datetime

# Config
# Use relative paths for Docker/Host compatibility
PROJECT_ROOT = Path(__file__).parent.parent.parent
INCOMING_DIR = PROJECT_ROOT / "data" / "incoming"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed_incoming"
INCOMING_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def validate_image(file_path: Path) -> bool:
    """
    Simulate EXIF/Metadata validation.
    In a real scenario, this would check for GPS tags.
    """
    # Placeholder: Accept all .jpg/.png
    if file_path.suffix.lower() not in ['.jpg', '.jpeg', '.png']:
        return False
    
    # Simulate corruption check
    if file_path.stat().st_size == 0:
        return False
        
    return True

from src.detection.ensemble_engine import EnsembleEngine

# Initialize Engine
ensemble = EnsembleEngine()

def process_file(file_path: Path):
    """
    Process a single file: Validation -> Preprocessing -> Inference -> Action.
    """
    logger.info(f"Detected new file: {file_path.name}")
    
    if not validate_image(file_path):
        logger.warning(f"Invalid file: {file_path.name}. Moving to quarantine.")
        return

    # Simulate Preprocessing
    time.sleep(0.1) 
    
    # Run AI Ensemble
    logger.info(f"   -> Triggering Ensemble Analysis for {file_path.name}...")
    try:
        results = ensemble.analyze_image(file_path)
        
        # Decision Logic
        for det in results.get("detections", []):
            label = det['defect_type']
            score = det['severity_score']
            logger.info(f"      [DETECTION] {label} (Severity: {score:.2f})")
            
            if label != "Healthy":
                logger.warning(f"      ⚠️ FLAGGED: {label}. Submitting Work Order...")
                submit_work_order(det, file_path.name)
                
    except Exception as e:
        logger.error(f"Inference failed: {e}")

    # Move to processed
    target_path = PROCESSED_DIR / file_path.name
    shutil.move(str(file_path), str(target_path))
    logger.info(f"✅ Archived to {target_path}")

def submit_work_order(det_data, filename):
    """Mock API Submission"""
    logger.info(f"      [API] POST /work_orders [pole_id=UNK, defect={det_data['defect_type']}] -> 201 Created")

def run_watcher():
    logger.info(f"Starting Ingestion Service - Monitoring {INCOMING_DIR}...")
    try:
        while True:
            # Poll directory
            files = list(INCOMING_DIR.glob("*"))
            if files:
                for f in files:
                    if f.is_file():
                        try:
                            process_file(f)
                        except Exception as e:
                            logger.error(f"Error processing {f.name}: {e}")
            
            time.sleep(5) # Poll every 5s
    except KeyboardInterrupt:
        logger.info("Stopping Ingestion Service.")

if __name__ == "__main__":
    run_watcher()
