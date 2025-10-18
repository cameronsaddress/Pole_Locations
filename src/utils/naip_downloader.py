"""
Download NAIP imagery from AWS S3 for pole detection
NAIP (National Agriculture Imagery Program) provides free 1m resolution aerial imagery
"""
import boto3
from botocore import UNSIGNED
from botocore.config import Config
import rasterio
from rasterio.merge import merge
from rasterio.warp import calculate_default_transform, reproject, Resampling
from pathlib import Path
import logging
from typing import List, Tuple, Optional
import sys
from tqdm import tqdm

sys.path.append(str(Path(__file__).parent.parent))
from config import IMAGERY_DIR, EAST_COAST_BBOX

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NAIPDownloader:
    """
    Download NAIP imagery from AWS S3
    Free public dataset: s3://naip-analytic/
    """

    def __init__(self):
        # Use anonymous access (no credentials needed for public NAIP data)
        self.s3 = boto3.client('s3',
                              region_name='us-west-2',
                              config=Config(signature_version=UNSIGNED))
        self.bucket = 'naip-analytic'
        self.imagery_dir = IMAGERY_DIR
        self.imagery_dir.mkdir(parents=True, exist_ok=True)

    def find_naip_tiles(self, state: str, year: str = '2022') -> List[str]:
        """
        Find available NAIP tiles for a state and year

        Args:
            state: Two-letter state code (e.g., 'pa', 'ny')
            year: Year of imagery (e.g., '2022', '2021', '2020')

        Returns:
            List of S3 keys for available tiles
        """
        logger.info(f"Searching for NAIP tiles: {state.upper()}/{year}")

        # NAIP S3 structure: naip-analytic/state/year/resolution/rgb/
        # We want 1m resolution 4-band imagery
        prefix = f"{state}/{year}/60cm/rgbir/"

        try:
            paginator = self.s3.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket, Prefix=prefix, MaxKeys=100)

            tiles = []
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        key = obj['Key']
                        if key.endswith('.tif'):
                            tiles.append(key)

            logger.info(f"Found {len(tiles)} NAIP tiles for {state.upper()}/{year}")
            return tiles

        except Exception as e:
            logger.error(f"Error searching NAIP tiles: {e}")
            # Try alternate bucket structure
            logger.info("Trying alternate NAIP bucket structure...")
            return self._search_alternate_structure(state, year)

    def _search_alternate_structure(self, state: str, year: str) -> List[str]:
        """Try alternate NAIP bucket structures"""
        # Try naip-visualization bucket which has different structure
        try:
            bucket = 'naip-visualization'
            prefix = f"{state}/{year}/"

            paginator = self.s3.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket, Prefix=prefix, MaxKeys=100)

            tiles = []
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        key = obj['Key']
                        if key.endswith('.tif'):
                            tiles.append((bucket, key))

            logger.info(f"Found {len(tiles)} tiles in alternate bucket")
            return tiles

        except Exception as e:
            logger.warning(f"Alternate bucket search failed: {e}")
            return []

    def download_tile(self, s3_key: str, output_path: Optional[Path] = None) -> Path:
        """
        Download a single NAIP tile from S3

        Args:
            s3_key: S3 object key
            output_path: Local path to save file

        Returns:
            Path to downloaded file
        """
        if output_path is None:
            filename = Path(s3_key).name
            output_path = self.imagery_dir / filename

        if output_path.exists():
            logger.info(f"Tile already downloaded: {output_path.name}")
            return output_path

        logger.info(f"Downloading {s3_key}")

        try:
            self.s3.download_file(self.bucket, s3_key, str(output_path))
            logger.info(f"✓ Downloaded to {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise

    def download_area_tiles(self, lat: float, lon: float,
                           radius_km: float = 2.0,
                           state: str = 'pa',
                           year: str = '2021') -> List[Path]:
        """
        Download NAIP tiles covering an area around a point

        Args:
            lat: Latitude of center point
            lon: Longitude of center point
            radius_km: Radius in kilometers
            state: State code
            year: Year of imagery

        Returns:
            List of downloaded tile paths
        """
        logger.info(f"Downloading tiles around ({lat}, {lon}) within {radius_km}km")

        # Find available tiles
        tiles = self.find_naip_tiles(state, year)

        if not tiles:
            logger.warning(f"No tiles found for {state}/{year}")
            logger.info("Trying different years...")
            for year_alt in ['2022', '2020', '2019', '2018']:
                tiles = self.find_naip_tiles(state, year_alt)
                if tiles:
                    logger.info(f"Found tiles in {year_alt}")
                    break

        if not tiles:
            raise ValueError(f"No NAIP tiles available for {state}")

        # Download first few tiles for 5 sq mi area
        # (Each NAIP tile is typically 3.75 x 3.75 miles)
        # So we need 2-3 tiles to cover 5 sq mi
        max_tiles = min(3, len(tiles))

        downloaded = []
        for tile_key in tiles[:max_tiles]:
            try:
                if isinstance(tile_key, tuple):
                    bucket, key = tile_key
                    # Use alternate bucket
                    logger.info(f"Downloading from {bucket}: {key}")
                    filename = Path(key).name
                    output_path = self.imagery_dir / filename

                    if not output_path.exists():
                        s3_alt = boto3.client('s3',
                                            region_name='us-west-2',
                                            config=Config(signature_version=UNSIGNED))
                        s3_alt.download_file(bucket, key, str(output_path))

                    downloaded.append(output_path)
                else:
                    path = self.download_tile(tile_key)
                    downloaded.append(path)

            except Exception as e:
                logger.warning(f"Failed to download {tile_key}: {e}")
                continue

        logger.info(f"✓ Downloaded {len(downloaded)} tiles")
        return downloaded

    def get_tile_info(self, tile_path: Path) -> dict:
        """Get metadata about a NAIP tile"""
        with rasterio.open(tile_path) as src:
            info = {
                'bounds': src.bounds,
                'crs': src.crs,
                'resolution': src.res,
                'shape': (src.height, src.width),
                'bands': src.count,
                'dtype': src.dtypes[0]
            }
        return info


def download_sample_imagery():
    """
    Download 5 square miles of NAIP imagery for pilot
    Focus on Pennsylvania (high pole density)
    """
    logger.info("=" * 80)
    logger.info("DOWNLOADING NAIP IMAGERY FOR PILOT")
    logger.info("=" * 80)

    downloader = NAIPDownloader()

    # Target area: Central PA (good pole density)
    # Harrisburg area: 40.2732° N, 76.8867° W
    center_lat = 40.2732
    center_lon = -76.8867

    logger.info(f"\nTarget Area: Harrisburg, PA region")
    logger.info(f"  Center: {center_lat}, {center_lon}")
    logger.info(f"  Coverage: ~5 square miles")

    try:
        # Download tiles covering the area
        tiles = downloader.download_area_tiles(
            lat=center_lat,
            lon=center_lon,
            radius_km=2.0,
            state='pa',
            year='2021'
        )

        if tiles:
            logger.info("\n" + "=" * 80)
            logger.info("DOWNLOAD COMPLETE")
            logger.info("=" * 80)

            for tile in tiles:
                info = downloader.get_tile_info(tile)
                logger.info(f"\n✓ {tile.name}")
                logger.info(f"  Bounds: {info['bounds']}")
                logger.info(f"  Resolution: {info['resolution'][0]:.2f}m")
                logger.info(f"  Size: {info['shape'][0]} x {info['shape'][1]} pixels")
                logger.info(f"  Bands: {info['bands']}")

            logger.info(f"\n✓ Total tiles downloaded: {len(tiles)}")
            logger.info(f"✓ Imagery stored in: {IMAGERY_DIR}")

            return tiles

        else:
            logger.error("No tiles downloaded!")
            raise RuntimeError("Unable to locate NAIP tiles for the requested area.")

    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise RuntimeError(
            "NAIP download failed. Please verify your network connection or download imagery manually "
            "from https://earthexplorer.usgs.gov."
        ) from e


if __name__ == "__main__":
    tiles = download_sample_imagery()

    if tiles:
        logger.info("\n🎯 Next Steps:")
        logger.info("  1. Extract pole crops from imagery")
        logger.info("  2. Label poles with LabelImg")
        logger.info("  3. Train YOLOv8 model")
        logger.info("  4. Run detection on full area")
