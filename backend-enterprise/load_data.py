import sys
from pathlib import Path
import csv
import pandas as pd
from shapely.geometry import Point
from sqlmodel import Session, select, text
from geoalchemy2.shape import from_shape

# Since this runs inside backend-enterprise/src (or is called as module), 
# and WORKDIR is /app (backend-enterprise)
# we can import directly if we run as `python src/load_data.py` from /app

from database import engine, init_db
from models import Pole

def load_osm_data():
    print("Initializing Database...")
    init_db()
    
    # Data is mounted at /data in the container
    csv_path = Path("/data/raw/osm_poles_harrisburg_real.csv") 
    input_path = Path("/data/processed/verified_poles_multi_source.csv")
    
    if not input_path.exists():
        print(f"Verified Poles not found at {input_path}, checking raw...")
        if not csv_path.exists():
            print(f"❌ No data found at {input_path} or {csv_path}")
            return
        input_path = csv_path
    
    print(f"Loading data from {input_path}...")
    df = pd.read_csv(input_path)
    
    # Count before
    print(f"Found {len(df)} rows.")

    # Deduplicate on pole_id
    if "pole_id" in df.columns:
        df = df.drop_duplicates(subset=["pole_id"])
        print(f"Deduplicated to {len(df)} rows.")
    
    # Also clean existing data?
    # Better to truncate to ensure clean slate for migration
    with Session(engine) as session:
        session.exec(text("TRUNCATE TABLE poles CASCADE"))
        session.commit()
        print("Truncated validation table.")

    with Session(engine) as session:
        count = 0
        
        for idx, row in df.iterrows():
            # Schema Drift Logic
            lat = row.get("lat") or row.get("detection_lat") or row.get("historical_lat")
            lon = row.get("lon") or row.get("detection_lon") or row.get("historical_lon")
            
            if pd.isna(lat) or pd.isna(lon) or lat == 0 or lon == 0:
                continue

            # ID Logic
            pid = row.get("pole_id")
            if pd.isna(pid):
                pid = f"UNK_{idx}"
            
            # Status Logic
            raw_status = row.get("classification", "Review")
            if raw_status == "verified_good":
                status = "Verified"
            elif raw_status == "moved_pole":
                status = "Critical"
            elif raw_status == "new_detection":
                status = "Flagged"
            else:
                status = "Review"

            # Create Point
            pt = Point(float(lon), float(lat))
            
            # Create Model
            pole = Pole(
                pole_id=str(pid),
                status=status,
                financial_impact=0.0,
                height_ag_m=float(row.get("height_ag_m", 0)) if pd.notna(row.get("height_ag_m")) else None,
                location=from_shape(pt, srid=4326),
                tags={"source": "migration_script", "original_row": idx}
            )
            
            session.add(pole)
            count += 1
            if count % 1000 == 0:
                print(f"Staged {count} poles...")
        
        print("Committing to PostGIS...")
        session.commit()
        print(f"✅ Successfully migrated {count} poles to PostGIS.")

if __name__ == "__main__":
    load_osm_data()
