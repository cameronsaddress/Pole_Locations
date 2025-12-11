
import logging
import argparse
import time
from src.pipeline.ingest_imagery import ingest_imagery_tiles
from src.pipeline.detect import run_detection_service
from src.pipeline.enrich import run_enrichment_service
from src.pipeline.fusion import run_fusion_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_pipeline(data_dirs, continuous=False):
    logger.info("🚀 Starting Enterprise Pipeline run...")
    
    # 1. Ingest
    logging.info("--- Stage 1: Ingestion ---")
    ingest_imagery_tiles(data_dirs)
    
    # 2. Detect
    logging.info("--- Stage 2: Detection ---")
    # In a real distributed system, this would be a separate worker.
    # Here we simulate the worker loop or just run it once.
    run_detection_service(limit=100)
    
    # 3. Enrich
    logging.info("--- Stage 3: Enrichment ---")
    run_enrichment_service()
    
    # 4. Fusion
    logging.info("--- Stage 4: Fusion ---")
    run_fusion_service()
    
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
