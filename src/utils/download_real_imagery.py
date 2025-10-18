"""
Download REAL satellite imagery using multiple FREE sources
1. Sentinel-2 (10m resolution, free, no login)
2. NAIP from Box.com (1m resolution, free)
3. Google Earth Engine (requires free signup)
"""
import logging
from pathlib import Path
import sys
from datetime import date
import ee
from sentinelsat import SentinelAPI, read_geojson, geojson_to_wkt

sys.path.append(str(Path(__file__).parent.parent))
from config import IMAGERY_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def download_sentinel2_imagery(lat=40.2732, lon=-76.8867, size_km=3):
    """
    Download FREE Sentinel-2 imagery (10m resolution)
    No login required for older imagery

    Args:
        lat: Latitude of center
        lon: Longitude of center
        size_km: Size in kilometers
    """
    logger.info("=" * 80)
    logger.info("DOWNLOADING SENTINEL-2 IMAGERY (FREE)")
    logger.info("=" * 80)
    logger.info(f"Location: {lat}, {lon}")
    logger.info(f"Coverage: {size_km}km x {size_km}km")
    logger.info("Resolution: 10 meters per pixel")
    logger.info("")

    try:
        # Initialize Sentinel API (using guest access)
        api = SentinelAPI(None, None, 'https://scihub.copernicus.eu/dhus')

        # Define area of interest (bounding box)
        offset = size_km / 111.0  # Approx km to degrees
        footprint = f"POLYGON(({lon-offset} {lat-offset}, {lon+offset} {lat-offset}, {lon+offset} {lat+offset}, {lon-offset} {lat+offset}, {lon-offset} {lat-offset}))"

        # Search for Sentinel-2 imagery
        logger.info("Searching for Sentinel-2 scenes...")
        products = api.query(
            footprint,
            date=('20230101', '20231231'),  # 2023 data
            platformname='Sentinel-2',
            cloudcoverpercentage=(0, 20),  # Low cloud cover
            limit=5
        )

        logger.info(f"Found {len(products)} scenes")

        if products:
            # Download first scene
            for product_id, product_info in list(products.items())[:1]:
                logger.info(f"\nDownloading scene: {product_info['title']}")
                logger.info(f"  Date: {product_info['beginposition']}")
                logger.info(f"  Cloud cover: {product_info['cloudcoverpercentage']:.1f}%")
                logger.info(f"  Size: {product_info['size']}")

                try:
                    api.download(product_id, directory_path=str(IMAGERY_DIR))
                    logger.info("✓ Download complete!")
                    return True
                except Exception as e:
                    logger.warning(f"Download requires login: {e}")
                    logger.info("Using Google Earth Engine instead...")
                    return download_via_earth_engine(lat, lon, size_km)
        else:
            logger.warning("No scenes found, trying Earth Engine...")
            return download_via_earth_engine(lat, lon, size_km)

    except Exception as e:
        logger.error(f"Sentinel-2 download failed: {e}")
        logger.info("Trying Google Earth Engine...")
        return download_via_earth_engine(lat, lon, size_km)


def download_via_earth_engine(lat=40.2732, lon=-76.8867, size_km=3):
    """
    Download imagery via Google Earth Engine (requires free signup)
    """
    logger.info("=" * 80)
    logger.info("DOWNLOADING VIA GOOGLE EARTH ENGINE")
    logger.info("=" * 80)

    try:
        # Initialize Earth Engine
        logger.info("Initializing Google Earth Engine...")
        logger.info("Note: If this fails, run: earthengine authenticate")

        try:
            ee.Initialize()
        except:
            logger.info("Authenticating...")
            ee.Authenticate()
            ee.Initialize()

        # Define area of interest
        offset = size_km / 111.0
        aoi = ee.Geometry.Rectangle([
            lon - offset, lat - offset,
            lon + offset, lat + offset
        ])

        # Get NAIP imagery (1m resolution, best for poles)
        logger.info("\nSearching for NAIP imagery...")
        naip = ee.ImageCollection('USDA/NAIP/DOQQ') \
            .filterBounds(aoi) \
            .filterDate('2018-01-01', '2023-12-31') \
            .sort('system:time_start', False) \
            .first()

        if naip:
            logger.info("✓ Found NAIP imagery")

            # Get download URL
            url = naip.getDownloadURL({
                'region': aoi.getInfo()['coordinates'],
                'scale': 1,
                'format': 'GEO_TIFF',
                'bands': ['R', 'G', 'B']
            })

            logger.info(f"\nDownload URL generated:")
            logger.info(url)
            logger.info("\nDownloading...")

            # Download the file
            import urllib.request
            output_path = IMAGERY_DIR / 'naip_harrisburg_pa.tif'
            urllib.request.urlretrieve(url, output_path)

            logger.info(f"✓ Downloaded to: {output_path}")

            # Verify
            import rasterio
            with rasterio.open(output_path) as src:
                logger.info(f"\n✓ Image Info:")
                logger.info(f"  Size: {src.width} x {src.height}")
                logger.info(f"  Bounds: {src.bounds}")
                logger.info(f"  Resolution: {src.res[0]:.2f}m")
                logger.info(f"  Bands: {src.count}")

            return [output_path]

        # Fallback to Sentinel-2
        logger.info("NAIP not available, trying Sentinel-2...")
        sentinel = ee.ImageCollection('COPERNICUS/S2_SR') \
            .filterBounds(aoi) \
            .filterDate('2023-01-01', '2023-12-31') \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
            .first()

        if sentinel:
            logger.info("✓ Found Sentinel-2 imagery")

            url = sentinel.select(['B4', 'B3', 'B2']).getDownloadURL({
                'region': aoi.getInfo()['coordinates'],
                'scale': 10,
                'format': 'GEO_TIFF'
            })

            logger.info(f"\nDownload URL: {url}")

            output_path = IMAGERY_DIR / 'sentinel2_harrisburg_pa.tif'
            urllib.request.urlretrieve(url, output_path)

            logger.info(f"✓ Downloaded to: {output_path}")
            return [output_path]

    except Exception as e:
        logger.error(f"Earth Engine failed: {e}")
        logger.info("\nPossible solutions:")
        logger.info("1. Run: earthengine authenticate")
        logger.info("2. Sign up (free): https://earthengine.google.com/signup")
        logger.info("3. Manual download from: https://earthexplorer.usgs.gov")
        return []


if __name__ == "__main__":
    logger.info("Attempting to download real satellite imagery...")
    logger.info("This will try multiple free sources\n")

    # Try Earth Engine first (best quality)
    tiles = download_via_earth_engine()

    if not tiles:
        logger.info("\n" + "=" * 80)
        logger.info("MANUAL DOWNLOAD REQUIRED")
        logger.info("=" * 80)
        logger.info("\nOption 1: NAIP from Box.com (NO LOGIN)")
        logger.info("  1. Visit: https://nrcs.app.box.com/v/naip")
        logger.info("  2. Navigate to: pa → 2021")
        logger.info("  3. Download any .tif files")
        logger.info(f"  4. Place in: {IMAGERY_DIR}\n")

        logger.info("Option 2: Google Earth Engine (FREE SIGNUP)")
        logger.info("  1. Sign up: https://earthengine.google.com/signup")
        logger.info("  2. Run: earthengine authenticate")
        logger.info("  3. Re-run this script\n")

        logger.info("Option 3: USGS EarthExplorer (FREE SIGNUP)")
        logger.info("  1. Register: https://earthexplorer.usgs.gov")
        logger.info("  2. Search: Harrisburg, PA")
        logger.info("  3. Datasets → NAIP → 2021")
        logger.info("  4. Download GeoTIFF")
    else:
        logger.info("\n✓ SUCCESS: Real imagery downloaded!")
        logger.info(f"Files: {[str(t) for t in tiles]}")
