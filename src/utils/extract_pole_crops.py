"""
Extract REAL pole image crops from NAIP imagery using OSM pole coordinates
Creates training dataset for YOLOv8 pole detection model
"""
import argparse
import json
import logging
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
    poles_df: Optional[pd.DataFrame] = None
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
                "resolution": float(src.res[0])
            })

    if not tile_infos:
        raise RuntimeError("No imagery metadata available; aborting extraction.")

    extracted = 0
    outside_bounds = 0
    invalid_crops = 0
    per_tile_counts = {info['path'].name: 0 for info in tile_infos}

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

        try:
            with rasterio.open(tile_match['path']) as src:
                row, col = src.index(*projected_xy)

                if (row < 0 or row >= src.height or
                    col < 0 or col >= src.width):
                    outside_bounds += 1
                    continue

                half_size = crop_size // 2
                col_off = max(0, col - half_size)
                row_off = max(0, row - half_size)

                col_size = min(crop_size, src.width - col_off)
                row_size = min(crop_size, src.height - row_off)

                if col_size < crop_size * 0.8 or row_size < crop_size * 0.8:
                    invalid_crops += 1
                    continue

                window = Window(col_off, row_off, col_size, row_size)
                crop = src.read([1, 2, 3], window=window)
        except Exception as exc:
            logger.warning(f"Failed to read crop for {pole_id} in {tile_match['path'].name}: {exc}")
            invalid_crops += 1
            continue

        crop = np.transpose(crop, (1, 2, 0))
        if crop.mean() < 10 or crop.mean() > 245:
            invalid_crops += 1
            continue

        img_filename = f"{pole_id}.png"
        img_path = images_dir / img_filename
        Image.fromarray(crop.astype(np.uint8)).save(img_path)

        # YOLO label with pole centered
        center_x = 0.5
        center_y = 0.5
        width = 13.0 / crop_size
        height = 20.0 / crop_size
        label_path = labels_dir / f"{pole_id}.txt"
        label_path.write_text(f"0 {center_x:.6f} {center_y:.6f} {width:.6f} {height:.6f}\n")

        extracted += 1
        per_tile_counts[tile_match['path'].name] += 1

        if extracted % 250 == 0:
            logger.info(f"  Extracted {extracted:,} crops…")

    logger.info("\n" + "=" * 80)
    logger.info("EXTRACTION COMPLETE")
    logger.info("=" * 80)
    logger.info(f"✓ Successfully extracted: {extracted:,} crops")
    logger.info(f"  Outside imagery bounds: {outside_bounds:,}")
    logger.info(f"  Invalid crops (too small/blank): {invalid_crops:,}")
    for tile_name, count in per_tile_counts.items():
        logger.info(f"  • {tile_name}: {count:,} crops")
    logger.info(f"\n✓ Images saved to: {images_dir}")
    logger.info(f"✓ Labels saved to: {labels_dir}")

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
total_images: {extracted}
image_size: {crop_size}
resolution: {dataset_resolution:.3f}m/pixel
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
        "resolution_meters": dataset_resolution
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
        type=Path,
        default=IMAGERY_DIR / "naip_mosaic.tif",
        help="Path to NAIP GeoTIFF covering the region",
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
    args = parser.parse_args()

    if not args.imagery.exists():
        logger.error(f"NAIP imagery not found: {args.imagery}")
        logger.info("Run: python src/utils/download_naip_pc.py")
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
        imagery_path=args.imagery,
        poles_csv=args.poles,
        output_dir=args.output,
        crop_size=args.crop_size,
    )

    if extracted > 0:
        logger.info(f"\n✅ SUCCESS: {extracted:,} real pole crops extracted!")
    else:
        logger.error("\n❌ FAILED: No crops extracted. Verify imagery coverage and pole coordinates.")
