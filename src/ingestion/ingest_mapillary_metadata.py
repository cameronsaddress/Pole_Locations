
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
        "limit": 2000 # Max allowed by API per page
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
        if next_link and len(images) < 2000000: # Cap at 2M
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

def subdivide_bbox(bbox, step=0.08): # Slightly less than 0.1 to be safe
    """Generator to yield smaller bboxes from a large one."""
    min_x, min_y, max_x, max_y = bbox
    
    curr_x = min_x
    while curr_x < max_x:
        curr_y = min_y
        while curr_y < max_y:
            next_x = min(curr_x + step, max_x)
            next_y = min(curr_y + step, max_y)
            yield [curr_x, curr_y, next_x, next_y]
            curr_y += step
        curr_x += step

def main():
    logger.info("Starting Mass Mapillary Ingest for PA Pilot Counties...")
    
    total = 0
    for name, bbox in COUNTIES.items():
        logger.info(f"Fetching {name} County (Subdividing Grid)...")
        
        county_total = 0
        for sub_bbox in subdivide_bbox(bbox):
             imgs = fetch_images_in_bbox(sub_bbox, limit=2000000)
             if imgs:
                 ingest_metadata(imgs)
                 county_total += len(imgs)
                 
        logger.info(f"  Processed {name}: {county_total} total images.")
        total += county_total
        
    logger.info(f"Done. Total Network Size: {total} images.")

if __name__ == "__main__":
    main()
