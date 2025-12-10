
import sys
from pathlib import Path
import logging
import pandas as pd
from src.detection.pole_detector import PoleDetector
from src.config import CONFIDENCE_THRESHOLD, IOU_THRESHOLD

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_clip():
    # 1. Setup Detector
    logger.info("Initializing Detector...")
    detector = PoleDetector(confidence=CONFIDENCE_THRESHOLD, iou=IOU_THRESHOLD)
    
    # 2. Define Tile Path
    # Using one of the tiles we saw in the logs
    tile_path = Path("data/imagery/naip_tiles/pa_m_4007641_se_18_060_20220510.tif")
    
    if not tile_path.exists():
        logger.error(f"Tile not found: {tile_path}")
        return
        
    logger.info(f"Running detection on {tile_path}...")
    
    # 3./Run Detection
    detections = detector.detect_tiles([tile_path], crop_size=640, stride=512)
    
    # 4. Analyze Results
    if not detections:
        logger.warning("No poles detected!")
        return

    df = pd.DataFrame(detections)
    logger.info(f"Detected {len(df)} poles.")
    
    if 'class_name' in df.columns:
        logger.info("\n=== Classification Distribution ===")
        print(df['class_name'].value_counts())
        
        logger.info("\n=== Sample Detections ===")
        print(df[['pole_id', 'ai_confidence', 'class_name']].head(10))
        
        # Save for inspection
        df.to_csv("data/processed/ai_detections_verify.csv", index=False)
        logger.info("Saved to data/processed/ai_detections_verify.csv")
    else:
        logger.error("No 'class_name' column found in results!")

if __name__ == "__main__":
    verify_clip()
