
import logging
import sys
import pandas as pd
from pathlib import Path

# Add src to path
PROJECT_ROOT = Path("/workspace")
sys.path.append(str(PROJECT_ROOT))

# Config imports
from src.config import PROCESSED_DATA_DIR
from src.fusion.context_filters import annotate_with_water

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestWaterFilter")

def test_water_filter():
    logger.info("🧪 Testing Water Filter Logic...")
    
    water_file = PROCESSED_DATA_DIR / "water_osm.geojson"
    if not water_file.exists():
        logger.error(f"❌ Water file missing: {water_file}")
        sys.exit(1)
        
    logger.info(f"Using water file: {water_file}")
    
    # Test Points
    # 1. Susquehanna River (Approx Middle) -> Should be TRUE
    # 2. Downtown Harrisburg (Dry) -> Should be FALSE
    
    test_data = [
        {"lat": 40.255, "lon": -76.890, "desc": "Susquehanna River (Middle)"}, 
        {"lat": 40.260, "lon": -76.880, "desc": "City Island (Dry Land or Edge)"}, 
        {"lat": 40.266, "lon": -76.884, "desc": "River Channel"},
        {"lat": 40.260, "lon": -76.870, "desc": "Harrisburg City (Dry)"} 
    ]
    
    df = pd.DataFrame(test_data)
    
    # Run Filter
    result_df = annotate_with_water(df)
    
    # Check
    print("\nResults:")
    print(result_df[["desc", "lat", "lon", "in_water"]])
    
    # Assertions
    susquehanna = result_df[result_df["desc"] == "Susquehanna River (Middle)"].iloc[0]
    dry_city = result_df[result_df["desc"] == "Harrisburg City (Dry)"].iloc[0]
    
    if susquehanna["in_water"]:
        logger.info("✅ River point correctly identified as WATER.")
    else:
        logger.error("❌ River point FAILED (marked as dry).")

    if not dry_city["in_water"]:
        logger.info("✅ City point correctly identified as DRY.")
    else:
        logger.error("❌ City point FAILED (marked as water).")

if __name__ == "__main__":
    test_water_filter()
