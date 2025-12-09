"""Compare YOLO validation predictions with direct inference on sample images."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import List

import numpy as np
from PIL import Image, ImageDraw
from ultralytics import YOLO

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("inspect-detector")


def load_val_predictions(pred_dir: Path, image_name: str) -> List[List[float]]:
    label_path = pred_dir / f"{Path(image_name).stem}.txt"
    if not label_path.exists():
        LOGGER.warning("No prediction file for %s", image_name)
        return []
    preds = []
    for line in label_path.read_text().strip().splitlines():
        if not line:
            continue
        cls, cx, cy, w, h, conf = map(float, line.split())
        preds.append([cx, cy, w, h, conf])
    return preds


def draw_boxes(image_path: Path, preds: List[List[float]], output_path: Path) -> None:
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    width, height = img.size
    for cx, cy, w, h, conf in preds:
        box_w = w * width
        box_h = h * height
        x1 = (cx * width) - box_w / 2
        y1 = (cy * height) - box_h / 2
        x2 = x1 + box_w
        y2 = y1 + box_h
        draw.rectangle([x1, y1, x2, y2], outline=(0, 255, 0), width=3)
        draw.text((x1, y1), f"{conf:.2f}", fill=(0, 255, 0))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)
    LOGGER.info("Wrote overlay to %s", output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect YOLO validation predictions vs direct inference")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--pred-dir", type=Path, required=True, help="Directory with val predictions (txt)")
    parser.add_argument("--output", type=Path, default=Path("runs/debug/overlay.png"))
    parser.add_argument("--conf", type=float, default=0.01)
    args = parser.parse_args()

    preds = load_val_predictions(args.pred_dir, args.image.name)
    if preds:
        draw_boxes(args.image, preds, args.output)
    else:
        LOGGER.warning("No validation predictions found for %s", args.image)

    LOGGER.info("Running direct inference with conf %.3f", args.conf)
    model = YOLO(args.model)
    results = model.predict(str(args.image), conf=args.conf, verbose=False)
    counts = sum(len(r.boxes) if r.boxes is not None else 0 for r in results)
    LOGGER.info("Direct inference boxes: %d", counts)
    if results and results[0].boxes is not None and results[0].boxes.data is not None:
        LOGGER.info("First boxes tensor: %s", results[0].boxes.data.cpu().numpy())
    else:
        LOGGER.info("No boxes returned by direct inference")


if __name__ == "__main__":
    main()
