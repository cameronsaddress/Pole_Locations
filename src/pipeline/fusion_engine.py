
import logging
from sqlmodel import Session, text
from database import engine
from src.config import (
    FUSION_UPDATE_CONFIDENCE_THRESHOLD,
    FUSION_NEW_FLAGGED_CONFIDENCE_THRESHOLD,
    FUSION_AUTO_VERIFY_CONFIDENCE_THRESHOLD,
    FUSION_NEW_FLAGGED_MAX_ROAD_DIST_M,
    FINANCIAL_IMPACT_DAMAGE,
    FINANCIAL_IMPACT_LEANING,
    FINANCIAL_IMPACT_VEGETATION
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FusionEngine:
    """
    Unified engine for fusing raw detections into the authoritative 'poles' table.
    Usage:
        engine = FusionEngine()
        engine.run_fusion() 
    """

    def __init__(self):
        self.params = {
            "damage_cost": FINANCIAL_IMPACT_DAMAGE,
            "leaning_cost": FINANCIAL_IMPACT_LEANING,
            "veg_cost": FINANCIAL_IMPACT_VEGETATION,
            "update_conf": FUSION_UPDATE_CONFIDENCE_THRESHOLD,
            "new_conf": FUSION_NEW_FLAGGED_CONFIDENCE_THRESHOLD,
            "auto_verify_conf": FUSION_AUTO_VERIFY_CONFIDENCE_THRESHOLD,
            "max_road_dist": FUSION_NEW_FLAGGED_MAX_ROAD_DIST_M,
            "pat_damage": "%damage%",
            "pat_leaning": "%leaning%",
            "pat_veg": "%vegetation%"
        }

    def run_fusion(self, session: Session = None, run_id: str = None):
        """
        Executes the SQL fusion logic. 
        If session provided, uses it (and does NOT commit).
        If no session, creates a new one and commits.
        
        Args:
            session: Existing DB session
            run_id: Optimization - only fuse detections from this specific run/tile.
        """
        if session:
            self._execute_fusion(session, run_id)
        else:
            with Session(engine) as session:
                self._execute_fusion(session, run_id)
                session.commit()

    def _execute_fusion(self, session: Session, run_id: str = None):
        logger.info(f"Executing Enterprise Fusion Logic (Run ID: {run_id or 'ALL'})...")
        
        # Prepare params
        fusion_params = self.params.copy()
        if run_id:
            fusion_params["run_id"] = run_id
            
        # Base WHERE clause fragment
        run_filter = "AND d.run_id = :run_id" if run_id else ""

        # 1. Update Existing Poles
        # Logic: If we see a pole within 10m of an existing verified pole, update its status 
        # if the new detection is high confidence.
        query_update = f"""
        UPDATE poles p
        SET last_verified_at = now(),
            status = CASE 
                WHEN d.class_name LIKE :pat_damage THEN 'Critical'
                WHEN d.class_name LIKE :pat_leaning THEN 'Critical'
                WHEN d.class_name LIKE :pat_veg THEN 'Review'
                ELSE 'Verified' 
            END,
            financial_impact = CASE 
                WHEN d.class_name LIKE :pat_damage THEN :damage_cost
                WHEN d.class_name LIKE :pat_leaning THEN :leaning_cost
                WHEN d.class_name LIKE :pat_veg THEN :veg_cost
                ELSE 0.0
            END,
            tags = p.tags || jsonb_build_object('last_detection_source', 'AI', 'last_conf', d.confidence)
        FROM detections d
        WHERE ST_DWithin(p.location::geography, d.location::geography, 10.0::float8)
        AND d.confidence > :update_conf
        {run_filter};
        """
        
        session.connection().execute(text(query_update), fusion_params)

        # 2. Insert New Poles
        # Logic: If we see a high-confidence pole that is NOT near an existing pole, create it.
        # Now supports AUTO-VERIFICATION for very high confidence.
        query_new = f"""
        INSERT INTO poles (id, pole_id, location, status, last_verified_at, tags, financial_impact)
        SELECT 
            gen_random_uuid(), 
            'AI_NEW_' || to_char(now(), 'YYYYMMDD_HH24MISS') || '_' || substr(md5(random()::text), 1, 6), 
            d.location, 
            CASE 
                WHEN d.class_name LIKE :pat_damage THEN 'Critical'
                WHEN d.class_name LIKE :pat_leaning THEN 'Critical'
                WHEN d.confidence >= :auto_verify_conf THEN 'Verified'
                ELSE 'Flagged'
            END, 
            now(), 
            d.tags || jsonb_build_object('source', 'AI_Discovery', 'initial_conf', d.confidence),
            CASE 
                WHEN d.class_name LIKE :pat_damage THEN :damage_cost
                WHEN d.class_name LIKE :pat_leaning THEN :leaning_cost
                WHEN d.class_name LIKE :pat_veg THEN :veg_cost
                ELSE 0.0
            END
        FROM detections d
        WHERE d.confidence > :new_conf
        {run_filter}
        -- Context Filtering (Road distance, etc)
        AND (d.road_distance_m IS NULL OR d.road_distance_m < :max_road_dist) 
        -- Deduplication: Do not duplicate existing poles within 10m
        AND NOT EXISTS (
            SELECT 1 FROM poles p 
            WHERE ST_DWithin(p.location::geography, d.location::geography, 10.0::float8)
        );
        """
        
        session.connection().execute(text(query_new), fusion_params)
        logger.info("Fusion logic applied successfully.")
