"""Download PASDA/PEMA orthophotos for Pennsylvania corridors."""
import argparse
import json
import logging
from pathlib import Path
from typing import List, Tuple

import pandas as pd
import requests

import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import RAW_DATA_DIR, IMAGERY_DIR

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger("pema_downloader")

ARCGIS_EXPORT = "https://imagery.pasda.psu.edu/arcgis/rest/services/PEMAImagery2021_2023/MapServer/export"
DEFAULT_SIZE = 2048
MAX_TILE_DIM_DEG = 0.05


def _compute_bbox(pole_csv: Path, margin: float) -> Tuple[float, float, float, float]:
    df = pd.read_csv(pole_csv)
    if df.empty:
        raise ValueError("Pole CSV contains no rows")
    min_lat = df["lat"].min() - margin
    max_lat = df["lat"].max() + margin
    min_lon = df["lon"].min() - margin
    max_lon = df["lon"].max() + margin
    return min_lon, min_lat, max_lon, max_lat


def _generate_tiles(bbox: Tuple[float, float, float, float], max_dim: float) -> List[Tuple[float, float, float, float]]:
    min_lon, min_lat, max_lon, max_lat = bbox
    lon_span = max_lon - min_lon
    lat_span = max_lat - min_lat
    lon_tiles = max(1, int(lon_span // max_dim) + 1)
    lat_tiles = max(1, int(lat_span // max_dim) + 1)
    lon_step = lon_span / lon_tiles
    lat_step = lat_span / lat_tiles
    tiles: List[Tuple[float, float, float, float]] = []
    for i in range(lon_tiles):
        lon0 = min_lon + i * lon_step
        lon1 = max_lon if i == lon_tiles - 1 else lon0 + lon_step
        for j in range(lat_tiles):
            lat0 = min_lat + j * lat_step
            lat1 = max_lat if j == lat_tiles - 1 else lat0 + lat_step
            tiles.append((lon0, lat0, lon1, lat1))
    return tiles


def _download_tile(bbox: Tuple[float, float, float, float], dest: Path, size: int) -> bool:
    params = {
        "f": "image",
        "format": "tiff",
        "bbox": ",".join(f"{v:.8f}" for v in bbox),
        "bboxSR": 4326,
        "imageSR": 26918,
        "size": f"{size},{size}",
        "dpi": 96,
    }
    response = requests.get(ARCGIS_EXPORT, params=params, timeout=90)
    content_type = response.headers.get("content-type", "")
    if response.status_code != 200 or "text/html" in content_type:
        LOGGER.warning("Failed to fetch %s (status %s, type %s)", bbox, response.status_code, content_type)
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(response.content)
    return True


def main():
    parser = argparse.ArgumentParser(description="Download PEMA orthophotos covering pole extent")
    parser.add_argument("--poles", type=Path, default=RAW_DATA_DIR / "osm_poles_harrisburg_real.csv")
    parser.add_argument("--output", type=Path, default=IMAGERY_DIR / "pema_tiles")
    parser.add_argument("--margin", type=float, default=0.02, help="Margin in degrees added to pole bounding box")
    parser.add_argument("--tile-span", type=float, default=MAX_TILE_DIM_DEG, help="Tile width/height (deg)")
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE, help="Tile pixel dimension")
    parser.add_argument("--manifest", type=Path, default=IMAGERY_DIR / "pema_tiles_manifest.json")
    args = parser.parse_args()

    bbox = _compute_bbox(args.poles, args.margin)
    LOGGER.info("Bounding box degrees: %s", bbox)
    tiles = _generate_tiles(bbox, args.tile_span)
    LOGGER.info("Tiles planned: %d", len(tiles))

    records = []
    for idx, tile in enumerate(tiles, start=1):
        dest = args.output / f"pema_tile_{idx:03d}.tif"
        if dest.exists():
            LOGGER.info("Skipping existing tile %s", dest.name)
            success = True
        else:
            LOGGER.info("Fetching tile %s -> %s", tile, dest.name)
            success = _download_tile(tile, dest, args.size)
        if success:
            records.append({"index": idx, "bbox": tile, "path": str(dest)})

    if records:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(records, indent=2))
        LOGGER.info("Manifest written to %s", args.manifest)
        LOGGER.info("✓ Downloaded %d PEMA tiles", len(records))
    else:
        LOGGER.error("No orthophoto tiles downloaded; inspect logs for errors.")


if __name__ == "__main__":
    main()
