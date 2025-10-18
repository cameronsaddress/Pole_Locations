"""
Download REAL NAIP imagery from AWS S3 (FREE)
Using naip-visualization bucket (RGB Cloud Optimized GeoTIFF)
NO MOCK DATA - Real aerial imagery from USDA
"""
import boto3
from botocore import UNSIGNED
from botocore.config import Config
import rasterio
from pathlib import Path
import logging
import sys

sys.path.append(str(Path(__file__).parent.parent))
from config import IMAGERY_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def download_naip_real_imagery():
    """
    Download REAL NAIP imagery from AWS S3
    Source: https://registry.opendata.aws/naip/
    Bucket: naip-visualization (RGB, Cloud Optimized GeoTIFF)
    """
    logger.info("=" * 80)
    logger.info("DOWNLOADING REAL NAIP IMAGERY FROM AWS")
    logger.info("=" * 80)
    logger.info("Source: USDA National Agriculture Imagery Program")
    logger.info("Bucket: naip-visualization (Public Access)")
    logger.info("Format: RGB Cloud Optimized GeoTIFF")
    logger.info("")

    # Use anonymous access for public bucket
    s3 = boto3.client('s3',
                     region_name='us-west-2',
                     config=Config(signature_version=UNSIGNED))

    # NAIP bucket structure: naip-visualization/state/year/state_60cm_year_state_fips_number.tif
    # Example: pa/2021/60cm/rgb/pa_060cm_2021_1.tif

    # Target: Pennsylvania 2021 imagery (5 square miles coverage)
    bucket = 'naip-visualization'
    state = 'pa'
    year = '2021'

    logger.info(f"Searching for {state.upper()} {year} imagery...")

    try:
        # List available tiles
        prefix = f"{state}/{year}/"

        response = s3.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix,
            MaxKeys=20
        )

        if 'Contents' not in response:
            logger.warning(f"No files found in {bucket}/{prefix}")
            # Try alternate structure
            logger.info("Trying alternate path structure...")
            prefix = f"{state}/{year}/60cm/rgb/"
            response = s3.list_objects_v2(
                Bucket=bucket,
                Prefix=prefix,
                MaxKeys=20
            )

        tiles = []
        if 'Contents' in response:
            for obj in response['Contents']:
                key = obj['Key']
                if key.endswith('.tif'):
                    tiles.append(key)
                    logger.info(f"  Found: {key} ({obj['Size'] / 1024 / 1024:.1f} MB)")

        if not tiles:
            raise ValueError("No NAIP tiles found")

        logger.info(f"\n✓ Found {len(tiles)} tiles")

        # Download first 3 tiles (covers ~5 square miles)
        downloaded = []
        for i, tile_key in enumerate(tiles[:3]):
            filename = Path(tile_key).name
            output_path = IMAGERY_DIR / filename

            if output_path.exists():
                logger.info(f"\n[{i+1}/3] Already downloaded: {filename}")
            else:
                logger.info(f"\n[{i+1}/3] Downloading: {filename}")
                logger.info(f"  Size: {response['Contents'][i]['Size'] / 1024 / 1024:.1f} MB")

                s3.download_file(bucket, tile_key, str(output_path))
                logger.info(f"  ✓ Saved to: {output_path}")

            downloaded.append(output_path)

            # Get tile info
            with rasterio.open(output_path) as src:
                logger.info(f"  Bounds: {src.bounds}")
                logger.info(f"  CRS: {src.crs}")
                logger.info(f"  Resolution: {src.res[0]:.2f}m x {src.res[1]:.2f}m")
                logger.info(f"  Size: {src.width} x {src.height} pixels")
                logger.info(f"  Bands: {src.count}")

        logger.info("\n" + "=" * 80)
        logger.info("REAL NAIP IMAGERY DOWNLOAD COMPLETE")
        logger.info("=" * 80)
        logger.info(f"✓ Downloaded {len(downloaded)} tiles")
        logger.info(f"✓ Coverage: ~5 square miles")
        logger.info(f"✓ Location: {IMAGERY_DIR}")
        logger.info("")
        logger.info("🎯 Next: Extract pole locations and create training dataset")

        return downloaded

    except Exception as e:
        logger.error(f"Download failed: {e}")
        logger.info("\nTrying USGS EarthExplorer method...")
        return download_via_earthengine()


def download_via_earthengine():
    """
    Fallback: Use Google Earth Engine Python API
    Requires: pip install earthengine-api
    """
    try:
        import ee

        logger.info("Attempting download via Google Earth Engine...")
        logger.info("Note: Requires GEE account signup at https://earthengine.google.com")

        # Initialize Earth Engine
        # ee.Authenticate()  # Run once to authenticate
        ee.Initialize()

        # Define area of interest (5 sq miles in PA)
        aoi = ee.Geometry.Rectangle([-77.0, 40.2, -76.9, 40.3])

        # Get NAIP imagery
        naip = ee.ImageCollection('USDA/NAIP/DOQQ') \
            .filterBounds(aoi) \
            .filterDate('2020-01-01', '2022-12-31') \
            .first()

        # Download
        url = naip.getDownloadURL({
            'region': aoi,
            'scale': 1,  # 1 meter resolution
            'format': 'GEO_TIFF'
        })

        logger.info(f"Download URL: {url}")
        logger.info("Opening in browser for manual download...")

        import webbrowser
        webbrowser.open(url)

        return []

    except ImportError:
        logger.error("earthengine-api not installed")
        logger.info("Install with: pip install earthengine-api")
        logger.info("Then run: earthengine authenticate")
        return []
    except Exception as e:
        logger.error(f"Earth Engine download failed: {e}")
        return []


if __name__ == "__main__":
    tiles = download_naip_real_imagery()

    if tiles:
        logger.info("\n✓ SUCCESS: Real NAIP imagery downloaded!")
        logger.info(f"Files: {[t.name for t in tiles]}")
    else:
        logger.error("\n✗ FAILED: Could not download imagery")
        logger.info("\nManual download instructions:")
        logger.info("1. Go to: https://earthexplorer.usgs.gov/")
        logger.info("2. Search for: Harrisburg, PA")
        logger.info("3. Datasets → Aerial Imagery → NAIP")
        logger.info("4. Select 2021 imagery")
        logger.info("5. Download GeoTIFF files")
        logger.info(f"6. Place in: {IMAGERY_DIR}")
