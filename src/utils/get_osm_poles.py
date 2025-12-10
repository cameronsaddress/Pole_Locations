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
        # Define Bounding Boxes for Target Counties (min_lat, min_lon, max_lat, max_lon)
        # Dauphin, York, Cumberland, Adams, Lebanon
        regions = {
            "Dauphin": (40.12, -77.05, 40.67, -76.55),
            "York": (39.71, -77.10, 40.23, -76.45),
            "Cumberland": (40.0, -77.60, 40.35, -76.85),
            "Adams": (39.72, -77.47, 40.0, -77.06),
            "Lebanon": (40.23, -76.65, 40.58, -76.28)
        }

        all_gdf = []

        for county, (min_lat, min_lon, max_lat, max_lon) in regions.items():
            logger.info(f"Querying OSM for {county} ({min_lat}, {min_lon})...")
            
            # Use box instead of point
            tags = {'power': ['pole', 'tower', 'portal', 'catenary_mast']}
            try:
                # OX expects (north, south, east, west)
                gdf_chunk = ox.geometries_from_bbox(max_lat, min_lat, max_lon, min_lon, tags=tags)
                if not gdf_chunk.empty:
                    gdf_chunk['county_ref'] = county
                    all_gdf.append(gdf_chunk)
                    logger.info(f"  ✓ Found {len(gdf_chunk)} poles in {county}")
            except Exception as e:
                logger.warning(f"  ⚠ Failed to download {county}: {e}")

        if not all_gdf:
            logger.error("No poles found in any region!")
            return None
            
        gdf = pd.concat(all_gdf)

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
