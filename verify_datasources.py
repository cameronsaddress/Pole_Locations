
"""
Data Source Verification Script
Tests that all newly integrated connectors (FAA, OpenInfraMap, Mapillary, PASDA, Lidar)
can be imported and instantiated correctly.
"""
import sys
import logging
from pathlib import Path

# Fix path to include project root
sys.path.append(str(Path(__file__).parent))

from src.ingestion.connectors.faa_obstacles import FAAConnector
from src.ingestion.connectors.openinframap import GridConnector
from src.ingestion.connectors.pasda_roads import PASDAConnector
from src.ingestion.connectors.mapillary import MapillaryClient
from src.ingestion.connectors.usgs_lidar import LidarProbe

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DataSourceVerifier")

def verify_connectors():
    logger.info("--- Starting Connector Verification ---")
    
    # 1. FAA
    try:
        faa = FAAConnector()
        logger.info("✅ FAA Connector: Instantiated")
    except Exception as e:
        logger.error(f"❌ FAA Connector Failed: {e}")

    # 2. OpenInfraMap
    try:
        grid = GridConnector()
        logger.info("✅ OpenInfraMap Connector: Instantiated")
    except Exception as e:
        logger.error(f"❌ OpenInfraMap Connector Failed: {e}")

    # 3. PASDA
    try:
        pasda = PASDAConnector()
        logger.info("✅ PASDA Connector: Instantiated")
    except Exception as e:
        logger.error(f"❌ PASDA Connector Failed: {e}")

    # 4. Mapillary
    try:
        mapillary = MapillaryClient(api_key="TEST_KEY")
        logger.info("✅ Mapillary Connector: Instantiated (Test Key)")
    except Exception as e:
        logger.error(f"❌ Mapillary Connector Failed: {e}")

    # 5. Lidar
    try:
        lidar = LidarProbe(laz_dir=Path("./data"))
        logger.info(f"✅ Lidar Connector: Instantiated (Enabled: {lidar.enabled})")
    except Exception as e:
        logger.error(f"❌ Lidar Connector Failed: {e}")
        
    logger.info("--- Verification Complete ---")

if __name__ == "__main__":
    verify_connectors()
