"""
Extract REAL pole image crops from NAIP imagery using OSM pole coordinates
Creates training dataset for YOLOv8 pole detection model
"""
import argparse
import json
import logging
import math
import random
import shutil
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Union

import numpy as np
import pandas as pd
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.windows import Window

sys.path.append(str(Path(__file__).parent.parent))
from config import IMAGERY_DIR, RAW_DATA_DIR, PROCESSED_DATA_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _normalize_imagery_inputs(
    imagery_input: Union[Path, str, Sequence[Union[Path, str]]]
) -> List[Path]:
    """
    Normalize imagery inputs into a list of GeoTIFF paths.
    Accepts a single path, directory, or iterable of paths.
    """

    def _expand(path_like: Union[Path, str]) -> List[Path]:
        path_obj = Path(path_like)
        if path_obj.is_dir():
            return sorted(path_obj.glob("*.tif"))
        return [path_obj]

    if isinstance(imagery_input, (str, Path)):
        return _expand(imagery_input)

    if isinstance(imagery_input, Iterable):
        paths: List[Path] = []
        for item in imagery_input:
            paths.extend(_expand(item))
        # Remove duplicates while preserving order
        unique_paths = []
        seen = set()
        for p in paths:
            if p not in seen:
                unique_paths.append(p)
                seen.add(p)
        return unique_paths

    raise TypeError(f"Unsupported imagery input type: {type(imagery_input)}")


def extract_pole_crops(
    imagery_path: Union[Path, Sequence[Union[Path, str]], str],
    poles_csv: Path,
    output_dir: Path,
    crop_size: int = 256,
    poles_df: Optional[pd.DataFrame] = None,
    negatives_per_pole: float = 0.0,
    negative_min_distance_m: float = 25.0,
    negative_attempts_multiplier: int = 8,
    random_seed: int = 42,
    min_negatives_per_tile: int = 0,
    jitter_repeats: int = 0,
    jitter_max_offset_px: int = 96,
):
    """
    Extract image crops around real pole locations

    Args:
        imagery_path: Path to NAIP GeoTIFF, directory of tiles, or list of paths
        poles_csv: Path to OSM poles CSV with lat/lon
        output_dir: Directory to save crops
        crop_size: Size of crop in pixels (default 100x100)
    """
    logger.info("=" * 80)
    logger.info("EXTRACTING REAL POLE CROPS FROM NAIP IMAGERY")
    logger.info("=" * 80)

    imagery_paths = _normalize_imagery_inputs(imagery_path)
    if not imagery_paths:
        raise FileNotFoundError(f"No GeoTIFF tiles found under {imagery_path}")

    for path in imagery_paths:
        if not path.exists():
            raise FileNotFoundError(f"Imagery tile not found: {path}")

    logger.info(f"Poles CSV: {poles_csv}")
    logger.info(f"Crop size: {crop_size}x{crop_size} pixels")
    logger.info(f"Imagery tiles: {len(imagery_paths)}")
    for path in imagery_paths:
        logger.info(f"  - {path}")
    logger.info("")

    # Create output directories
    images_dir = output_dir / 'images'
    labels_dir = output_dir / 'labels'
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    # Load pole coordinates
    if poles_df is None:
        logger.info("Loading pole coordinates…")
        poles_df = pd.read_csv(poles_csv)
    logger.info(f"✓ Loaded {len(poles_df):,} poles")

    logger.info("\nInspecting imagery tiles…")
    tile_infos = []
    for tile_path in imagery_paths:
        with rasterio.open(tile_path) as src:
            logger.info(
                f"✓ {tile_path.name}: {src.width}x{src.height}px, "
                f"CRS={src.crs}, res={src.res[0]:.3f}m"
            )
            tile_infos.append({
                "path": tile_path,
                "bounds": src.bounds,
                "crs": src.crs,
                "transformer": Transformer.from_crs("EPSG:4326", src.crs, always_xy=True),
                "resolution": float(src.res[0]),
                "positive_xy": [],
                "negatives": 0,
            })

    if not tile_infos:
        raise RuntimeError("No imagery metadata available; aborting extraction.")

    augment_counts = {info['path'].name: 0 for info in tile_infos}

    extracted = 0
    outside_bounds = 0
    invalid_crops = 0
    per_tile_counts = {info['path'].name: 0 for info in tile_infos}

    rng = random.Random(random_seed)

    logger.info("\nExtracting crops…")

    for _, pole in poles_df.iterrows():
        pole_id = pole['pole_id']
        lat, lon = pole['lat'], pole['lon']

        tile_match = None
        projected_xy = None

        for tile_info in tile_infos:
            transformer = tile_info['transformer']
            x, y = transformer.transform(lon, lat)
            bounds = tile_info['bounds']
            if bounds.left <= x <= bounds.right and bounds.bottom <= y <= bounds.top:
                tile_match = tile_info
                projected_xy = (x, y)
                break

        if tile_match is None or projected_xy is None:
            outside_bounds += 1
            continue

        offsets = [(0, 0)]
        for _ in range(jitter_repeats):
            dx = rng.randint(-jitter_max_offset_px, jitter_max_offset_px)
            dy = rng.randint(-jitter_max_offset_px, jitter_max_offset_px)
            offsets.append((dx, dy))

        try:
            with rasterio.open(tile_match['path']) as src:
                base_row, base_col = src.index(*projected_xy)

                if (base_row < 0 or base_row >= src.height or
                    base_col < 0 or base_col >= src.width):
                    outside_bounds += 1
                    continue

                aug_index = 0

                for offset_idx, (off_x, off_y) in enumerate(offsets):
                    center_col = base_col + off_x
                    center_row = base_row + off_y

                    if (center_row < 0 or center_row >= src.height or
                        center_col < 0 or center_col >= src.width):
                        outside_bounds += 1
                        continue

                    half_size = crop_size // 2
                    col_off = max(0, center_col - half_size)
                    row_off = max(0, center_row - half_size)

                    col_size = min(crop_size, src.width - col_off)
                    row_size = min(crop_size, src.height - row_off)

                    if col_size < crop_size * 0.8 or row_size < crop_size * 0.8:
                        invalid_crops += 1
                        continue

                    window = Window(col_off, row_off, col_size, row_size)
                    try:
                        crop = src.read([1, 2, 3], window=window)
                    except rasterio.errors.RasterioIOError as exc:
                        logger.warning(
                            "Failed to read crop for %s in %s offset (%d,%d): %s",
                            pole_id, tile_match['path'].name, off_x, off_y, exc
                        )
                        invalid_crops += 1
                        continue

                    crop = np.transpose(crop, (1, 2, 0))
                    if crop.mean() < 10 or crop.mean() > 245:
                        invalid_crops += 1
                        continue

                    local_x = center_col - col_off
                    local_y = center_row - row_off
                    center_x = local_x / float(col_size)
                    center_y = local_y / float(row_size)

                    if not (0.0 <= center_x <= 1.0 and 0.0 <= center_y <= 1.0):
                        invalid_crops += 1
                        continue

                    suffix = f"_aug{aug_index}" if offset_idx > 0 else ""
                    img_filename = f"{pole_id}{suffix}.png"
                    Image.fromarray(crop.astype(np.uint8)).save(images_dir / img_filename)

                    width = 13.0 / crop_size
                    height = 20.0 / crop_size
                    (labels_dir / f"{pole_id}{suffix}.txt").write_text(
                        f"0 {center_x:.6f} {center_y:.6f} {width:.6f} {height:.6f}\n"
                    )

                    tile_match['positive_xy'].append(projected_xy)

                    extracted += 1
                    per_tile_counts[tile_match['path'].name] += 1
                    if offset_idx > 0:
                        augment_counts[tile_match['path'].name] += 1
                        aug_index += 1

                if extracted and extracted % 250 == 0:
                    logger.info(f"  Extracted {extracted:,} crops…")

        except Exception as exc:
            logger.warning(f"Failed to process {pole_id} in {tile_match['path'].name}: {exc}")
            invalid_crops += 1
            continue

    negatives_generated = 0
    if negatives_per_pole > 0:
        logger.info("\nGenerating hard negatives…")
        min_dist_sq = (negative_min_distance_m ** 2)
        for tile_info in tile_infos:
            positives_xy = np.array(tile_info["positive_xy"])
            with rasterio.open(tile_info["path"]) as src:
                if positives_xy.size == 0:
                    target_negatives = max(min_negatives_per_tile, 0)
                else:
                    target_negatives = max(
                        int(math.ceil(len(positives_xy) * negatives_per_pole)),
                        min_negatives_per_tile,
                    )

                generated_for_tile = 0
                attempts = 0
                max_attempts = max(target_negatives * negative_attempts_multiplier, 10)

                while generated_for_tile < target_negatives and attempts < max_attempts:
                    attempts += 1
                    row = rng.randint(crop_size // 2, src.height - crop_size // 2 - 1)
                    col = rng.randint(crop_size // 2, src.width - crop_size // 2 - 1)
                    x, y = src.xy(row, col)

                    if positives_xy.size > 0:
                        dists_sq = ((positives_xy[:, 0] - x) ** 2 + (positives_xy[:, 1] - y) ** 2)
                        if float(dists_sq.min()) < min_dist_sq:
                            continue

                    half_size = crop_size // 2
                    col_off = col - half_size
                    row_off = row - half_size
                    window = Window(col_off, row_off, crop_size, crop_size)
                    crop = src.read([1, 2, 3], window=window)
                    crop = np.transpose(crop, (1, 2, 0))
                    if crop.mean() < 15 or crop.mean() > 240:
                        continue

                    neg_name = f"neg_{tile_info['path'].stem}_{generated_for_tile + 1 + tile_info['negatives']}"
                    Image.fromarray(crop.astype(np.uint8)).save(images_dir / f"{neg_name}.png")
                    # Empty label file denotes background sample
                    (labels_dir / f"{neg_name}.txt").write_text("")

                    generated_for_tile += 1
                    negatives_generated += 1

                tile_info["negatives"] += generated_for_tile
                if generated_for_tile < target_negatives:
                    logger.info(
                        "  • %s: requested %d negatives, generated %d (limited by attempts)",
                        tile_info["path"].name,
                        target_negatives,
                        generated_for_tile,
                    )

    logger.info("\n" + "=" * 80)
    logger.info("EXTRACTION COMPLETE")
    logger.info("=" * 80)
    logger.info(f"✓ Successfully extracted: {extracted:,} crops")
    logger.info(f"  Outside imagery bounds: {outside_bounds:,}")
    logger.info(f"  Invalid crops (too small/blank): {invalid_crops:,}")
    for tile_name, count in per_tile_counts.items():
        logger.info(f"  • {tile_name}: {count:,} crops")
        if augment_counts.get(tile_name):
            logger.info(f"    ↳ augmentations: {augment_counts[tile_name]:,}")
    logger.info(f"\n✓ Images saved to: {images_dir}")
    logger.info(f"✓ Labels saved to: {labels_dir}")

    logger.info(f"  Hard negatives generated: {negatives_generated:,}")
    dataset_resolution = tile_infos[0]['resolution']
    yaml_content = f"""# Utility Pole Detection Dataset (REAL DATA)
# Source: OSM poles + NAIP imagery
# Location: Harrisburg, PA
# Date: {poles_csv.stat().st_mtime}

path: {output_dir.absolute()}
train: images
val: images  # Will split later

nc: 1  # Number of classes
names: ['utility_pole']

# Dataset stats
total_images: {extracted + negatives_generated}
image_size: {crop_size}
resolution: {dataset_resolution:.3f}m/pixel
augmentations_per_pole: {jitter_repeats}
"""

    yaml_path = output_dir / 'dataset.yaml'
    yaml_path.write_text(yaml_content)
    logger.info(f"✓ Dataset config: {yaml_path}")

    metadata = {
        "total_poles": len(poles_df),
        "extracted_crops": extracted,
        "outside_bounds": outside_bounds,
        "invalid_crops": invalid_crops,
        "crop_size": crop_size,
        "imagery_tiles": [str(info["path"]) for info in tile_infos],
        "tile_counts": per_tile_counts,
        "poles_csv": str(poles_csv),
        "imagery_crs": [str(info["crs"]) for info in tile_infos],
        "resolution_meters": dataset_resolution,
        "negatives_generated": negatives_generated,
        "negatives_per_tile": {
            info["path"].name: int(info.get("negatives", 0)) for info in tile_infos
        },
        "negatives_per_pole": negatives_per_pole,
        "negative_min_distance_m": negative_min_distance_m,
        "random_seed": random_seed,
        "augment_counts": augment_counts,
        "jitter_repeats": jitter_repeats,
        "jitter_max_offset_px": jitter_max_offset_px,
    }

    metadata_path = output_dir / 'extraction_metadata.json'
    metadata_path.write_text(json.dumps(metadata, indent=2))
    logger.info(f"✓ Metadata: {metadata_path}")

    logger.info("\n🎯 Next Steps:")
    logger.info("  1. Review sample crops to verify pole visibility")
    logger.info("  2. Split dataset into train/val (80/20)")
    logger.info("  3. Train YOLOv8: yolo train data=dataset.yaml model=yolov8n.pt epochs=100")

    return extracted


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract pole crops from NAIP imagery")
    parser.add_argument(
        "--imagery",
        type=str,
        nargs="+",
        default=[str(IMAGERY_DIR / "naip_mosaic.tif")],
        help="Path(s) to GeoTIFF tiles or directories (NAIP, PAMAP, etc.)",
    )
    parser.add_argument(
        "--poles",
        type=Path,
        default=RAW_DATA_DIR / "osm_poles_harrisburg_real.csv",
        help="CSV containing pole coordinates",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROCESSED_DATA_DIR / "pole_training_dataset",
        help="Output directory for crops and labels",
    )
    parser.add_argument("--crop-size", type=int, default=256, help="Crop size in pixels")
    parser.add_argument("--clean", action="store_true", help="Remove existing dataset before extraction")
    parser.add_argument(
        "--negatives-per-pole",
        type=float,
        default=0.0,
        help="How many hard negatives to sample per positive pole (0 disables negatives).",
    )
    parser.add_argument(
        "--negative-min-distance",
        type=float,
        default=25.0,
        help="Minimum distance in meters from any known pole when sampling negatives.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=42,
        help="Random seed for reproducible sampling.",
    )
    parser.add_argument(
        "--min-negatives-per-tile",
        type=int,
        default=0,
        help="Ensure at least this many negatives per tile when negatives are enabled.",
    )
    parser.add_argument(
        "--jitter-repeats",
        type=int,
        default=0,
        help="Number of additional jittered crops to create for each pole.",
    )
    parser.add_argument(
        "--jitter-max-offset",
        type=int,
        default=96,
        help="Maximum pixel offset (applied to both axes) for jittered crops.",
    )
    args = parser.parse_args()

    imagery_inputs = [Path(p) for p in args.imagery]
    missing = [p for p in imagery_inputs if not p.exists()]
    if missing:
        logger.error("Imagery paths missing: %s", ", ".join(str(p) for p in missing))
        logger.info("Run: python src/utils/download_naip_pc.py (and/or download_pema_imagery.py)")
        sys.exit(1)

    if not args.poles.exists():
        logger.error(f"Pole CSV not found: {args.poles}")
        logger.info("Fetch real pole data before running extraction.")
        sys.exit(1)

    if args.clean and args.output.exists():
        logger.info(f"Cleaning existing dataset at {args.output}")
        for sub in ["images", "labels", "train", "val"]:
            target = args.output / sub
            if target.exists():
                shutil.rmtree(target)

    logger.info("Extracting REAL pole crops from REAL imagery…")
    extracted = extract_pole_crops(
        imagery_path=[str(p) for p in imagery_inputs] if len(imagery_inputs) > 1 else imagery_inputs[0],
        poles_csv=args.poles,
        output_dir=args.output,
        crop_size=args.crop_size,
        negatives_per_pole=args.negatives_per_pole,
        negative_min_distance_m=args.negative_min_distance,
        random_seed=args.random_seed,
        min_negatives_per_tile=args.min_negatives_per_tile,
        jitter_repeats=args.jitter_repeats,
        jitter_max_offset_px=args.jitter_max_offset,
    )

    if extracted > 0:
        logger.info(f"\n✅ SUCCESS: {extracted:,} real pole crops extracted!")
    else:
        logger.error("\n❌ FAILED: No crops extracted. Verify imagery coverage and pole coordinates.")
