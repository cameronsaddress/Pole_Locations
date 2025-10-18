"""
Prepare YOLOv8 dataset by splitting into train/val sets
Organizes real pole crops for model training
"""
import json
import shutil
from pathlib import Path
import logging
import sys
import random

sys.path.append(str(Path(__file__).parent.parent))
from config import PROCESSED_DATA_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def prepare_dataset(
    dataset_dir: Path,
    train_split: float = 0.8,
    seed: int = 42
):
    """
    Split dataset into train/val sets for YOLOv8

    Args:
        dataset_dir: Directory containing images/ and labels/
        train_split: Fraction for training (default 0.8 = 80/20 split)
        seed: Random seed for reproducibility
    """
    logger.info("=" * 80)
    logger.info("PREPARING YOLOV8 DATASET")
    logger.info("=" * 80)
    logger.info(f"Dataset: {dataset_dir}")
    logger.info(f"Train/Val split: {train_split:.0%}/{1-train_split:.0%}")
    logger.info("")

    images_dir = dataset_dir / 'images'
    labels_dir = dataset_dir / 'labels'

    # Get all image files
    image_files = sorted(images_dir.glob('*.png'))
    logger.info(f"✓ Found {len(image_files)} images")

    # Verify labels exist
    label_files = sorted(labels_dir.glob('*.txt'))
    logger.info(f"✓ Found {len(label_files)} labels")

    if len(image_files) != len(label_files):
        logger.warning(f"Mismatch: {len(image_files)} images vs {len(label_files)} labels")

    # Create train/val directories
    train_images_dir = dataset_dir / 'train' / 'images'
    train_labels_dir = dataset_dir / 'train' / 'labels'
    val_images_dir = dataset_dir / 'val' / 'images'
    val_labels_dir = dataset_dir / 'val' / 'labels'

    for d in [train_images_dir, train_labels_dir, val_images_dir, val_labels_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Shuffle and split
    random.seed(seed)
    random.shuffle(image_files)

    split_idx = int(len(image_files) * train_split)
    train_images = image_files[:split_idx]
    val_images = image_files[split_idx:]

    logger.info(f"\nSplitting dataset...")
    logger.info(f"  Training: {len(train_images)} images")
    logger.info(f"  Validation: {len(val_images)} images")

    # Copy train set
    logger.info("\nCopying training set...")
    for img_path in train_images:
        # Copy image
        shutil.copy2(img_path, train_images_dir / img_path.name)

        # Copy corresponding label
        label_path = labels_dir / f"{img_path.stem}.txt"
        if label_path.exists():
            shutil.copy2(label_path, train_labels_dir / label_path.name)

    # Copy val set
    logger.info("Copying validation set...")
    for img_path in val_images:
        # Copy image
        shutil.copy2(img_path, val_images_dir / img_path.name)

        # Copy corresponding label
        label_path = labels_dir / f"{img_path.stem}.txt"
        if label_path.exists():
            shutil.copy2(label_path, val_labels_dir / label_path.name)

    logger.info("\n" + "=" * 80)
    logger.info("DATASET PREPARATION COMPLETE")
    logger.info("=" * 80)
    logger.info(f"✓ Train: {len(train_images)} images")
    logger.info(f"✓ Val: {len(val_images)} images")
    logger.info(f"\n✓ Train images: {train_images_dir}")
    logger.info(f"✓ Train labels: {train_labels_dir}")
    logger.info(f"✓ Val images: {val_images_dir}")
    logger.info(f"✓ Val labels: {val_labels_dir}")

    # Update dataset.yaml
    metadata_path = dataset_dir / 'extraction_metadata.json'
    crop_size_value = None
    resolution_value = None

    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text())
            crop_size_value = metadata.get('crop_size')
            resolution_value = metadata.get('resolution_meters')
        except Exception as exc:
            logger.warning(f"Unable to read metadata from {metadata_path}: {exc}")

    crop_size_str = str(int(crop_size_value)) if crop_size_value else 'unknown'
    if resolution_value:
        resolution_str = f"{float(resolution_value):.3f}"
        resolution_comment = f"~{resolution_str}m/pixel"
        resolution_line = f"{resolution_str}m/pixel"
    else:
        resolution_str = 'unknown'
        resolution_comment = 'unknown'
        resolution_line = 'unknown'

    yaml_content = f"""# Utility Pole Detection Dataset (REAL DATA)
# Source: OSM poles + NAIP imagery
# Location: Harrisburg, PA
# Resolution: {resolution_comment}

path: {dataset_dir.absolute()}
train: train/images
val: val/images

nc: 1  # Number of classes
names: ['utility_pole']

# Dataset stats
total_images: {len(image_files)}
train_images: {len(train_images)}
val_images: {len(val_images)}
crop_size: {crop_size_str}
resolution: {resolution_line}
"""

    yaml_path = dataset_dir / 'dataset.yaml'
    with open(yaml_path, 'w') as f:
        f.write(yaml_content)

    logger.info(f"\n✓ Updated dataset config: {yaml_path}")

    logger.info("\n🎯 Ready for YOLOv8 training!")
    logger.info("Run: yolo train data=dataset.yaml model=yolov8n.pt epochs=100 imgsz=100")

    return {
        'train': len(train_images),
        'val': len(val_images),
        'total': len(image_files)
    }


if __name__ == "__main__":
    dataset_dir = PROCESSED_DATA_DIR / 'pole_training_dataset'

    if not dataset_dir.exists():
        logger.error(f"Dataset directory not found: {dataset_dir}")
        logger.info("Run: python src/utils/extract_pole_crops.py")
        sys.exit(1)

    logger.info("Preparing REAL pole dataset for YOLOv8 training...")
    logger.info("NO SYNTHETIC DATA!\n")

    stats = prepare_dataset(dataset_dir)

    if stats['total'] > 0:
        logger.info(f"\n✅ SUCCESS: Dataset ready for training!")
        logger.info(f"   Total: {stats['total']} images")
        logger.info(f"   Train: {stats['train']} images ({stats['train']/stats['total']:.0%})")
        logger.info(f"   Val: {stats['val']} images ({stats['val']/stats['total']:.0%})")
    else:
        logger.error("\n❌ FAILED: No images found")
