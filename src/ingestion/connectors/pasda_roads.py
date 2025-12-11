
"""
PASDA / PennDOT Road Network Connector.
Fetches official state road centerlines.
"""
import geopandas as gpd
from pathlib import Path
import logging
from src.config import DATA_DIR

logger = logging.getLogger(__name__)

PASDA_ROADS_PATH = DATA_DIR / "processed" / "roads_pasda.geojson"

class PASDAConnector:
    def __init__(self):
        self.gdf = None
        if PASDA_ROADS_PATH.exists():
            self.gdf = gpd.read_file(PASDA_ROADS_PATH)
            
    def get_roads_gdf(self):
        return self.gdf

def ingest_pasda_roads(url: str):
    """
    Downloads shapefile zip from PASDA, converts to optimized GeoJSON.
    """
    # Logic to download, unzip, read via gpd, to_crs(4326), save.
    pass
