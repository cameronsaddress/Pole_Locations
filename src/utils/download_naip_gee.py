"""
Download REAL NAIP imagery using Google Earth Engine
NOW AUTHENTICATED - Ready to download actual satellite imagery
"""
import ee
import urllib.request
import rasterio
from pathlib import Path
import logging
import sys
import time
import math
import json

import pandas as pd

sys.path.append(str(Path(__file__).parent.parent))
from config import IMAGERY_DIR, PROCESSED_DATA_DIR, RAW_DATA_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _load_harrisburg_aoi(
    poles_csv: Path,
    margin_meters: float = 1000.0
):
    """
    Derive an area-of-interest rectangle from the real pole inventory.

    Args:
        poles_csv: Path to the OSM pole inventory CSV.
        margin_meters: Buffer to expand the bounding box on each side.

    Returns:
        Tuple (west, south, east, north) suitable for Earth Engine rectangle.
    """
    if not poles_csv.exists():
        raise FileNotFoundError(
            f"Pole inventory not found at {poles_csv}. "
            "Run src/utils/get_osm_poles.py first."
        )

    df = pd.read_csv(poles_csv, usecols=['lat', 'lon'])
    if df.empty:
        raise ValueError(f"No coordinates found in {poles_csv}")

    min_lat = df['lat'].min()
    max_lat = df['lat'].max()
    min_lon = df['lon'].min()
    max_lon = df['lon'].max()
    mean_lat = df['lat'].mean()

    # Convert buffer to degrees (approximation sufficient for AOI padding)
    lat_margin_deg = margin_meters / 111_000.0
    lon_margin_deg = margin_meters / (111_000.0 * math.cos(math.radians(mean_lat)))

    south = min_lat - lat_margin_deg
    north = max_lat + lat_margin_deg
    west = min_lon - lon_margin_deg
    east = max_lon + lon_margin_deg

    return west, south, east, north


def download_real_naip_imagery():
    """
    Download REAL NAIP imagery for 5 square miles in Pennsylvania
    Uses authenticated Google Earth Engine
    """
    logger.info("=" * 80)
    logger.info("DOWNLOADING REAL NAIP IMAGERY - GOOGLE EARTH ENGINE")
    logger.info("=" * 80)
    logger.info("Location: Harrisburg, PA region")
    logger.info("Coverage: 5 square miles")
    logger.info("Resolution: 1 meter per pixel")
    logger.info("Source: USDA NAIP via Google Earth Engine")
    logger.info("")

    try:
        # Initialize Earth Engine (now authenticated)
        logger.info("Initializing Google Earth Engine...")
        ee.Initialize(project='ee-cameronanderson')  # Use authenticated project
        logger.info("✓ Successfully authenticated!")

        poles_csv = RAW_DATA_DIR / 'osm_poles_harrisburg_real.csv'
        west, south, east, north = _load_harrisburg_aoi(poles_csv, margin_meters=1500)
        aoi = ee.Geometry.Rectangle([west, south, east, north])

        logger.info(f"Area of Interest: {aoi.bounds().getInfo()}")

        # Search for NAIP imagery
        logger.info("\nSearching for NAIP imagery...")
        naip_collection = ee.ImageCollection('USDA/NAIP/DOQQ') \
            .filterBounds(aoi) \
            .filterDate('2018-01-01', '2024-01-01') \
            .sort('system:time_start', False)

        count = naip_collection.size().getInfo()
        logger.info(f"✓ Found {count} NAIP images")

        if count == 0:
            logger.error("No NAIP imagery available for this area!")
            return []

        # Get the most recent image
        naip_image = naip_collection.first()
        image_date = ee.Date(naip_image.get('system:time_start')).format('YYYY-MM-dd').getInfo()

        logger.info(f"✓ Selected image from: {image_date}")
        logger.info(f"  Image ID: {naip_image.get('system:index').getInfo()}")

        # Download the image in tiles (Earth Engine has size limits)
        logger.info("\nDownloading NAIP imagery...")
        logger.info("This may take 2-5 minutes for high-resolution data...")

        # Select RGB bands
        rgb_image = naip_image.select(['R', 'G', 'B'])

        # Get download URL
        url = rgb_image.getDownloadURL({
            'region': aoi.getInfo()['coordinates'],
            'scale': 1,  # 1 meter resolution
            'format': 'GEO_TIFF',
            'crs': 'EPSG:4326',
            'maxPixels': int(1e9)
        })

        logger.info(f"✓ Generated download URL")

        # Download the file
        output_path = IMAGERY_DIR / f'naip_harrisburg_pa_{image_date}.tif'

        logger.info(f"Downloading to: {output_path}")
        urllib.request.urlretrieve(url, output_path)

        # Verify the downloaded image
        with rasterio.open(output_path) as src:
            logger.info("\n" + "=" * 80)
            logger.info("DOWNLOAD COMPLETE - REAL NAIP IMAGERY")
            logger.info("=" * 80)
            logger.info(f"✓ File: {output_path.name}")
            logger.info(f"✓ Size: {output_path.stat().st_size / 1024 / 1024:.1f} MB")
            logger.info(f"✓ Dimensions: {src.width} x {src.height} pixels")
            logger.info(f"✓ Bounds: {src.bounds}")
            logger.info(f"✓ CRS: {src.crs}")
            logger.info(f"✓ Resolution: {src.res[0]:.3f}m x {src.res[1]:.3f}m")
            logger.info(f"✓ Bands: {src.count} (RGB)")
            logger.info(f"✓ Data type: {src.dtypes[0]}")
            logger.info("")

            # Calculate coverage
            # Bounds are in EPSG:4326 since we requested CRS=4326
            lat_extent = src.bounds.top - src.bounds.bottom
            lon_extent = src.bounds.right - src.bounds.left
            mean_lat = (src.bounds.top + src.bounds.bottom) / 2
            meters_per_degree_lat = 111_000.0
            meters_per_degree_lon = 111_000.0 * math.cos(math.radians(mean_lat))
            area_m2 = abs(lat_extent * meters_per_degree_lat) * abs(lon_extent * meters_per_degree_lon)
            area_sq_miles = area_m2 / 2_589_988.11  # Convert to square miles
            logger.info(f"✓ Coverage: {area_sq_miles:.2f} square miles (~{area_m2/1e6:.1f} km²)")

            metadata = {
                "downloaded_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                "aoi_bounds": {
                    "west": west,
                    "south": south,
                    "east": east,
                    "north": north
                },
                "mean_latitude": mean_lat,
                "resolution_meters": src.res[0],
                "pixels": {
                    "width": src.width,
                    "height": src.height
                },
                "coverage_sq_miles": area_sq_miles,
                "imagery_source": "USDA/NAIP/DOQQ",
                "image_date": image_date
            }
            metadata_path = IMAGERY_DIR / f'naip_harrisburg_pa_{image_date}.metadata.json'
            metadata_path.write_text(json.dumps(metadata, indent=2))
            logger.info(f"✓ Metadata saved: {metadata_path.name}")

        logger.info("\n🎯 Next Steps:")
        logger.info("  1. Extract pole locations from imagery")
        logger.info("  2. Create training dataset from real poles")
        logger.info("  3. Train YOLOv8 model")

        return [output_path]

    except Exception as e:
        logger.error(f"Download failed: {e}")
        logger.error(f"Error type: {type(e).__name__}")

        if "project" in str(e).lower():
            logger.info("\nTrying without project specification...")
            try:
                ee.Initialize()
                return download_real_naip_imagery()  # Retry
            except:
                pass

        logger.info("\nAlternative: Download manually")
        logger.info("1. Visit: https://code.earthengine.google.com")
        logger.info("2. Paste this code:")
        logger.info("""
var aoi = ee.Geometry.Rectangle([-76.9037, 40.2372, -76.8697, 40.3092]);
var naip = ee.ImageCollection('USDA/NAIP/DOQQ')
  .filterBounds(aoi)
  .filterDate('2018-01-01', '2024-01-01')
  .sort('system:time_start', false)
  .first();

Export.image.toDrive({
  image: naip.select(['R', 'G', 'B']),
  description: 'naip_harrisburg_pa',
  scale: 1,
  region: aoi,
  maxPixels: 1e9
});
        """)
        logger.info("3. Run script and download from Google Drive")

        return []


if __name__ == "__main__":
    tiles = download_real_naip_imagery()

    if tiles:
        logger.info("\n✅ SUCCESS: REAL satellite imagery downloaded!")
        logger.info("Ready for pole detection training!")
    else:
        logger.error("\n❌ Download failed - see instructions above")
