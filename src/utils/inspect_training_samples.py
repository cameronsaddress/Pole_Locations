"""
Inspect training samples to diagnose low model performance
Displays sample images with annotations to verify pole visibility
"""
import sys
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from PIL import Image
import random

sys.path.append(str(Path(__file__).parent.parent))
from config import PROCESSED_DATA_DIR

def inspect_samples(dataset_dir: Path, num_samples: int = 9):
    """
    Display sample training images with YOLO annotations

    Args:
        dataset_dir: Path to training dataset
        num_samples: Number of samples to display
    """
    train_images_dir = dataset_dir / 'train' / 'images'
    train_labels_dir = dataset_dir / 'train' / 'labels'

    image_files = list(train_images_dir.glob('*.png'))
    samples = random.sample(image_files, min(num_samples, len(image_files)))

    fig, axes = plt.subplots(3, 3, figsize=(15, 15))
    fig.suptitle('Training Samples with YOLO Annotations (Red Box = Pole)', fontsize=16)

    for idx, img_path in enumerate(samples):
        row, col = idx // 3, idx % 3
        ax = axes[row, col]

        # Load image
        img = Image.open(img_path)
        ax.imshow(img)

        # Load annotation
        label_path = train_labels_dir / f"{img_path.stem}.txt"
        if label_path.exists():
            with open(label_path, 'r') as f:
                for line in f:
                    # YOLO format: class_id center_x center_y width height (normalized)
                    parts = line.strip().split()
                    if len(parts) == 5:
                        _, cx, cy, w, h = map(float, parts)

                        # Convert normalized coords to pixels
                        img_w, img_h = img.size
                        x = (cx - w/2) * img_w
                        y = (cy - h/2) * img_h
                        box_w = w * img_w
                        box_h = h * img_h

                        # Draw bounding box
                        rect = patches.Rectangle(
                            (x, y), box_w, box_h,
                            linewidth=2, edgecolor='red', facecolor='none'
                        )
                        ax.add_patch(rect)

        ax.set_title(f"{img_path.name}", fontsize=8)
        ax.axis('off')

    plt.tight_layout()
    output_path = dataset_dir / 'sample_inspection.png'
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"✓ Saved inspection image: {output_path}")
    print(f"\n📋 Analysis:")
    print(f"  - If poles are NOT visible in the images, the OSM coordinates may be inaccurate")
    print(f"  - If poles ARE visible but very small, we need higher resolution imagery")
    print(f"  - If red boxes don't align with poles, we have a coordinate transformation issue")


def analyze_annotations(dataset_dir: Path):
    """Analyze annotation statistics"""
    train_labels_dir = dataset_dir / 'train' / 'labels'
    label_files = list(train_labels_dir.glob('*.txt'))

    box_sizes = []
    for label_path in label_files:
        with open(label_path, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 5:
                    _, _, _, w, h = map(float, parts)
                    box_sizes.append((w, h))

    if box_sizes:
        avg_w = sum(w for w, h in box_sizes) / len(box_sizes)
        avg_h = sum(h for w, h in box_sizes) / len(box_sizes)

        print(f"\n📊 Annotation Statistics:")
        print(f"  Total annotations: {len(box_sizes)}")
        print(f"  Avg box width: {avg_w:.4f} (normalized) = {avg_w*100:.1f}px in 100px image")
        print(f"  Avg box height: {avg_h:.4f} (normalized) = {avg_h*100:.1f}px in 100px image")
        print(f"\n⚠️  Issue: Boxes are {avg_w*100:.1f}×{avg_h*100:.1f} pixels")
        print(f"   YOLOv8 struggles with objects <10×10 pixels")
        print(f"   Recommendation: Use larger crop size (256px or 512px)")


if __name__ == "__main__":
    dataset_dir = PROCESSED_DATA_DIR / 'pole_training_dataset'

    print("=" * 80)
    print("INSPECTING TRAINING SAMPLES")
    print("=" * 80)
    print(f"Dataset: {dataset_dir}\n")

    # Analyze annotations
    analyze_annotations(dataset_dir)

    # Create visual inspection
    print("\nCreating visual inspection...")
    inspect_samples(dataset_dir, num_samples=9)

    print("\n✅ Inspection complete!")
    print(f"   Open: {dataset_dir}/sample_inspection.png")
