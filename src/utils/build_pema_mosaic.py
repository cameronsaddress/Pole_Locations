"""Create a mosaic GeoTIFF from georeferenced PEMA tiles."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import rasterio
from rasterio.merge import merge

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import IMAGERY_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("pema-mosaic")


def collect_tiles(directory: Path) -> list[Path]:
    if not directory.exists():
        raise FileNotFoundError(f"Tile directory missing: {directory}")
    tiles = sorted(directory.glob("*.tif"))
    if not tiles:
        raise FileNotFoundError(f"No GeoTIFF tiles found under {directory}")
    return tiles


def build_mosaic(tiles: list[Path], output: Path) -> None:
    datasets = []
    for path in tiles:
        try:
            datasets.append(rasterio.open(path))
        except Exception as exc:
            LOGGER.warning("Skipping %s: %s", path, exc)
    if not datasets:
        raise RuntimeError("No readable tiles for mosaic")

    mosaic, transform = merge(datasets)
    meta = datasets[0].meta.copy()
    meta.update(
        {
            "driver": "GTiff",
            "height": mosaic.shape[1],
            "width": mosaic.shape[2],
            "transform": transform,
            "compress": "lzw",
        }
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output, "w", **meta) as dst:
        dst.write(mosaic)
    LOGGER.info("Wrote mosaic to %s", output)

    for ds in datasets:
        ds.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a mosaic from georeferenced PEMA tiles")
    parser.add_argument("--tiles", type=Path, default=IMAGERY_DIR / "pema_tiles")
    parser.add_argument("--output", type=Path, default=IMAGERY_DIR / "pema_mosaic.tif")
    args = parser.parse_args()

    tiles = collect_tiles(args.tiles)
    LOGGER.info("Found %d tiles", len(tiles))
    build_mosaic(tiles, args.output)


if __name__ == "__main__":
    main()
