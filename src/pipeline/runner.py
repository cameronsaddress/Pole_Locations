
import logging
import argparse
import time
from src.pipeline.ingest_imagery import ingest_imagery_tiles
from src.pipeline.detect import run_detection_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_pipeline(data_dirs, continuous=False):
    logger.info("🚀 Starting Unified Enterprise Pipeline run...")
    
    # 1. Ingest
    logging.info("--- Stage 1: Ingestion ---")
    ingest_imagery_tiles(data_dirs)
    
    # 2. Unified Detection Service
    # (Inference -> Enrichment -> Fusion -> Persistence)
    logging.info("--- Stage 2: Unified Detection & Fusion ---")
    run_detection_service(limit=1000)
    
    logger.info("✅ Pipeline Run Complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dirs", nargs="+", default=["/data/imagery/naip_tiles"], help="Imagery directories")
    parser.add_argument("--loop", action="store_true", help="Run in continuous loop")
    args = parser.parse_args()
    
    if args.loop:
        while True:
            run_pipeline(args.dirs)
            logger.info("Sleeping 60s...")
            time.sleep(60)
    else:
        run_pipeline(args.dirs)
