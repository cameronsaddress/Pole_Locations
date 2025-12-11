
import logging
from sqlmodel import Session, text
from database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from src.config import (
    FUSION_UPDATE_CONFIDENCE_THRESHOLD,
    FUSION_NEW_FLAGGED_CONFIDENCE_THRESHOLD,
    FUSION_NEW_FLAGGED_MAX_ROAD_DIST_M,
    FINANCIAL_IMPACT_DAMAGE,
    FINANCIAL_IMPACT_LEANING,
    FINANCIAL_IMPACT_VEGETATION
)

def run_fusion_service():
    logger.info("Starting Fusion Service...")
    
    with Session(engine) as session:
        # Match Detections to Existing Poles (within 10m)
        
        try:
            # 1. Update Existing Poles (Verified or Critical)
            logger.info("Executing Fusion: Updating Existing Poles with new AI sightings...")
            
            # Use binding for parameters
            params = {
                "damage_cost": FINANCIAL_IMPACT_DAMAGE,
                "leaning_cost": FINANCIAL_IMPACT_LEANING,
                "veg_cost": FINANCIAL_IMPACT_VEGETATION,
                "update_conf": FUSION_UPDATE_CONFIDENCE_THRESHOLD,
                "new_conf": FUSION_NEW_FLAGGED_CONFIDENCE_THRESHOLD,
                "max_road_dist": FUSION_NEW_FLAGGED_MAX_ROAD_DIST_M
            }

            query_update = """
            UPDATE poles p
            SET last_verified_at = now(),
                status = CASE 
                    WHEN d.class_name LIKE '%damage%' THEN 'Critical'
                    WHEN d.class_name LIKE '%leaning%' THEN 'Critical'
                    WHEN d.class_name LIKE '%vegetation%' THEN 'Review'
                    ELSE 'Verified' 
                END,
                financial_impact = CASE 
                    WHEN d.class_name LIKE '%damage%' THEN :damage_cost
                    WHEN d.class_name LIKE '%leaning%' THEN :leaning_cost
                    WHEN d.class_name LIKE '%vegetation%' THEN :veg_cost
                    ELSE 0.0
                END,
                tags = p.tags || jsonb_build_object('last_detection_source', 'AI', 'last_conf', d.confidence)
            FROM detections d
            WHERE ST_DWithin(p.location::geography, d.location::geography, 10.0::float8)
            AND d.confidence > :update_conf;
            """
            
            session.exec(text(query_update), params=params)
            session.commit()

            # 2. Insert New High-Confidence Poles (Flagged)
            logger.info("Executing Fusion: Inserting New Flagged Poles...")
            query_new = """
            INSERT INTO poles (id, pole_id, location, status, last_verified_at, tags, financial_impact)
            SELECT 
                gen_random_uuid(), 
                'AI_NEW_' || to_char(now(), 'YYYYMMDD_HH24MISS') || '_' || substr(md5(random()::text), 1, 6), 
                d.location, 
                CASE 
                    WHEN d.class_name LIKE '%damage%' THEN 'Critical'
                    WHEN d.class_name LIKE '%leaning%' THEN 'Critical'
                    ELSE 'Flagged'
                END, 
                now(), 
                d.tags || jsonb_build_object('source', 'AI_Discovery', 'initial_conf', d.confidence),
                CASE 
                    WHEN d.class_name LIKE '%damage%' THEN :damage_cost
                    WHEN d.class_name LIKE '%leaning%' THEN :leaning_cost
                    WHEN d.class_name LIKE '%vegetation%' THEN :veg_cost
                    ELSE 0.0
                END
            FROM detections d
            WHERE d.confidence > :new_conf
            -- Ensure we ignore trash detections far from roads (Context Filter)
            AND (d.road_distance_m IS NULL OR d.road_distance_m < :max_road_dist) 
            -- Crucial: Do not duplicate existing poles
            AND NOT EXISTS (
                SELECT 1 FROM poles p 
                WHERE ST_DWithin(p.location::geography, d.location::geography, 10.0::float8)
            )
            ;
            """
            
            session.exec(text(query_new), params=params)
            session.commit()
            
            logger.info("✅ Fusion Complete.")
            
        except Exception as e:
            logger.error(f"Fusion failed: {e}")
            session.rollback()

if __name__ == "__main__":
    run_fusion_service()
