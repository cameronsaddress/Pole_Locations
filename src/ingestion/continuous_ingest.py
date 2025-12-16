
import time
import os
import shutil
import logging
from pathlib import Path
from datetime import datetime

# Config
INCOMING_DIR = Path("data/incoming")
PROCESSING_DIR = Path("data/processing")
ARCHIVE_DIR = Path("data/archive")
REJECTED_DIR = Path("data/rejected")
POLL_INTERVAL = 5  # Seconds

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ingestion.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("IngestService")

def setup_dirs():
    for d in [INCOMING_DIR, PROCESSING_DIR, ARCHIVE_DIR, REJECTED_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def validate_image(file_path):
    """
    Mock validation: Check extension and size.
    """
    valid_exts = {'.jpg', '.jpeg', '.png', '.tif', '.tiff'}
    if file_path.suffix.lower() not in valid_exts:
        return False, "Invalid Extension"
    
    if file_path.stat().st_size < 1024:
        return False, "File too small (Corrupt?)"
        
    return True, "Valid"

def process_file(file_path):
    logger.info(f"Detected new file: {file_path.name}")
    
    # 1. Move to Processing (Atomic-ish)
    processing_path = PROCESSING_DIR / file_path.name
    try:
        shutil.move(str(file_path), str(processing_path))
    except Exception as e:
        logger.error(f"Failed to move {file_path.name} to processing: {e}")
        return

    # 2. Validation
    is_valid, reason = validate_image(processing_path)
    if not is_valid:
        logger.warning(f"Rejected {file_path.name}: {reason}")
        shutil.move(str(processing_path), str(REJECTED_DIR / file_path.name))
        return

    # 3. Trigger Pipeline (Mock)
    logger.info(f"🚀 Triggering Inference Pipeline for {file_path.name}...")
    start_time = time.time()
    
    # ... Call to detect.py or ensemble_engine.py would go here ...
    time.sleep(0.5) # Simulate processing time
    
    duration = time.time() - start_time
    logger.info(f"✅ Pipeline Success for {file_path.name} ({duration:.2f}s)")
    
    # 4. Archive
    timestamp = datetime.now().strftime("%Y%m%d")
    archive_day_dir = ARCHIVE_DIR / timestamp
    archive_day_dir.mkdir(exist_ok=True)
    shutil.move(str(processing_path), str(archive_day_dir / file_path.name))

def run_ingest_loop():
    logger.info("Starting Continuous Ingestion Service...")
    logger.info(f"Watching {INCOMING_DIR.absolute()}")
    
    setup_dirs()
    
    while True:
        try:
            # List files
            files = list(INCOMING_DIR.glob("*"))
            if not files:
                time.sleep(POLL_INTERVAL)
                continue
                
            for f in files:
                if f.is_file():
                    process_file(f)
                    
        except KeyboardInterrupt:
            logger.info("Stopping Ingestion Service.")
            break
        except Exception as e:
            logger.error(f"Critical Loop Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_ingest_loop()
