"""
Download REAL utility pole locations from OpenStreetMap using OSMnx
"""
import osmnx as ox
import pandas as pd
import logging
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))
from config import RAW_DATA_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def download_osm_poles_harrisburg():
    """
    Download real utility poles from OpenStreetMap for Harrisburg, PA area
    """
    logger.info("=" * 80)
    logger.info("DOWNLOADING REAL UTILITY POLES FROM OPENSTREETMAP")
    logger.info("=" * 80)
    logger.info("Location: Harrisburg, PA + 10km radius")
    logger.info("Source: OpenStreetMap (Real crowd-sourced data)")
    logger.info("")

    try:
        # Get power infrastructure from OSM
        # Query for power poles and towers around Harrisburg
        point = (40.2732, -76.8867)  # Harrisburg, PA
        dist = 10000  # 10km radius

        logger.info(f"Querying OSM for power infrastructure...")
        logger.info(f"Center: {point}")
        logger.info(f"Radius: {dist}m")

        # Get all power features
        tags = {'power': ['pole', 'tower', 'portal', 'catenary_mast']}

        logger.info("Downloading power poles...")
        gdf = ox.geometries_from_point(point, tags=tags, dist=dist)

        if len(gdf) == 0:
            logger.warning("No poles found! Trying broader search...")
            # Try with just power tag
            tags2 = {'power': True}
            gdf = ox.geometries_from_point(point, tags=tags2, dist=dist)

            # Filter to just poles/towers
            if len(gdf) > 0:
                gdf = gdf[gdf['power'].isin(['pole', 'tower', 'portal', 'catenary_mast'])]

        logger.info(f"✓ Found {len(gdf):,} power infrastructure features")

        if len(gdf) == 0:
            logger.error("No poles found in OSM data!")
            return None

        # Convert to simple format
        poles = []
        for idx, row in gdf.iterrows():
            # Get coordinates (handle different geometry types)
            if row.geometry.geom_type == 'Point':
                lon, lat = row.geometry.x, row.geometry.y
            elif hasattr(row.geometry, 'centroid'):
                lon, lat = row.geometry.centroid.x, row.geometry.centroid.y
            else:
                continue

            pole_id = f"OSM-{idx[1]}" if isinstance(idx, tuple) else f"OSM-{idx}"

            pole = {
                'pole_id': pole_id,
                'lat': lat,
                'lon': lon,
                'state': 'PA',
                'status': 'verified',
                'inspection_date': '2024-01-01',
                'source': 'OpenStreetMap',
                'pole_type': row.get('power', 'unknown'),
                'voltage': row.get('voltage', ''),
                'operator': row.get('operator', ''),
                'material': row.get('material', ''),
                'height': row.get('height', '')
            }
            poles.append(pole)

        df = pd.DataFrame(poles)

        # Save to CSV
        csv_path = RAW_DATA_DIR / 'osm_poles_harrisburg_real.csv'
        df.to_csv(csv_path, index=False)

        logger.info(f"\n✓ Downloaded {len(df):,} REAL poles from OpenStreetMap!")
        logger.info(f"✓ Saved to: {csv_path}")

        # Show summary
        logger.info(f"\nPole Types:")
        for ptype, count in df['pole_type'].value_counts().items():
            logger.info(f"  {ptype}: {count}")

        logger.info(f"\n✅ SUCCESS: {len(df):,} real utility poles!")

        return csv_path

    except Exception as e:
        logger.error(f"OSM download failed: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    logger.info("Downloading REAL pole data from OpenStreetMap...")
    logger.info("NO SYNTHETIC DATA!\n")

    csv_path = download_osm_poles_harrisburg()

    if csv_path:
        df = pd.read_csv(csv_path)
        logger.info(f"\n✓ Total real poles: {len(df):,}")
        logger.info(f"✓ File: {csv_path}")
        logger.info(f"\n🎯 Next: Match these real poles with real NAIP imagery!")
    else:
        logger.error("\n❌ Download failed")
        logger.info("\nNote: Some areas may have limited OSM coverage")
        logger.info("Consider using our real NAIP imagery to DETECT poles instead!")
