
import os
import requests
import logging
from typing import List, Dict
from sqlmodel import Session, select
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from datetime import datetime
import sys

# Path Setup
sys.path.append("/workspace/backend-enterprise")
from database import engine
from models import StreetViewImage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MapillaryIngest")

MAPILLARY_TOKEN = os.getenv("MAPILLARY_TOKEN")
if not MAPILLARY_TOKEN:
    logger.error("MAPILLARY_TOKEN not found in env!")
    sys.exit(1)

# PA County Bounding Boxes (Approximate)
COUNTIES = {
    "Dauphin":  [-77.0, 40.1, -76.5, 40.6], 
    "York":     [-77.2, 39.7, -76.4, 40.2],
    "Cumberland": [-77.6, 40.0, -76.8, 40.3]
}

def fetch_images_in_bbox(bbox: List[float], limit=2000):
    """Fetch image metadata from Mapillary API."""
    url = "https://graph.mapillary.com/images"
    params = {
        "access_token": MAPILLARY_TOKEN,
        "fields": "id,geometry,compass_angle,captured_at,sequence",
        "bbox": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
        "limit": limit
    }
    
    images = []
    while True:
        resp = requests.get(url, params=params)
        if resp.status_code != 200:
            logger.error(f"API Error: {resp.text}")
            break
            
        data = resp.json()
        images.extend(data.get('data', []))
        
        # Pagination
        if len(images) >= limit:
            break
            
        # Check next page logic if needed, but for "all available" we might need proper paging
        # Mapillary paging uses 'paging.next' link
        next_link = data.get('paging', {}).get('next')
        if next_link and len(images) < 10000: # Safety cap
            url = next_link
            params = {} # Params are in the link
        else:
            break
            
    return images

def ingest_metadata(images: List[Dict]):
    with Session(engine) as session:
        added = 0
        for img in images:
            key = img.get('id')
            
            # Check existence
            existing = session.exec(select(StreetViewImage).where(StreetViewImage.image_key == key)).first()
            if existing:
                continue
                
            coords = img['geometry']['coordinates'] # Lon, Lat
            
            # Parse time
            captured = None
            if 'captured_at' in img:
                try:
                    captured = datetime.fromtimestamp(img['captured_at'] / 1000.0)
                except: pass

            record = StreetViewImage(
                provider="Mapillary",
                image_key=key,
                location=from_shape(Point(coords[0], coords[1]), srid=4326),
                heading=float(img.get('compass_angle', 0.0)),
                captured_at=captured
            )
            session.add(record)
            added += 1
            
        session.commit()
        logger.info(f"Committed {added} new street view records.")

def main():
    logger.info("Starting Mass Mapillary Ingest for PA Pilot Counties...")
    
    total = 0
    for name, bbox in COUNTIES.items():
        logger.info(f"Fetching {name} County...")
        imgs = fetch_images_in_bbox(bbox, limit=5000) # Fetch 5000 per county for pilot
        logger.info(f"  Found {len(imgs)} images.")
        ingest_metadata(imgs)
        total += len(imgs)
        
    logger.info(f"Done. Total Network Size: {total} images.")

if __name__ == "__main__":
    main()
