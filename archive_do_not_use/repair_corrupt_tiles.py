
"""
Repair Corrupt NAIP Tiles
-------------------------
Redownloads specific Item IDs from Microsoft Planetary Computer to replace corrupted local files.
"""
import logging
import time
import urllib.request
from pathlib import Path
import planetary_computer as pc
from pystac_client import Client
import rasterio
import rasterio.errors

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("NAIP_Repair")

# Map Item ID -> Destination Folder
REPAIR_TARGETS = {
    "pa_m_3907604_ne_18_060_20220711": "/data/imagery/naip_multi_county/dauphin_pa",
    "md_m_3907622_nw_18_030_20230527_20231018": "/data/imagery/naip_multi_county/york_pa",
    "md_m_3907622_sw_18_030_20230527_20231018": "/data/imagery/naip_multi_county/york_pa",
    "ny_m_4207748_ne_18_060_20221103": "/data/imagery/naip_multi_county/new_york_state/schuyler"
}

def is_valid_geotiff(path: Path) -> bool:
    """Checks if a GeoTIFF file is valid and readable."""
    try:
        with rasterio.open(path) as src:
            # Basic header check
            _ = src.width
            # Deep data check (read center window)
            w = min(512, src.width)
            h = min(512, src.height)
            window = rasterio.windows.Window(src.width // 2, src.height // 2, w, h)
            src.read(1, window=window)
        return True
    except (rasterio.errors.RasterioIOError, Exception):
        return False

def repair_tiles():
    logger.info("Connecting to Planetary Computer...")
    catalog = Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=pc.sign_inplace,
    )
    
    item_ids = list(REPAIR_TARGETS.keys())
    logger.info(f"Searching for {len(item_ids)} items: {item_ids}")
    
    search = catalog.search(collections=["naip"], ids=item_ids)
    items = list(search.items())
    
    logger.info(f"Found {len(items)} matching items in catalog.")
    
    for item in items:
        item_id = item.id
        dest_dir = Path(REPAIR_TARGETS.get(item_id))
        
        if not dest_dir.exists():
            logger.warning(f"Destination dir {dest_dir} does not exist, creating.")
            dest_dir.mkdir(parents=True, exist_ok=True)
            
        asset = item.assets.get("image")
        if not asset:
            logger.error(f"No image asset for {item_id}")
            continue
            
        dest_path = dest_dir / f"{item_id}.tif"
        
        # 1. Check if exists and valid (Resume Logic)
        if dest_path.exists():
            if is_valid_geotiff(dest_path):
                logger.info(f"✅ File exists and is valid: {dest_path.name} (Skipping)")
                continue
            else:
                logger.warning(f"⚠️ Found CORRUPT file (will replace): {dest_path}")
                dest_path.unlink()
        else:
            logger.info(f"⚠️ File missing: {dest_path}")

        # 2. Download
        logger.info(f"⬇️ Downloading {item_id} -> {dest_path}")
        
        def show_progress(block_num, block_size, total_size):
            downloaded = block_num * block_size
            if total_size > 0:
                percent = downloaded * 100 / total_size
                downloaded_mb = downloaded / (1024 * 1024)
                total_mb = total_size / (1024 * 1024)
                print(f"\rProgress: {percent:.1f}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)", end='')
            
        try:
            signed_href = pc.sign(asset.href)
            urllib.request.urlretrieve(signed_href, dest_path, reporthook=show_progress)
            print("") # Newline after progress
            logger.info(f"✅ Downloaded {item.id}")
        except Exception as e:
            print("") # Newline if error during progress
            logger.error(f"❌ Failed to download {item_id}: {e}")

if __name__ == "__main__":
    repair_tiles()
