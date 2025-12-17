
"""
OpenInfraMap / Overpass API Connector.
Fetches high-voltage power lines and towers to define the 'Grid Backbone'.
"""
import requests
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point
import logging
from src.config import DATA_DIR, EAST_COAST_BBOX

logger = logging.getLogger(__name__)

OVERPASS_URL = "http://overpass-api.de/api/interpreter"

def fetch_grid_backbone(bbox=None):
    """
    Query Overpass for 'power=line' (high voltage) and 'power=tower'.
    """
    if bbox is None:
        # Harrisburg BBOX (Target Pilot Area)
        bbox = {
            "minx": -77.05,
            "miny": 40.20,
            "maxx": -76.80,
            "maxy": 40.40
        }
        
    # Overpass QL
    # Fetch high voltage lines and towers
    query = f"""
    [out:json][timeout:60];
    (
      way["power"="line"]({bbox['miny']},{bbox['minx']},{bbox['maxy']},{bbox['maxx']});
      way["power"="minor_line"]({bbox['miny']},{bbox['minx']},{bbox['maxy']},{bbox['maxx']});
      node["power"="tower"]({bbox['miny']},{bbox['minx']},{bbox['maxy']},{bbox['maxx']});
      node["power"="pole"]({bbox['miny']},{bbox['minx']},{bbox['maxy']},{bbox['maxx']});
    );
    /* Recurse down to get geometry */
    (._;>;);
    out geom;
    """
    
    try:
        logger.info("Fetching Grid Backbone from Overpass...")
        response = requests.post(OVERPASS_URL, data={'data': query})
        response.raise_for_status()
        data = response.json()
        
        # Convert to GeoJSON
        features = []
        for element in data['elements']:
            if element['type'] == 'way' and 'geometry' in element:
                coords = [[pt['lon'], pt['lat']] for pt in element['geometry']]
                features.append({
                    "type": "Feature",
                    "properties": element.get("tags", {}),
                    "geometry": { "type": "LineString", "coordinates": coords }
                })
            elif element['type'] == 'node':
                features.append({
                    "type": "Feature",
                    "properties": element.get("tags", {}),
                    "geometry": { "type": "Point", "coordinates": [element['lon'], element['lat']] }
                })

        if not features:
            logger.warning("No grid backbone features found.")
            return False

        fc = {"type": "FeatureCollection", "features": features}
        gdf = gpd.GeoDataFrame.from_features(fc, crs="EPSG:4326")
        
        output_path = DATA_DIR / "processed" / "grid_backbone.geojson"
        gdf.to_file(output_path, driver="GeoJSON")
        logger.info(f"✅ Grid Backbone saved ({len(gdf)} features) to {output_path}")
        
        return True
    except Exception as e:
        logger.error(f"Overpass Query Failed: {e}")
        return False

class GridConnector:
    def __init__(self):
        self.path = DATA_DIR / "processed" / "grid_backbone.geojson"
        self.gdf = None
        if self.path.exists():
            self.gdf = gpd.read_file(self.path)
            
    def get_nearest_powerline_dists(self, lat_lons: list) -> list:
        """
        Returns distance to nearest high-voltage line for a list of points.
        """
        if self.gdf is None or self.gdf.empty:
            return [None] * len(lat_lons)
            
        # Create points GDF
        points = gpd.GeoDataFrame(
            geometry=gpd.points_from_xy([lon for lat, lon in lat_lons], [lat for lat, lon in lat_lons]),
            crs="EPSG:4326"
        )
        
        # Ensure we have metric projection for accurate distance
        if self.gdf.crs.is_geographic:
             try:
                 utm = self.gdf.estimate_utm_crs()
                 grid_metric = self.gdf.to_crs(utm)
             except:
                 # Fallback if global coverage makes estimate ambiguous 
                 grid_metric = self.gdf.to_crs("EPSG:3857")
        else:
             grid_metric = self.gdf
             
        points_metric = points.to_crs(grid_metric.crs)
        
        # Use sindex for fast nearest search
        nearest_idxs = grid_metric.sindex.nearest(
            points_metric.geometry, 
            return_all=False, 
            return_distance=False
        )
        
        # Calculation
        nearest_lines = grid_metric.geometry.iloc[nearest_idxs[1]].reset_index(drop=True)
        input_pts = points_metric.geometry.iloc[nearest_idxs[0]].reset_index(drop=True)
        
        dists = input_pts.distance(nearest_lines)
        
        # Re-align with original index order (nearest_idxs[0] are input indices)
        results = pd.Series(index=points.index, dtype=float)
        results.iloc[nearest_idxs[0]] = dists.values
        
        return results.tolist()

def fetch_osm_poles(bbox, output_path):
    """
    Fetches utility poles from OSM for a given bbox and saves to output_path.
    bbox format: {'minx': float, 'miny': float, 'maxx': float, 'maxy': float}
    """
    query = f"""
    [out:json][timeout:60];
    (
      node["power"="pole"]({bbox['miny']},{bbox['minx']},{bbox['maxy']},{bbox['maxx']});
      node["power"="tower"]({bbox['miny']},{bbox['minx']},{bbox['maxy']},{bbox['maxx']});
    );
    out geom;
    """
    
    try:
        logger.info(f"Fetching OSM Poles for bbox: {bbox}...")
        response = requests.post(OVERPASS_URL, data={'data': query})
        response.raise_for_status()
        data = response.json()
        
        features = []
        for element in data.get('elements', []):
            if element['type'] == 'node':
                features.append({
                    "type": "Feature",
                    "properties": element.get("tags", {"id": str(element['id'])}),
                    "geometry": { "type": "Point", "coordinates": [element['lon'], element['lat']] }
                })
                
        if not features:
            logger.warning(f"No poles found in OSM for this area.")
            return False

        fc = {"type": "FeatureCollection", "features": features}
        gdf = gpd.GeoDataFrame.from_features(fc, crs="EPSG:4326")
        
        # Ensure parent dir exists
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        gdf.to_file(output_path, driver="GeoJSON")
        logger.info(f"✅ Generated Grid File ({len(gdf)} poles) at {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"OSM Fetch Failed: {e}")
        return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fetch_grid_backbone()
