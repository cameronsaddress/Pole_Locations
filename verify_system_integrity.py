
import sys
import os
from pathlib import Path
import logging

# Add src to path
sys.path.append(str(Path(__file__).parent / 'src'))

from config import (
    MODEL_TYPE, CONFIDENCE_THRESHOLD, FILTER_DROP_FAILURES,
    MODELS_DIR, DATA_DIR, OUTPUTS_DIR
)
from src.detection.pole_detector import PoleDetector

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("IntegrityCheck")

def check_file(path, description):
    if path.exists():
        logger.info(f"✅ {description} found: {path}")
        return True
    else:
        logger.error(f"❌ {description} MISSING: {path}")
        return False

def check_model():
    logger.info("--- Checking AI Model Configuration ---")
    logger.info(f"Configured Model Type: {MODEL_TYPE}")
    logger.info(f"Confidence Threshold: {CONFIDENCE_THRESHOLD}")
    
    if MODEL_TYPE != "yolov8l":
        logger.warning(f"⚠️ Model type is {MODEL_TYPE}, expected 'yolov8l' for Enterprise Grade.")
    
    if CONFIDENCE_THRESHOLD < 0.2:
        logger.warning(f"⚠️ Confidence threshold {CONFIDENCE_THRESHOLD} is low. Recommended > 0.25.")

    detector = PoleDetector()
    if detector.model:
         logger.info(f"✅ PoleDetector initialized successfully with model: {detector.model.overrides.get('model', 'Unknown') if hasattr(detector.model, 'overrides') else 'Loaded'}")
         logger.info(f"✅ Test Time Augmentation (TTA): {detector.augment}")
    else:
        logger.error("❌ PoleDetector failed to load model.")

def check_data():
    logger.info("--- Checking Data Assets ---")
    check_file(DATA_DIR / "raw" / "osm_poles_harrisburg_real.csv", "Historical Pole Records")
    check_file(DATA_DIR / "imagery" / "naip_tiles", "NAIP Imagery Tiles")
    check_file(MODELS_DIR / "yolov8l_v1" / "weights" / "best.pt", "Fine-tuned YOLOv8l Model")

def main():
    logger.info("Starting System Integrity Check...")
    check_model()
    check_data()
    logger.info("--- Integrity Check Complete ---")

if __name__ == "__main__":
    main()
