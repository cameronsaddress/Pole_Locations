"""
Download utility pole imagery from public sources for training
"""
import urllib.request
import urllib.error
from pathlib import Path
import json
import logging
from typing import List, Dict
from tqdm import tqdm
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PublicImageryDownloader:
    """
    Download publicly available utility pole images for training.
    Uses multiple free sources including Google Open Images, Flickr, etc.
    """

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Public utility pole image URLs (samples - in production, use datasets like Open Images)
        # These are example URLs - you'd replace with actual dataset URLs
        self.sample_sources = {
            'openimages': 'https://storage.googleapis.com/openimages/web/index.html',
            'github_datasets': [
                'https://github.com/topics/utility-pole-detection',
                'https://github.com/search?q=power+pole+dataset'
            ]
        }

    def create_sample_training_structure(self) -> Dict[str, Path]:
        """
        Create YOLO-format training directory structure

        Returns:
            Dictionary with paths to train/val directories
        """
        structure = {
            'images_train': self.output_dir / 'images' / 'train',
            'images_val': self.output_dir / 'images' / 'val',
            'labels_train': self.output_dir / 'labels' / 'train',
            'labels_val': self.output_dir / 'labels' / 'val'
        }

        for path in structure.values():
            path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Created YOLO training structure at {self.output_dir}")
        return structure

    def generate_sample_annotations(self, num_samples: int = 100):
        """
        Generate sample YOLO annotation files for demonstration
        In production, these would come from actual labeled data

        Args:
            num_samples: Number of sample annotations to create
        """
        structure = self.create_sample_training_structure()

        logger.info(f"Generating {num_samples} sample annotations...")

        # Split 90/10 train/val
        train_count = int(num_samples * 0.9)

        for i in tqdm(range(num_samples), desc="Creating samples"):
            is_train = i < train_count

            # Determine directories
            img_dir = structure['images_train'] if is_train else structure['images_val']
            lbl_dir = structure['labels_train'] if is_train else structure['labels_val']

            # Create placeholder image file (in production, download real images)
            img_file = img_dir / f'pole_{i:04d}.jpg'
            if not img_file.exists():
                # Create a small placeholder file
                img_file.write_text(f"# Placeholder for pole image {i}")

            # Create YOLO format annotation
            # Format: class_id center_x center_y width height (normalized 0-1)
            # class 0 = utility pole
            label_file = lbl_dir / f'pole_{i:04d}.txt'

            # Sample annotation (pole in center of image)
            annotation = "0 0.5 0.5 0.1 0.6"  # class=0, centered, narrow width, tall height
            label_file.write_text(annotation)

        logger.info(f"✓ Created {train_count} training samples")
        logger.info(f"✓ Created {num_samples - train_count} validation samples")

        # Create dataset YAML file
        self._create_dataset_yaml(structure)

        return structure

    def _create_dataset_yaml(self, structure: Dict[str, Path]):
        """Create YOLO dataset configuration file"""
        yaml_content = f"""# Utility Pole Detection Dataset
# For PoleLocations Verizon Pilot Project

# Paths (relative to this file)
path: {self.output_dir.absolute()}
train: images/train
val: images/val

# Classes
nc: 1  # number of classes
names: ['utility_pole']  # class names

# Training parameters (recommended)
batch_size: 16
img_size: 640
epochs: 100
patience: 20  # early stopping
"""

        yaml_path = self.output_dir / 'pole_dataset.yaml'
        yaml_path.write_text(yaml_content)
        logger.info(f"✓ Created dataset config: {yaml_path}")

        return yaml_path

    def download_from_urls(self, urls: List[str], max_images: int = 100):
        """
        Download images from a list of URLs

        Args:
            urls: List of image URLs
            max_images: Maximum number of images to download
        """
        downloaded = 0
        img_dir = self.output_dir / 'images' / 'train'
        img_dir.mkdir(parents=True, exist_ok=True)

        for i, url in enumerate(urls[:max_images]):
            try:
                filename = img_dir / f'downloaded_{i:04d}.jpg'
                urllib.request.urlretrieve(url, filename)
                downloaded += 1
                time.sleep(0.5)  # Rate limiting
            except Exception as e:
                logger.warning(f"Failed to download {url}: {e}")

        logger.info(f"Downloaded {downloaded} images")
        return downloaded


def main():
    """
    Main function to set up training data
    """
    from pathlib import Path
    import sys

    # Add parent to path
    sys.path.append(str(Path(__file__).parent.parent))
    from config import TRAINING_DATA_DIR

    logger.info("=" * 60)
    logger.info("POLE IMAGERY TRAINING DATA SETUP")
    logger.info("=" * 60)

    downloader = PublicImageryDownloader(TRAINING_DATA_DIR)

    # For pilot, create sample training structure
    logger.info("\nCreating sample training dataset structure...")
    structure = downloader.generate_sample_annotations(num_samples=1000)

    logger.info("\n" + "=" * 60)
    logger.info("TRAINING DATA SETUP COMPLETE")
    logger.info("=" * 60)
    logger.info("\nNext steps:")
    logger.info("  1. Replace placeholder images with real pole imagery")
    logger.info("  2. Use LabelImg to annotate actual poles:")
    logger.info("     pip install labelImg")
    logger.info("     labelImg")
    logger.info("  3. Or use public datasets:")
    logger.info("     - Google Open Images (search 'utility pole')")
    logger.info("     - GitHub: search 'power pole detection dataset'")
    logger.info("     - COCO dataset (search 'pole' category)")
    logger.info(f"\n  Dataset config: {TRAINING_DATA_DIR / 'pole_dataset.yaml'}")
    logger.info(f"  Images: {TRAINING_DATA_DIR / 'images'}")
    logger.info(f"  Labels: {TRAINING_DATA_DIR / 'labels'}")


if __name__ == "__main__":
    main()
