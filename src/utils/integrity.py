
import logging
import rasterio
import rasterio.errors
import urllib.request
import time
from pathlib import Path
import planetary_computer as pc
from pystac_client import Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DataIntegrity")

def show_progress(block_num, block_size, total_size):
    downloaded = block_num * block_size
    if total_size > 0:
        percent = downloaded * 100 / total_size
        downloaded_mb = downloaded / (1024 * 1024)
        total_mb = total_size / (1024 * 1024)
        print(f"\rProgress: {percent:.1f}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)", end='')

def download_replacement(item_id: str, dest_path: Path):
    """Fetches a fresh copy of the item from Planetary Computer."""
    logger.info(f"🔄 Attempting repair for {item_id}...")
    
    try:
        catalog = Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=pc.sign_inplace,
        )
        
        search = catalog.search(collections=["naip"], ids=[item_id])
        items = list(search.items())
        
        if not items:
            logger.error(f"❌ Item {item_id} not found in Planetary Computer catalog.")
            return False
            
        item = items[0]
        asset = item.assets.get("image")
        if not asset:
            logger.error("❌ No image asset found for item.")
            return False
            
        signed_href = pc.sign(asset.href)
        
        logger.info(f"⬇️ Downloading replacement -> {dest_path}")
        urllib.request.urlretrieve(signed_href, dest_path, reporthook=show_progress)
        print("") # clean newline
        logger.info(f"✅ Successfully repaired {dest_path.name}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Repair failed: {e}")
        return False

def scan_and_repair(directories):
    """Scans directories for corrupt TIFFs and auto-repairs them."""
    logger.info(f"🛡️ Starting Data Integrity Scan on: {directories}")
    
    corrupt_count = 0
    repaired_count = 0
    
    all_files = []
    for d in directories:
        p = Path(d)
        if p.exists():
            all_files.extend(list(p.rglob("*.tif")))
            
    logger.info(f"Scanning {len(all_files)} files...")
    
    for i, file_path in enumerate(all_files):
        if i % 100 == 0:
            print(f"Checked {i}/{len(all_files)}...", end='\r')
            
        is_corrupt = False
        try:
            with rasterio.open(file_path) as src:
                # Basic header check
                _ = src.width
                # Deep data check (center window)
                w = min(512, src.width)
                h = min(512, src.height)
                window = rasterio.windows.Window(src.width // 2, src.height // 2, w, h)
                src.read(1, window=window)
        except (rasterio.errors.RasterioIOError, Exception):
            is_corrupt = True
            
        if is_corrupt:
            logger.warning(f"⚠️ CORRUPT FILE DETECTED: {file_path}")
            corrupt_count += 1
            
            # Delete bad file
            try:
                file_path.unlink()
            except:
                pass
                
            # Attempt Repair
            # Assuming filename is item_id (e.g. "pa_m_3907604_ne_18_060_20220711.tif")
            item_id = file_path.stem 
            success = download_replacement(item_id, file_path)
            if success:
                repaired_count += 1
                
    logger.info(f"🛡️ Integrity Scan Complete.")
    logger.info(f"   Corrupt: {corrupt_count}")
    logger.info(f"   Repaired: {repaired_count}")
    
    if corrupt_count > repaired_count:
        logger.warning(f"⚠️ {corrupt_count - repaired_count} files could not be repaired.")
