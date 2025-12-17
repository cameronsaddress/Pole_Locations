
import os
import shutil
import random
import logging
import yaml
from pathlib import Path
from tqdm import tqdm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ExpertDatprep")

# Config
# Config - Updated for Manual Feed (Human Verified)
SAT_SRC = Path("data/training/satellite_drops")
STREET_SRC = Path("data/training/layer1_drops")

SAT_DEST = Path("data/training/satellite_expert")
STREET_DEST = Path("data/training/street_expert")

VAL_SPLIT = 0.20

def setup_dirs(base_dir):
    img_train = base_dir / "images/train"
    img_val = base_dir / "images/val"
    lbl_train = base_dir / "labels/train"
    lbl_val = base_dir / "labels/val"
    
    # Clean logic: only wipe if safe
    if base_dir.exists():
        shutil.rmtree(base_dir)
    
    for d in [img_train, img_val, lbl_train, lbl_val]:
        d.mkdir(parents=True, exist_ok=True)
        
    return img_train, img_val, lbl_train, lbl_val

def create_yaml(base_dir):
    data = {
        'path': str(base_dir.absolute()),
        'train': 'images/train',
        'val': 'images/val',
        'nc': 1,
        'names': ['utility_pole']
    }
    with open(base_dir / "dataset.yaml", "w") as f:
        yaml.dump(data, f)

def process_dataset(src, dest):
    logger.info(f"Processing expert dataset: {src} -> {dest}")
    
    # Source structure verification
    src_images = src / "images"
    src_labels = src / "labels"
    
    if not src_images.exists():
        logger.warning(f"Source images dir missing: {src_images}")
        return

    img_t, img_v, lbl_t, lbl_v = setup_dirs(dest)
    create_yaml(dest)
    
    images = list(src_images.glob("*.jpg"))
    pairs = []
    
    for img in images:
        # Check for corresponding label in labels dir
        lbl = src_labels / img.with_suffix(".txt").name
        
        # KEY CHANGE: Only include if label exists and is NOT empty/skipped
        if lbl.exists():
            # Optional: Check for 'skipped' content or empty content if using that convention
            if lbl.stat().st_size > 0:
                 pairs.append((img, lbl))
            
    logger.info(f"Found {len(pairs)} labeled images in {src.name} (from {len(images)} total).")
            
    random.shuffle(pairs)
    split_idx = int(len(pairs) * (1 - VAL_SPLIT))
    train_set = pairs[:split_idx]
    val_set = pairs[split_idx:]
    
    for img, lbl in tqdm(train_set, desc=f"Train split {dest.name}"):
        shutil.copy(img, img_t / img.name)
        shutil.copy(lbl, lbl_t / lbl.name)
        
    for img, lbl in tqdm(val_set, desc=f"Val split {dest.name}"):
        shutil.copy(img, img_v / img.name)
        shutil.copy(lbl, lbl_v / lbl.name)

def main():
    if SAT_SRC.exists():
        process_dataset(SAT_SRC, SAT_DEST)
    else:
        logger.warning(f"Metadata source {SAT_SRC} not found!")

    if STREET_SRC.exists():
        process_dataset(STREET_SRC, STREET_DEST)
    else:
        logger.warning(f"Metadata source {STREET_SRC} not found!")
        
if __name__ == "__main__":
    main()
