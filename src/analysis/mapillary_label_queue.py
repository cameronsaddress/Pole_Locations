#!/usr/bin/env python
"""
Generate a lightweight labeling queue for Mapillary street-level imagery.

Produces:
  - CSV with review fields (pole present, confidence, notes).
  - Contact sheet JPEG to speed up visual triage.
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import random
from pathlib import Path
from typing import Iterable, List, Tuple

from PIL import Image, ImageDraw, ImageFont
import pandas as pd

LOGGER = logging.getLogger("mapillary-label-queue")


def load_metadata(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    if "image_id" not in df.columns:
        raise ValueError(f"Expected 'image_id' column in {csv_path}")
    return df


def sample_images(meta: pd.DataFrame, limit: int, seed: int) -> pd.DataFrame:
    if limit and limit < len(meta):
        sampled = meta.sample(n=limit, random_state=seed)
    else:
        sampled = meta
    return sampled.reset_index(drop=True)


def ensure_relative_path(image_dir: Path, image_id: str) -> Path:
    candidates = list(image_dir.glob(f"{image_id}.*"))
    if not candidates:
        raise FileNotFoundError(f"No image file matching {image_id}.* under {image_dir}")
    # Prefer JPEG if multiple matches
    for ext in (".jpg", ".jpeg", ".png"):
        for candidate in candidates:
            if candidate.suffix.lower() == ext:
                return candidate
    return candidates[0]


def make_label_csv(
    sampled: pd.DataFrame,
    image_dir: Path,
    output_csv: Path,
) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    rows: List[dict] = []
    for _, row in sampled.iterrows():
        image_id = str(row["image_id"])
        image_path = ensure_relative_path(image_dir, image_id)
        rows.append(
            {
                "image_id": image_id,
                "relative_path": image_path.relative_to(image_dir.parent),
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "capture_time": row.get("capture_time"),
                "sequence_id": row.get("sequence_id"),
                "camera_type": row.get("camera_type"),
                "pole_present": "",
                "confidence": "",
                "notes": "",
            }
        )

    with output_csv.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    LOGGER.info("Wrote labeling CSV with %d rows to %s", len(rows), output_csv)


def create_contact_sheet(
    sampled: pd.DataFrame,
    image_dir: Path,
    output_path: Path,
    tile_width: int = 256,
    tile_height: int = 256,
    columns: int = 6,
    font_path: Path | None = None,
) -> None:
    count = len(sampled)
    if count == 0:
        LOGGER.warning("No images sampled; skipping contact sheet.")
        return

    rows = math.ceil(count / columns)
    sheet = Image.new("RGB", (columns * tile_width, rows * tile_height), color=(25, 25, 25))

    font = None
    if font_path and font_path.exists():
        try:
            font = ImageFont.truetype(str(font_path), size=14)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to load font %s: %s", font_path, exc)

    draw = ImageDraw.Draw(sheet)
    for idx, row in sampled.iterrows():
        image_id = str(row["image_id"])
        try:
            image_path = ensure_relative_path(image_dir, image_id)
            img = Image.open(image_path).convert("RGB")
        except Exception as exc:
            LOGGER.warning("Skipping %s due to error: %s", image_id, exc)
            continue

        img.thumbnail((tile_width, tile_height), Image.LANCZOS)
        col = idx % columns
        row_idx = idx // columns
        x = col * tile_width
        y = row_idx * tile_height
        sheet.paste(img, (x, y))

        label_text = f"{idx+1:03d} • {image_id}"
        text_y = y + tile_height - 18
        draw.rectangle([(x, text_y - 2), (x + tile_width, text_y + 18)], fill=(0, 0, 0, 200))
        draw.text((x + 5, text_y), label_text, fill=(255, 255, 255), font=font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format="JPEG", quality=90)
    LOGGER.info("Contact sheet saved to %s", output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Mapillary labeling queue assets.")
    parser.add_argument("--metadata", type=Path, default=Path("data/raw/street_level/mapillary/mapillary_metadata.csv"))
    parser.add_argument("--image-dir", type=Path, default=Path("data/raw/street_level/mapillary/images"))
    parser.add_argument("--limit", type=int, default=120, help="Maximum number of images to sample (0 = all).")
    parser.add_argument("--seed", type=int, default=321)
    parser.add_argument("--output-csv", type=Path, default=Path("outputs/labels/mapillary_label_queue.csv"))
    parser.add_argument("--contact-sheet", type=Path, default=Path("outputs/labels/mapillary_contact_sheet.jpg"))
    parser.add_argument("--columns", type=int, default=6)
    parser.add_argument("--tile-width", type=int, default=256)
    parser.add_argument("--tile-height", type=int, default=256)
    parser.add_argument("--font", type=Path, help="Optional TTF font for captions.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    LOGGER.info("Loading Mapillary metadata from %s", args.metadata)
    meta = load_metadata(args.metadata)
    LOGGER.info("Total images available: %d", len(meta))

    sampled = sample_images(meta, args.limit, args.seed)
    LOGGER.info("Sampled %d images for labeling", len(sampled))

    make_label_csv(sampled, args.image_dir, args.output_csv)
    create_contact_sheet(
        sampled,
        args.image_dir,
        args.contact_sheet,
        tile_width=args.tile_width,
        tile_height=args.tile_height,
        columns=args.columns,
        font_path=args.font,
    )


if __name__ == "__main__":
    main()
