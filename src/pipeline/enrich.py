
import logging
from sqlmodel import Session, select
from database import engine
from models import Detection
from src.fusion.context_filters import annotate_with_dsm, annotate_with_roads
import pandas as pd
from shapely import wkb
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_enrichment_service(batch_size: int = 500):
    logger.info("Starting enrichment service...")
    with Session(engine) as session:
        # Get pending detections (those without height or road_dist)
        detections = session.exec(select(Detection).where(Detection.height_ag_m == None).limit(batch_size)).all()
        
        if not detections:
             logger.info("No pending detections for enrichment.")
             return

        logger.info(f"Enriching {len(detections)} detections...")

        # Convert to DataFrame for bulk processing logic
        data = []
        for d in detections:
            # location is WKBElement
            point = wkb.loads(bytes(d.location.data))
            data.append({
                "id": d.id,
                "lat": point.y,
                "lon": point.x,
                "height_ag_m": None,
                "road_distance_m": None
            })
        
        df = pd.DataFrame(data)
        
        # 1. Enrich with Roads
        # Uses context_filters logic which expects 'lat', 'lon'
        # ensure it finds the roads file
        df = annotate_with_roads(df)
        
        # 2. Enrich with DSM
        df = annotate_with_dsm(df)
        
        # 3. Update DB
        updates = 0
        for _, row in df.iterrows():
            det_id = row['id']
            # Find obj in session
            try:
                det = next(d for d in detections if d.id == det_id)
                
                # Handle NA/NaN values
                rd = row.get('road_distance_m')
                hag = row.get('height_ag_m')
                
                det.road_distance_m = float(rd) if pd.notna(rd) else None
                det.height_ag_m = float(hag) if pd.notna(hag) else None
                
                session.add(det)
                updates += 1
            except StopIteration:
                continue
        
        session.commit()
        logger.info(f"✅ Enriched {updates} detections.")

if __name__ == "__main__":
    run_enrichment_service()
