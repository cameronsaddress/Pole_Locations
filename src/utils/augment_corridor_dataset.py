"""
Augment pole training dataset with corridor-focused positives and hard negatives.

Creates additional augmented images for poles currently flagged as "in question"
and optional background crops (empty labels) sampled near the same tiles.
"""
import argparse
import random
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd
from PIL import Image, ImageEnhance, ImageFilter
import rasterio
from rasterio.windows import Window
from pyproj import Transformer


def _load_review_dataframe(verified_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(verified_csv)
    if 'classification' not in df.columns:
        raise ValueError("verified CSV must contain a 'classification' column.")
    review_df = df[df['classification'] == 'in_question'].copy()
    if review_df.empty:
        print("Warning: no 'in_question' rows found in verified dataset.")
    required_cols = {'pole_id', 'lat', 'lon'}
    missing = required_cols - set(review_df.columns)
    if missing:
        raise ValueError(f"verified CSV missing required columns: {missing}")
    review_df['pole_id'] = review_df['pole_id'].astype(str)
    return review_df


def _augment_image(img: Image.Image) -> Image.Image:
    """Apply a random combination of augmentations while preserving size."""
    angle = random.uniform(-12, 12)
    augmented = img.rotate(angle, resample=Image.BICUBIC, expand=False)

    if random.random() < 0.7:
        factor = random.uniform(0.85, 1.15)
        augmented = ImageEnhance.Brightness(augmented).enhance(factor)

    if random.random() < 0.7:
        factor = random.uniform(0.85, 1.15)
        augmented = ImageEnhance.Contrast(augmented).enhance(factor)

    if random.random() < 0.5:
        augmented = augmented.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.0, 1.2)))

    if random.random() < 0.3:
        arr = np.asarray(augmented).astype(np.float32)
        noise = np.random.normal(0, random.uniform(3, 8), size=arr.shape)
        arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
        augmented = Image.fromarray(arr)

    return augmented


def _write_label(dst: Path, content: str):
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(content)


def _load_label(label_path: Path) -> str:
    return label_path.read_text() if label_path.exists() else ""


def _sample_background(
    tile_path: Path,
    lat: float,
    lon: float,
    crop_size: int = 256,
    min_distance_m: float = 40.0
) -> Tuple[Image.Image, bool]:
    """
    Sample a background crop near the given coordinate but offset to avoid the pole center.
    Returns (image, success flag).
    """
    try:
        with rasterio.open(tile_path) as src:
            transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            x, y = transformer.transform(lon, lat)
            row, col = src.index(x, y)

            offset_pixels = max(int(min_distance_m / float(src.res[0])), 20)
            for _ in range(6):
                row_shift = random.randint(-offset_pixels, offset_pixels)
                col_shift = random.randint(-offset_pixels, offset_pixels)
                if abs(row_shift) < offset_pixels // 2 and abs(col_shift) < offset_pixels // 2:
                    continue

                row_bg = row + row_shift
                col_bg = col + col_shift
                if row_bg < 0 or col_bg < 0 or row_bg >= src.height or col_bg >= src.width:
                    continue

                half = crop_size // 2
                row_off = max(0, row_bg - half)
                col_off = max(0, col_bg - half)
                row_size = min(crop_size, src.height - row_off)
                col_size = min(crop_size, src.width - col_off)
                if row_size < crop_size or col_size < crop_size:
                    continue

                window = Window(col_off, row_off, col_size, row_size)
                data = src.read([1, 2, 3], window=window)
                if data.size == 0:
                    continue

                img = Image.fromarray(np.transpose(data, (1, 2, 0)).astype(np.uint8))
                if 10 < np.asarray(img).mean() < 245:
                    return img, True
    except Exception:
        return Image.new("RGB", (crop_size, crop_size), color=0), False

    return Image.new("RGB", (crop_size, crop_size), color=0), False


def main():
    parser = argparse.ArgumentParser(description="Augment pole training dataset with corridor samples.")
    parser.add_argument(
        "--verified-csv",
        type=Path,
        default=Path("data/processed/verified_poles_multi_source.csv"),
        help="CSV produced by fusion validator (used to identify corridor poles)."
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("data/processed/pole_training_dataset"),
        help="Existing training dataset directory (images/ + labels/)."
    )
    parser.add_argument(
        "--imagery-dir",
        type=Path,
        default=Path("data/imagery/naip_tiles"),
        help="Directory containing NAIP GeoTIFF tiles."
    )
    parser.add_argument("--augment-per-pole", type=int, default=3, help="Augmented variants per corridor pole.")
    parser.add_argument("--backgrounds", type=int, default=400, help="Number of background crops to sample.")
    parser.add_argument("--crop-size", type=int, default=256, help="Crop size for backgrounds.")
    args = parser.parse_args()

    images_dir = args.dataset_dir / "images"
    labels_dir = args.dataset_dir / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    review_df = _load_review_dataframe(args.verified_csv)
    if review_df.empty:
        print("No in-question poles found; exiting.")
        return

    imagery_tiles = sorted(Path(args.imagery_dir).glob("*.tif"))
    if not imagery_tiles:
        print("No imagery tiles found; background sampling disabled.")

    # Augment positives
    augmented = 0
    skipped = 0
    for _, row in review_df.iterrows():
        pole_id = row['pole_id']
        img_path = images_dir / f"{pole_id}.png"
        label_path = labels_dir / f"{pole_id}.txt"
        if not img_path.exists() or not label_path.exists():
            skipped += 1
            continue

        original = Image.open(img_path)
        label_text = _load_label(label_path)

        for idx in range(args.augment_per_pole):
            aug_image = _augment_image(original)
            aug_name = f"{pole_id}_aug{idx+1}"
            aug_image_path = images_dir / f"{aug_name}.png"
            aug_label_path = labels_dir / f"{aug_name}.txt"
            aug_image.save(aug_image_path)
            _write_label(aug_label_path, label_text)
            augmented += 1

    print(f"Augmented {augmented} corridor images. Skipped missing: {skipped}")

    # Background sampling
    backgrounds_written = 0
    if imagery_tiles and args.backgrounds > 0:
        tiles_cycle = imagery_tiles.copy()

        for _ in range(args.backgrounds):
            row = review_df.sample(1).iloc[0]
            lat, lon = float(row['lat']), float(row['lon'])
            tile = random.choice(tiles_cycle)
            bg_image, ok = _sample_background(tile, lat, lon, crop_size=args.crop_size)
            if not ok:
                continue
            name = f"bg_corridor_{backgrounds_written+1}"
            bg_image.save(images_dir / f"{name}.png")
            _write_label(labels_dir / f"{name}.txt", "")
            backgrounds_written += 1
            if backgrounds_written >= args.backgrounds:
                break

    print(f"Wrote {backgrounds_written} background crops.")


if __name__ == "__main__":
    main()
