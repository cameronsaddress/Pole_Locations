
import logging
from sqlmodel import Session, text
from database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_fusion_service():
    logger.info("Starting Fusion Service...")
    
    with Session(engine) as session:
        # Match Detections to Existing Poles (within 10m)
        
        # 1. New High-Confidence Poles (Flagged)
        # Condition: High Conf (>0.6), Close to Road (<50m), No existing pole within 10m
        query_new = """
        INSERT INTO poles (id, pole_id, location, status, last_verified_at, tags, financial_impact)
        SELECT 
            gen_random_uuid(), 
            'NEW_' || to_char(now(), 'YYYYMMDD_HH24MISS') || '_' || substr(md5(random()::text), 1, 6), 
            d.location, 
            'Flagged', 
            now(), 
            d.tags,
            0.0
        FROM detections d
        WHERE d.confidence > 0.6
        AND (d.road_distance_m IS NULL OR d.road_distance_m < 50)
        AND NOT EXISTS (
            SELECT 1 FROM poles p 
            WHERE ST_DWithin(p.location::geography, d.location::geography, 10.0::float8)
        )
        -- Exclude detections already converted/linked? (TODO: Add 'processed' flag to detections if needed)
        -- For now, simple insert. Deduplication via Unique constraint on pole_id won't help here as we generate new IDs.
        -- We should rely on NOT EXISTS check.
        ;
        """
        
        # 2. Update Existing Poles (Verified)
        # Condition: Existing pole within 10m of a High Conf detection
        query_update = """
        UPDATE poles p
        SET last_verified_at = now(),
            status = 'Verified'
        FROM detections d
        WHERE ST_DWithin(p.location::geography, d.location::geography, 10.0::float8)
        AND d.confidence > 0.7;
        """
        
        try:
            logger.info("Executing Fusion: Inserting New Poles...")
            session.exec(text(query_new))
            session.commit()
            
            logger.info("Executing Fusion: Updating Existing Poles...")
            session.exec(text(query_update))
            session.commit()
            
            logger.info("✅ Fusion Complete.")
            
        except Exception as e:
            logger.error(f"Fusion failed: {e}")
            session.rollback()

if __name__ == "__main__":
    run_fusion_service()
