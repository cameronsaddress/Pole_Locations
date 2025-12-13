import sys
from pathlib import Path
import csv
import pandas as pd
from shapely.geometry import Point
from sqlmodel import Session, select
from geoalchemy2.shape import from_shape

# Add backend source to path
BACKEND_SRC = Path(__file__).parent.parent.parent / 'backend-enterprise' / 'src'
sys.path.append(str(BACKEND_SRC))

from database import engine, init_db
from models import Pole

def load_osm_data():
    print("Initializing Database...")
    init_db()
    
    csv_path = Path("data/raw/osm_poles_harrisburg_real.csv") 
    # Also check processed for the "verified" ones if we want to migrate state
    # But for a clean rebuild, let's load Raw OSM first, or the "verified" if it exists.
    
    # Actually, the user wants "Best in Class".
    # The best source right now is our "verified_poles_multi_source.csv" because it has the fusion results.
    input_path = Path("data/processed/verified_poles_multi_source.csv")
    
    if not input_path.exists():
        print(f"Verified Poles not found at {input_path}, falling back to OSM Raw.")
        input_path = csv_path

    print(f"Loading data from {input_path}...")
    df = pd.read_csv(input_path)
    
    # Count before
    print(f"Found {len(df)} rows.")

    session = Session(engine)
    count = 0
    
    try:
        for idx, row in df.iterrows():
            # Handle Schema Drift Logic HERE (The Adapter Pattern)
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
            
            # Check if exists
            existing_pole = session.exec(select(Pole).where(Pole.pole_id == str(pid))).first()
            
            if existing_pole:
                # Update
                existing_pole.status = status
                existing_pole.location = from_shape(pt, srid=4326)
                existing_pole.tags = {"source": "migration_script", "original_row": idx, "update": True}
                session.add(existing_pole)
            else:
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
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    load_osm_data()
