
import logging
from sqlalchemy import create_engine, text
from src.config import DATABASE_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Migration")

def add_status_column():
    engine = create_engine("postgresql://pole_user:pole_secure_password@localhost:5433/polevision")
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE street_view_images ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'pending';"))
            conn.commit()
        logger.info("✅ Successfully added 'status' column to street_view_images.")
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")

if __name__ == "__main__":
    add_status_column()
