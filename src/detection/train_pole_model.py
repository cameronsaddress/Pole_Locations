"""Train YOLOv8 detector on real utility-pole imagery using GPU acceleration."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from ultralytics import YOLO

sys.path.append(str(Path(__file__).parent.parent))
from config import MODELS_DIR, PROCESSED_DATA_DIR  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("pole-trainer")


def _default_device(user_device: str | None = None) -> str:
    """Choose CUDA when available unless the user forces a device."""
    if user_device:
        return user_device
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:  # pragma: no cover - defensive
        return "cpu"


def train_pole_detector(
    data_yaml: Path,
    model_name: str,
    output_name: str,
    epochs: int,
    batch_size: int,
    img_size: int,
    patience: int,
    device: str,
    workers: int,
    optimizer: str,
    learning_rate: float | None = None,
    warmup_epochs: float | None = None,
    cos_lr: bool = False,
    augment_mosaic: float = 0.5,
    augment_mixup: float = 0.0,
    augment_degrees: float = 15.0,
    augment_translate: float = 0.1,
    augment_scale: float = 0.2,
    augment_fliplr: float = 0.5,
    augment_shear: float = 0.0,
    hsv_h: float = 0.015,
    hsv_s: float = 0.7,
    hsv_v: float = 0.4,
    weight_decay: float = 0.0005,
    label_smoothing: float = 0.0,
) -> Dict[str, Any]:
    """Fine-tune a YOLOv8 model on the curated pole dataset."""
    LOGGER.info("=" * 90)
    LOGGER.info("YOLOv8 POLE DETECTOR TRAINING")
    LOGGER.info("=" * 90)
    LOGGER.info("Dataset:      %s", data_yaml)
    LOGGER.info("Model:        %s", model_name)
    LOGGER.info("Project name: %s", output_name)
    LOGGER.info("Epochs:       %d", epochs)
    LOGGER.info("Batch size:   %d", batch_size)
    LOGGER.info("Image size:   %d", img_size)
    LOGGER.info("Patience:     %d", patience)
    LOGGER.info("Device:       %s", device)
    LOGGER.info("Workers:      %d", workers)
    LOGGER.info("Optimizer:    %s", optimizer)
    if learning_rate:
        LOGGER.info("Learning rate: %.5f", learning_rate)
    if warmup_epochs:
        LOGGER.info("Warmup epochs: %.2f", warmup_epochs)
    LOGGER.info("Weight decay: %.5f", weight_decay)
    if label_smoothing:
        LOGGER.info("Label smoothing: %.3f", label_smoothing)
    LOGGER.info("HSV augment:  h=%.3f s=%.3f v=%.3f", hsv_h, hsv_s, hsv_v)
    if augment_shear:
        LOGGER.info("Shear augment: %.2f", augment_shear)
    LOGGER.info("")

    if not data_yaml.exists():
        raise FileNotFoundError(f"Dataset config not found: {data_yaml}")

    LOGGER.info("Loading pretrained weights: %s", model_name)
    model = YOLO(model_name)

    train_kwargs: Dict[str, Any] = {
        "data": str(data_yaml),
        "epochs": epochs,
        "imgsz": img_size,
        "batch": batch_size,
        "patience": patience,
        "device": device,
        "project": str(MODELS_DIR),
        "name": output_name,
        "exist_ok": True,
        "pretrained": True,
        "optimizer": optimizer,
        "verbose": True,
        "workers": workers,
        "degrees": augment_degrees,
        "translate": augment_translate,
        "scale": augment_scale,
        "flipud": 0.0,
        "fliplr": augment_fliplr,
        "mosaic": augment_mosaic,
        "mixup": augment_mixup,
        "cache": False,
        "save": True,
        "save_period": max(10, epochs // 10),
        "plots": True,
        "close_mosaic": 5,
        "weight_decay": weight_decay,
        "label_smoothing": label_smoothing,
        "hsv_h": hsv_h,
        "hsv_s": hsv_s,
        "hsv_v": hsv_v,
        "shear": augment_shear,
    }

    if learning_rate:
        train_kwargs["lr0"] = learning_rate
    if warmup_epochs is not None:
        train_kwargs["warmup_epochs"] = warmup_epochs
    if cos_lr:
        train_kwargs["cos_lr"] = True

    LOGGER.info("Kickstarting training…")
    _train_metrics = model.train(**train_kwargs)

    # Ultralytics exposes the save directory on the trainer instance.
    try:
        project_dir = Path(model.trainer.save_dir)
    except AttributeError:  # pragma: no cover - fallback for older versions
        project_dir = Path(MODELS_DIR) / output_name
    weights_dir = project_dir / "weights"
    best_model_path = weights_dir / "best.pt"
    last_model_path = weights_dir / "last.pt"

    LOGGER.info("Training complete. Best weights: %s", best_model_path)

    LOGGER.info("Running validation sweep on best checkpoint…")
    best_model = YOLO(str(best_model_path))
    val_results = best_model.val(device=device, imgsz=img_size)

    metrics = {
        "map50": float(val_results.box.map50),
        "map50_95": float(val_results.box.map),
        "precision": float(val_results.box.mp),
        "recall": float(val_results.box.mr),
        "epochs": epochs,
        "batch_size": batch_size,
        "img_size": img_size,
        "model": model_name,
        "device": device,
        "timestamp": datetime.utcnow().isoformat(),
        "output_dir": str(project_dir),
        "best_weights": str(best_model_path),
        "last_weights": str(last_model_path),
    }

    LOGGER.info("")
    LOGGER.info("📊 Validation metrics:")
    for key in ("map50", "map50_95", "precision", "recall"):
        LOGGER.info("  %-10s %.3f", key, metrics[key])

    final_model_path = MODELS_DIR / "pole_detector_real.pt"
    shutil.copy2(best_model_path, final_model_path)
    LOGGER.info("Copied best weights to %s", final_model_path)

    metrics_path = project_dir / "training_metrics.json"
    with metrics_path.open("w", encoding="utf-8") as fp:
        json.dump(metrics, fp, indent=2)
    LOGGER.info("Saved training metrics to %s", metrics_path)

    summary_path = project_dir / "training_summary.txt"
    with summary_path.open("w", encoding="utf-8") as fp:
        fp.write("YOLO Pole Detector Training Summary\n")
        fp.write("=" * 60 + "\n")
        for key, value in metrics.items():
            fp.write(f"{key}: {value}\n")
    LOGGER.info("Wrote human-readable summary to %s", summary_path)

    metrics["final_model"] = str(final_model_path)
    metrics["metrics_path"] = str(metrics_path)
    metrics["summary_path"] = str(summary_path)
    return metrics


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the YOLO pole detector with GPU acceleration.")
    parser.add_argument(
        "--data",
        type=Path,
        default=PROCESSED_DATA_DIR / "pole_training_dataset" / "dataset.yaml",
        help="Path to YOLO dataset YAML.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="yolov8m.pt",
        help="Base YOLO checkpoint to fine-tune (e.g., yolov8n.pt, yolov8s.pt, yolov8m.pt).",
    )
    parser.add_argument("--output-name", type=str, default="pole_detector_v2", help="Ultralytics project/name.")
    parser.add_argument("--epochs", type=int, default=200, help="Number of training epochs.")
    parser.add_argument("--batch", type=int, default=16, help="Training batch size.")
    parser.add_argument("--imgsz", type=int, default=512, help="Training image resolution.")
    parser.add_argument("--patience", type=int, default=60, help="Early-stopping patience.")
    parser.add_argument("--device", type=str, default=None, help="Training device override (cuda or cpu).")
    parser.add_argument("--workers", type=int, default=8, help="Number of dataloader workers.")
    parser.add_argument("--optimizer", type=str, default="AdamW", help="Optimizer to use (SGD/Adam/AdamW).")
    parser.add_argument("--learning-rate", type=float, default=0.0005, help="Initial learning rate.")
    parser.add_argument("--warmup-epochs", type=float, default=3.0, help="Warmup epochs.")
    parser.add_argument("--cos-lr", action="store_true", help="Enable cosine learning-rate schedule.")
    parser.add_argument("--mosaic", type=float, default=0.7, help="Mosaic augmentation probability.")
    parser.add_argument("--mixup", type=float, default=0.1, help="Mixup augmentation probability.")
    parser.add_argument("--degrees", type=float, default=20.0, help="Rotation augmentation (degrees).")
    parser.add_argument("--translate", type=float, default=0.15, help="Translation augmentation factor.")
    parser.add_argument("--scale", type=float, default=0.3, help="Random scale augmentation factor.")
    parser.add_argument("--fliplr", type=float, default=0.5, help="Left-right flip probability.")
    parser.add_argument("--shear", type=float, default=0.0, help="Shear augmentation factor.")
    parser.add_argument("--hsv-h", type=float, default=0.015, help="HSV hue augmentation gain.")
    parser.add_argument("--hsv-s", type=float, default=0.7, help="HSV saturation augmentation gain.")
    parser.add_argument("--hsv-v", type=float, default=0.4, help="HSV value augmentation gain.")
    parser.add_argument("--weight-decay", type=float, default=0.0005, help="Weight decay regularization strength.")
    parser.add_argument("--label-smoothing", type=float, default=0.0, help="Label smoothing factor.")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    device = _default_device(args.device)
    LOGGER.info("Resolved training device: %s", device)

    metrics = train_pole_detector(
        data_yaml=args.data,
        model_name=args.model,
        output_name=args.output_name,
        epochs=args.epochs,
        batch_size=args.batch,
        img_size=args.imgsz,
        patience=args.patience,
        device=device,
        workers=args.workers,
        optimizer=args.optimizer,
        learning_rate=args.learning_rate,
        warmup_epochs=args.warmup_epochs,
        cos_lr=args.cos_lr,
        augment_mosaic=args.mosaic,
        augment_mixup=args.mixup,
        augment_degrees=args.degrees,
        augment_translate=args.translate,
        augment_scale=args.scale,
        augment_fliplr=args.fliplr,
        augment_shear=args.shear,
        hsv_h=args.hsv_h,
        hsv_s=args.hsv_s,
        hsv_v=args.hsv_v,
        weight_decay=args.weight_decay,
        label_smoothing=args.label_smoothing,
    )

    LOGGER.info("")
    LOGGER.info("✅ Training completed successfully.")
    LOGGER.info("   Best checkpoint: %s", metrics["best_weights"])
    LOGGER.info("   Final pipeline weight: %s", metrics["final_model"])
    LOGGER.info("   mAP50: %.2f%% | mAP50-95: %.2f%% | Precision: %.2f%% | Recall: %.2f%%",
                metrics["map50"] * 100,
                metrics["map50_95"] * 100,
                metrics["precision"] * 100,
                metrics["recall"] * 100)


if __name__ == "__main__":
    main()
