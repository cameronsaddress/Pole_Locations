
import logging
import json
import requests
from pathlib import Path
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
import geopandas as gpd
import pandas as pd
import sys

# Add src to path
PROJECT_ROOT = Path("/workspace")
sys.path.append(str(PROJECT_ROOT))

# Config imports
from src.config import PROCESSED_DATA_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WaterFetcher")

# Tri-County BBOX (Cumberland, Dauphin, York) + Buffer
# Min/Max Lat/Lon covering the region
BBOX = (-77.7, 39.7, -76.2, 40.7)  # (min_lon, min_lat, max_lon, max_lat)

def fetch_osm_water():
    """
    Fetches water polygons from Overpass API for the PA Tri-County region.
    Saves directly to 'data/processed/water_osm.geojson'.
    """
    output_path = PROCESSED_DATA_DIR / "water_osm.geojson"
    
    logger.info(f"🌊 Fetching Water Bodies for Regional BBOX: {BBOX}")
    
    overpass_url = "http://overpass-api.de/api/interpreter"
    
    # Overpass QL
    # Recursive fetch to get all ways constituting the water bodies
    query = f"""
    [out:json][timeout:180][bbox:{BBOX[1]},{BBOX[0]},{BBOX[3]},{BBOX[2]}];
    (
      way["natural"="water"];
      way["waterway"="riverbank"];
      way["water"="lake"];
      way["water"="river"];
      relation["natural"="water"];
      relation["waterway"="riverbank"];
      relation["water"="lake"];
      relation["water"="river"];
    );
    /* Recurse down to get geometry (ways and nodes) */
    (._;>;);
    /* Filter to just ways */
    way._;
    out geom;
    """
    
    logger.info("Sending query to Overpass API (this may take 30-60s)...")
    try:
        response = requests.get(overpass_url, params={'data': query})
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.error(f"❌ Failed to fetch OSM data: {e}")
        return

    logger.info(f"Received {len(data.get('elements', []))} elements. Processing...")

    # Convert to GeoJSON
    features = []
    
    for element in data['elements']:
        geom = None
        
        # Simple Way
        if element['type'] == 'way':
            coords = element.get('geometry', [])
            if len(coords) < 3: continue
            geom = {
                "type": "Polygon",
                "coordinates": [[ [pt['lon'], pt['lat']] for pt in coords ]]
            }
            
        # Relation (Multipolygon) - Overpass returns 'members' with geometry if 'out geom' used?
        # Actually 'out geom' on relations returns members with geometry.
        # Handling complex multipolygons nicely without osmnx is hard.
        # Quick hack: If we have 'out geom', relation members have geometry.
        # But simpler: just use the ways. Most broad rivers are ways or collections of ways.
        # For a truly robust Enterprise system we should use osmnx if available, or just filtering.
        
        if geom:
            features.append({
                "type": "Feature",
                "properties": element.get("tags", {}),
                "geometry": geom
            })

    if not features:
        logger.warning("No water features found!")
        return

    # Create GeoDataFrame
    fc = {
        "type": "FeatureCollection",
        "features": features
    }
    
    gdf = gpd.GeoDataFrame.from_features(fc, crs="EPSG:4326")
    
    logger.info(f"Found {len(gdf)} water polygons. Cleaning geometries...")
    
    # Fix topology errors (self-intersections)
    gdf['geometry'] = gdf.geometry.buffer(0)
    
    # Remove empty/invalid
    gdf = gdf[gdf.geometry.is_valid]
    gdf = gdf[~gdf.geometry.is_empty]
    
    logger.info(f"Valid polygons after cleaning: {len(gdf)}")
    
    logger.info(f"💾 Saving to {output_path}...")
    gdf.to_file(output_path, driver="GeoJSON")
    logger.info("✅ Water body database updated.")

if __name__ == "__main__":
    fetch_osm_water()
