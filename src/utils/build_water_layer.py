"""Download open water polygons for the pole AOI using OpenStreetMap (free)."""
import argparse
from pathlib import Path
from typing import Tuple

import osmnx as ox
import pandas as pd

from config import RAW_DATA_DIR, PROCESSED_DATA_DIR


def _compute_bbox(poles_csv: Path, margin_degrees: float = 0.02) -> Tuple[float, float, float, float]:
    df = pd.read_csv(poles_csv)
    if df.empty:
        raise ValueError("Pole CSV is empty; cannot build bounding box")

    min_lat = df["lat"].min() - margin_degrees
    max_lat = df["lat"].max() + margin_degrees
    min_lon = df["lon"].min() - margin_degrees
    max_lon = df["lon"].max() + margin_degrees
    return max_lat, min_lat, max_lon, min_lon


def build_water_layer(poles_csv: Path, output_path: Path) -> Path:
    north, south, east, west = _compute_bbox(poles_csv)
    ox.settings.log_console = True
    ox.settings.use_cache = True

    tags = {
        "natural": ["water", "wetland"],
        "water": True,
        "waterway": ["riverbank", "stream", "river"],
        "landuse": ["reservoir", "basin"]
    }

    water = ox.geometries_from_bbox(
        north,
        south,
        east,
        west,
        tags=tags
    )

    if water.empty:
        raise RuntimeError("No water features retrieved from OpenStreetMap for the requested bbox")

    water = water[["geometry"]].reset_index(drop=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    water.to_file(output_path, driver="GeoJSON")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Build an open water polygon layer for pole analysis")
    parser.add_argument(
        "--poles",
        type=Path,
        default=RAW_DATA_DIR / "osm_poles_harrisburg_real.csv",
        help="CSV with pole lat/lon used to define bounding box",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROCESSED_DATA_DIR / "water_osm.geojson",
        help="Output GeoJSON path",
    )
    args = parser.parse_args()

    result = build_water_layer(args.poles, args.output)
    print(f"Saved water layer to {result}")


if __name__ == "__main__":
    main()
