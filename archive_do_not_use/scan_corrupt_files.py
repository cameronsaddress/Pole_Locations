
import rasterio
from pathlib import Path
import logging
import argparse
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("CorruptFileScanner")

def scan_directory(directory: str):
    p = Path(directory)
    if not p.exists():
        logger.error(f"Directory not found: {p}")
        return

    logger.info(f"Scanning {p} for corrupt GeoTIFFs...")
    
    files = list(p.rglob("*.tif"))
    logger.info(f"Found {len(files)} TIFF files. Checking integrity...")
    
    corrupt_files = []
    
    for i, file_path in enumerate(files):
        if i % 10 == 0:
            print(f"Checked {i}/{len(files)}...", end='\r')
            
        try:
            with rasterio.open(file_path) as src:
                # 1. Check basic metadata
                _ = src.width
                _ = src.height
                
                # 2. Try to read a small chunk (center of image)
                # This catches truncated files that have valid headers but missing data
                w = min(512, src.width)
                h = min(512, src.height)
                window = rasterio.windows.Window(src.width // 2, src.height // 2, w, h)
                _ = src.read(1, window=window)
                
        except (rasterio.errors.RasterioIOError, Exception) as e:
            logger.error(f"❌ CORRUPT: {file_path} - {e}")
            corrupt_files.append(str(file_path))
            
    print("\nScan Complete.")
    
    if corrupt_files:
        logger.error(f"Found {len(corrupt_files)} corrupt files.")
        with open("corrupt_files.txt", "w") as f:
            for cf in corrupt_files:
                f.write(f"{cf}\n")
        logger.info("List saved to corrupt_files.txt")
    else:
        logger.info("✅ No corrupt files found!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dir", help="Directory to scan")
    args = parser.parse_args()
    
    scan_directory(args.dir)
