
import os
import shutil
import random
import logging
from pathlib import Path
from tqdm import tqdm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DatasetMerger")

# Config
SAT_DIR = Path("data/training/satellite_smart_drops")
STREET_DIR = Path("data/training/street_smart_drops")
OUTPUT_DIR = Path("data/training/unified_dataset")
TRAIN_IMG_DIR = OUTPUT_DIR / "images/train"
VAL_IMG_DIR = OUTPUT_DIR / "images/val"
TRAIN_LBL_DIR = OUTPUT_DIR / "labels/train"
VAL_LBL_DIR = OUTPUT_DIR / "labels/val"

VAL_SPLIT = 0.20

def setup_dirs():
    # Only clean subdirs to preserve dataset.yaml if it exists
    for d in [TRAIN_IMG_DIR, VAL_IMG_DIR, TRAIN_LBL_DIR, VAL_LBL_DIR]:
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

def copy_dataset(source_dir, prefix):
    # Find pairs of jpg/txt
    images = list(source_dir.glob("*.jpg"))
    logger.info(f"Processing {len(images)} images from {source_dir}...")
    
    pairs = []
    for img_path in images:
        lbl_path = img_path.with_suffix(".txt")
        if lbl_path.exists():
            pairs.append((img_path, lbl_path))
            
    # Shuffle
    random.shuffle(pairs)
    
    # Split
    val_count = int(len(pairs) * VAL_SPLIT)
    val_set = pairs[:val_count]
    train_set = pairs[val_count:]
    
    # Copy Helper
    def copy_files(subset, dest_img, dest_lbl):
        for img, lbl in tqdm(subset, desc=f"Copying {prefix}"):
            # Rename to avoid collisions
            new_name = f"{prefix}_{img.name}"
            shutil.copy(img, dest_img / new_name)
            shutil.copy(lbl, dest_lbl / new_name.replace('.jpg', '.txt'))
            
    copy_files(train_set, TRAIN_IMG_DIR, TRAIN_LBL_DIR)
    copy_files(val_set, VAL_IMG_DIR, VAL_LBL_DIR)
    
    return len(train_set), len(val_set)

def main():
    setup_dirs()
    
    t1, v1 = copy_dataset(SAT_DIR, "sat")
    t2, v2 = copy_dataset(STREET_DIR, "street")
    
    logger.info("--- Merge Complete ---")
    logger.info(f"Satellite: {t1} train, {v1} val")
    logger.info(f"Street:    {t2} train, {v2} val")
    logger.info(f"Total:     {t1+t2} train, {v1+v2} val")

if __name__ == "__main__":
    main()
