"""Dual-pass pole verification runner.

1. Harvest public pole inventories (OpenStreetMap) and prep contextual layers.
2. Run the verification pipeline (historical vs AI detections).
3. Generate AI-only pole candidates with contextual filtering (water masks, linear corridors).
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd
import geopandas as gpd
import sys

# Ensure project root and src are on the import path when executed as a script
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
if str(SRC_ROOT) not in sys.path:
    sys.path.append(str(SRC_ROOT))

from config import RAW_DATA_DIR, PROCESSED_DATA_DIR  # noqa: E402
from src.utils.get_osm_poles import download_osm_poles_harrisburg  # noqa: E402
from src.utils.build_roads_layer import build_roads_layer  # noqa: E402
from src.utils.build_water_layer import build_water_layer  # noqa: E402
from src.analysis.new_pole_candidates import (  # noqa: E402
    generate_new_pole_candidates,
    persist_candidates,
    WATER_LAYER_PATH,
)
from run_pilot import run_pilot_pipeline  # noqa: E402


PUBLIC_POLES_GEOJSON = PROCESSED_DATA_DIR / "public_poles.geojson"


def _ensure_public_poles(force_refresh: bool = False) -> Path:
    poles_csv = RAW_DATA_DIR / "osm_poles_harrisburg_real.csv"
    if force_refresh or not poles_csv.exists():
        poles_csv = download_osm_poles_harrisburg()
    return poles_csv


def _export_public_geojson(poles_csv: Path, output_path: Path = PUBLIC_POLES_GEOJSON) -> Path:
    df = pd.read_csv(poles_csv)
    if df.empty:
        raise ValueError("Public pole CSV is empty; cannot create GeoJSON export.")
    gdf = gpd.GeoDataFrame(
        df.copy(),
        geometry=gpd.points_from_xy(df["lon"], df["lat"]),
        crs="EPSG:4326",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(output_path, driver="GeoJSON")
    return output_path


def _ensure_roads_layer(poles_csv: Path, force_refresh: bool = False) -> Path:
    output = PROCESSED_DATA_DIR / "roads_osm.geojson"
    if force_refresh or not output.exists():
        build_roads_layer(poles_csv, output)
    return output


def _ensure_water_layer(poles_csv: Path, force_refresh: bool = False) -> Path:
    output = WATER_LAYER_PATH
    if force_refresh or not output.exists():
        build_water_layer(poles_csv, output)
    return output


def run_dual_pass(
    refresh_public_data: bool,
    refresh_context_layers: bool,
    skip_detection: bool,
    min_confidence: float,
    min_ndvi: float,
    max_road_distance: float,
    alignment_radius: float,
    alignment_neighbors: int,
    alignment_ratio: float,
) -> None:
    print("=== Dual-Pass Pole Verification Runner ===")
    print("Step 1: Harvesting public pole data...")
    poles_csv = _ensure_public_poles(force_refresh=refresh_public_data)
    print(f"  ✓ Public poles CSV ready: {poles_csv}")
    geojson = _export_public_geojson(poles_csv)
    print(f"  ✓ Exported GeoJSON for mapping: {geojson}")

    print("\nStep 2: Building contextual layers (roads, water)...")
    roads = _ensure_roads_layer(poles_csv, force_refresh=refresh_context_layers)
    print(f"  ✓ Roads layer: {roads}")
    water = _ensure_water_layer(poles_csv, force_refresh=refresh_context_layers)
    print(f"  ✓ Water layer: {water}")

    if skip_detection:
        print("\nStep 3 skipped (detection pipeline) per user request.")
    else:
        print("\nStep 3: Running verification pipeline (public vs AI)...")
        run_pilot_pipeline()

    print("\nStep 4: Generating AI-only pole candidates with smart filtering...")
    candidates, summary = generate_new_pole_candidates(
        min_confidence=min_confidence,
        min_ndvi=min_ndvi,
        max_road_distance_m=max_road_distance,
        alignment_radius_m=alignment_radius,
        alignment_min_neighbors=alignment_neighbors,
        alignment_min_eigen_ratio=alignment_ratio,
        water_geojson=water,
    )
    output_csv = PROCESSED_DATA_DIR / "new_pole_candidates.csv"
    output_geojson = PROCESSED_DATA_DIR / "new_pole_candidates.geojson"
    persist_candidates(candidates, summary, output_csv=output_csv, output_geojson=output_geojson)

    print("\n=== Dual-Pass Summary ===")
    for key, value in summary.as_dict().items():
        print(f"- {key}: {value}")
    print(f"\nOutputs:")
    print(f"  • Public pole GeoJSON: {geojson}")
    print(f"  • Filtered AI-only candidates CSV: {output_csv}")
    print(f"  • Filtered AI-only candidates GeoJSON: {output_geojson}")
    print("\nNext steps:")
    print("  1. Load public_poles.geojson and new_pole_candidates.geojson in the dashboard map layer.")
    print("  2. Review candidate poles prioritized by contextual filters before field validation.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the dual-pass pole verification workflow")
    parser.add_argument("--refresh-public", action="store_true", help="Force refresh of public pole inventory")
    parser.add_argument("--refresh-context", action="store_true", help="Force refresh of roads/water contextual layers")
    parser.add_argument("--skip-detection", action="store_true", help="Skip running the detection pipeline (reuse existing outputs)")
    parser.add_argument("--min-confidence", type=float, default=0.45, help="Minimum AI confidence for new pole candidates")
    parser.add_argument("--min-ndvi", type=float, default=-0.15, help="Minimum NDVI (drops likely water detections)")
    parser.add_argument("--max-road-distance", type=float, default=150.0, help="Max distance from roads (meters)")
    parser.add_argument("--alignment-radius", type=float, default=80.0, help="Alignment neighborhood radius (meters)")
    parser.add_argument("--alignment-neighbors", type=int, default=2, help="Minimum neighbors required for alignment")
    parser.add_argument("--alignment-ratio", type=float, default=5.0, help="Minimum eigenvalue ratio for line structures")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dual_pass(
        refresh_public_data=args.refresh_public,
        refresh_context_layers=args.refresh_context,
        skip_detection=args.skip_detection,
        min_confidence=args.min_confidence,
        min_ndvi=args.min_ndvi,
        max_road_distance=args.max_road_distance,
        alignment_radius=args.alignment_radius,
        alignment_neighbors=args.alignment_neighbors,
        alignment_ratio=args.alignment_ratio,
    )


if __name__ == "__main__":
    main()
