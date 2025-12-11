import logging
import sys
from sqlmodel import SQLModel
from database import engine
# Import models to register them with metadata
from models import Pole, Detection, Job, Tile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    logger.info("Connecting to database...")
    try:
        SQLModel.metadata.create_all(engine)
        logger.info("✅ Database tables created successfully.")
    except Exception as e:
        logger.error(f"❌ Failed to create tables: {e}")
        sys.exit(1)

if __name__ == "__main__":
    init_db()
