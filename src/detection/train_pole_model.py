"""
Train YOLOv8 model on REAL utility pole imagery
Uses 317 real pole crops from NAIP imagery + OSM coordinates
"""
from ultralytics import YOLO
from pathlib import Path
import logging
import sys

sys.path.append(str(Path(__file__).parent.parent))
from config import PROCESSED_DATA_DIR, MODELS_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def train_pole_detector(
    data_yaml: Path,
    epochs: int = 150,
    batch_size: int = 8,
    img_size: int = 256,
    patience: int = 50,
    device: str = 'cpu'
):
    """
    Train YOLOv8 model on real utility pole dataset

    Args:
        data_yaml: Path to dataset.yaml
        epochs: Number of training epochs (default 100)
        batch_size: Batch size (default 16)
        img_size: Image size (default 100)
        patience: Early stopping patience (default 50)
        device: Training device ('cpu' or 'cuda')
    """
    logger.info("=" * 80)
    logger.info("TRAINING YOLOV8 POLE DETECTOR ON REAL DATA")
    logger.info("=" * 80)
    logger.info(f"Dataset: {data_yaml}")
    logger.info(f"Epochs: {epochs}")
    logger.info(f"Batch size: {batch_size}")
    logger.info(f"Image size: {img_size}x{img_size}")
    logger.info(f"Device: {device}")
    logger.info("")

    # Verify dataset exists
    if not data_yaml.exists():
        raise FileNotFoundError(f"Dataset config not found: {data_yaml}")

    # Load YOLOv8 nano model (fastest, good for 100x100 images)
    logger.info("Loading YOLOv8n pretrained model...")
    model = YOLO('yolov8n.pt')
    logger.info("✓ Model loaded")

    # Train the model
    logger.info("\nStarting training...")
    logger.info("This will take 30-60 minutes on CPU (5-10 min on GPU)")
    logger.info("")

    results = model.train(
        data=str(data_yaml),
        epochs=epochs,
        imgsz=img_size,
        batch=batch_size,
        patience=patience,
        device=device,
        project=str(MODELS_DIR),
        name='pole_detector_v1',
        exist_ok=True,
        pretrained=True,
        optimizer='Adam',
        verbose=True,
        # Augmentation settings
        degrees=15.0,  # Rotation augmentation
        translate=0.1,  # Translation augmentation
        scale=0.2,      # Scale augmentation
        flipud=0.0,     # No vertical flip (poles are vertical)
        fliplr=0.5,     # Horizontal flip OK
        mosaic=0.5,     # Mosaic augmentation
        mixup=0.0,      # No mixup (simple dataset)
        # Performance settings
        workers=4,
        save=True,
        save_period=10,  # Save checkpoint every 10 epochs
        cache=False,     # Don't cache (dataset is small)
    )

    logger.info("\n" + "=" * 80)
    logger.info("TRAINING COMPLETE")
    logger.info("=" * 80)

    # Get best model path
    best_model_path = MODELS_DIR / 'pole_detector_v1' / 'weights' / 'best.pt'
    last_model_path = MODELS_DIR / 'pole_detector_v1' / 'weights' / 'last.pt'

    logger.info(f"✓ Best model: {best_model_path}")
    logger.info(f"✓ Last model: {last_model_path}")

    # Load best model and validate
    logger.info("\nValidating best model...")
    best_model = YOLO(str(best_model_path))
    val_results = best_model.val()

    logger.info("\n📊 VALIDATION METRICS:")
    logger.info(f"  mAP50: {val_results.box.map50:.3f}")
    logger.info(f"  mAP50-95: {val_results.box.map:.3f}")
    logger.info(f"  Precision: {val_results.box.mp:.3f}")
    logger.info(f"  Recall: {val_results.box.mr:.3f}")

    # Save final model to standard location
    final_model_path = MODELS_DIR / 'pole_detector_real.pt'
    import shutil
    shutil.copy2(best_model_path, final_model_path)
    logger.info(f"\n✓ Final model saved: {final_model_path}")

    logger.info("\n🎯 Next Steps:")
    logger.info("  1. Test model on validation images")
    logger.info("  2. Run detection on full NAIP imagery")
    logger.info("  3. Validate detection accuracy")
    logger.info("  4. Generate final results report")

    return {
        'best_model': best_model_path,
        'final_model': final_model_path,
        'map50': val_results.box.map50,
        'map': val_results.box.map,
        'precision': val_results.box.mp,
        'recall': val_results.box.mr
    }


if __name__ == "__main__":
    dataset_yaml = PROCESSED_DATA_DIR / 'pole_training_dataset' / 'dataset.yaml'

    if not dataset_yaml.exists():
        logger.error(f"Dataset config not found: {dataset_yaml}")
        logger.info("Run these scripts first:")
        logger.info("  1. python src/utils/extract_pole_crops.py")
        logger.info("  2. python src/utils/prepare_yolo_dataset.py")
        sys.exit(1)

    logger.info("Training YOLOv8 on REAL pole imagery...")
    logger.info("Source: OSM poles + NAIP satellite imagery")
    logger.info("NO SYNTHETIC DATA!\n")

    # Check for GPU
    import torch
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    if device == 'cpu':
        logger.info("⚠️  Training on CPU (slow). For faster training, use GPU.")
        logger.info("   Expected time: 30-60 minutes")
    else:
        logger.info("✓ GPU detected! Training will be fast (5-10 minutes)")

    logger.info("")

    try:
        results = train_pole_detector(
            data_yaml=dataset_yaml,
            epochs=150,
            batch_size=8,
            img_size=256,
            device=device
        )

        logger.info("\n✅ SUCCESS: Model training complete!")
        logger.info(f"   Precision: {results['precision']:.1%}")
        logger.info(f"   Recall: {results['recall']:.1%}")
        logger.info(f"   mAP50: {results['map50']:.1%}")
        logger.info(f"\n✓ Model ready for pole detection!")

    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Training interrupted by user")
        logger.info("Partial model may be saved in models/pole_detector_v1/")
    except Exception as e:
        logger.error(f"\n❌ Training failed: {e}")
        import traceback
        traceback.print_exc()
