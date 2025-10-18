"""Generate AI-only pole candidates with contextual filtering."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import geopandas as gpd
from scipy.spatial import KDTree
import json

from config import PROCESSED_DATA_DIR


WATER_LAYER_PATH = PROCESSED_DATA_DIR / "water_osm.geojson"


@dataclass
class FilterSummary:
    initial: int
    ndvi_dropped: int = 0
    confidence_dropped: int = 0
    road_distance_dropped: int = 0
    water_dropped: int = 0
    alignment_dropped: int = 0

    @property
    def remaining(self) -> int:
        return (
            self.initial
            - self.ndvi_dropped
            - self.confidence_dropped
            - self.road_distance_dropped
            - self.water_dropped
            - self.alignment_dropped
        )

    def as_dict(self) -> Dict[str, int]:
        return {
            "initial": self.initial,
            "ndvi_dropped": self.ndvi_dropped,
            "confidence_dropped": self.confidence_dropped,
            "road_distance_dropped": self.road_distance_dropped,
            "water_dropped": self.water_dropped,
            "alignment_dropped": self.alignment_dropped,
            "final": self.remaining,
        }


def _load_verified_results() -> pd.DataFrame:
    verified_path = PROCESSED_DATA_DIR / "verified_poles_multi_source.csv"
    if not verified_path.exists():
        raise FileNotFoundError(
            f"{verified_path} not found. Run the verification pipeline first."
        )

    df = pd.read_csv(verified_path)
    return df


def _normalize_numeric_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric


def _filter_by_ndvi(
    df: pd.DataFrame,
    min_ndvi: float,
    summary: FilterSummary,
) -> pd.DataFrame:
    if "ndvi" not in df.columns:
        return df

    ndvi = _normalize_numeric_series(df["ndvi"])
    mask = (ndvi.isna()) | (ndvi >= min_ndvi)
    summary.ndvi_dropped = int((~mask).sum())
    return df.loc[mask].copy()


def _filter_by_confidence(
    df: pd.DataFrame,
    min_confidence: float,
    summary: FilterSummary,
) -> pd.DataFrame:
    confidence = _normalize_numeric_series(
        df.get("ai_confidence", df.get("confidence", pd.Series(dtype=float)))
    ).fillna(0.0)

    mask = confidence >= min_confidence
    summary.confidence_dropped = int((~mask).sum())
    filtered = df.loc[mask].copy()
    filtered["ai_confidence"] = confidence.loc[mask]
    return filtered


def _filter_by_road_distance(
    df: pd.DataFrame,
    max_road_distance_m: float,
    summary: FilterSummary,
) -> pd.DataFrame:
    if max_road_distance_m is None or "road_distance_m" not in df.columns:
        return df

    distances = _normalize_numeric_series(df["road_distance_m"])
    mask = (distances.isna()) | (distances <= max_road_distance_m)
    summary.road_distance_dropped = int((~mask).sum())
    return df.loc[mask].copy()


def _filter_by_water(
    df: pd.DataFrame,
    water_path: Path,
    summary: FilterSummary,
) -> pd.DataFrame:
    if not water_path.exists() or df.empty:
        return df

    try:
        water = gpd.read_file(water_path)
    except Exception:
        return df

    if water.empty:
        return df

    water = water[["geometry"]].dropna()
    if water.empty:
        return df

    water = water.to_crs("EPSG:4326")

    # Reproject to a metric CRS for buffering accuracy
    try:
        metric_crs = water.estimate_utm_crs()
    except Exception:
        metric_crs = None

    if metric_crs:
        water_metric = water.to_crs(metric_crs)
        buffered = water_metric.buffer(10)  # 10 meters buffer
        buffered = buffered.to_crs("EPSG:4326")
    else:
        # Fallback: small angular buffer (≈5m) if projection estimation fails
        buffered = water.buffer(0.00005)

    water_union = buffered.unary_union

    points = gpd.GeoDataFrame(
        df.copy(),
        geometry=gpd.points_from_xy(df["lon"], df["lat"]),
        crs="EPSG:4326",
    )

    mask = points.geometry.apply(lambda geom: not water_union.contains(geom))
    summary.water_dropped = int((~mask).sum())

    filtered = points.loc[mask].copy()
    filtered.drop(columns="geometry", inplace=True)
    return filtered


def _filter_by_alignment(
    df: pd.DataFrame,
    radius_m: float,
    min_neighbors: int,
    min_eigen_ratio: float,
    summary: FilterSummary,
) -> pd.DataFrame:
    if df.empty or len(df) < min_neighbors + 1:
        summary.alignment_dropped = len(df)
        return df.iloc[0:0].copy()

    gdf = gpd.GeoDataFrame(
        df.copy(),
        geometry=gpd.points_from_xy(df["lon"], df["lat"]),
        crs="EPSG:4326",
    )
    try:
        metric_crs = gdf.estimate_utm_crs()
    except Exception:
        metric_crs = None

    if metric_crs is None:
        summary.alignment_dropped = 0
        return df

    metric = gdf.to_crs(metric_crs)
    coords = np.column_stack([metric.geometry.x.values, metric.geometry.y.values])
    tree = KDTree(coords)

    keep_mask = np.zeros(len(df), dtype=bool)

    for idx, point in enumerate(coords):
        neighbor_idx = tree.query_ball_point(point, r=radius_m)
        # Remove self to evaluate neighbors
        neighbor_idx = [i for i in neighbor_idx if i != idx]

        if len(neighbor_idx) < min_neighbors:
            continue

        neighbor_points = coords[[idx] + neighbor_idx]  # include self
        centered = neighbor_points - neighbor_points.mean(axis=0)
        if centered.shape[0] < 2:
            continue
        cov = np.cov(centered.T)
        if not np.isfinite(cov).all():
            continue

        try:
            eigenvals = np.linalg.eigvalsh(cov)
        except np.linalg.LinAlgError:
            continue

        eigenvals.sort()
        smallest = max(eigenvals[0], 1e-6)
        ratio = eigenvals[-1] / smallest
        if ratio >= min_eigen_ratio:
            keep_mask[idx] = True

    summary.alignment_dropped = int((~keep_mask).sum())
    filtered = df.loc[keep_mask].copy()
    return filtered


def generate_new_pole_candidates(
    min_confidence: float = 0.45,
    min_ndvi: float = -0.15,
    max_road_distance_m: float = 150.0,
    alignment_radius_m: float = 80.0,
    alignment_min_neighbors: int = 2,
    alignment_min_eigen_ratio: float = 5.0,
    water_geojson: Path = WATER_LAYER_PATH,
) -> Tuple[pd.DataFrame, FilterSummary]:
    """
    Produce AI-only pole candidates that do not overlap public pole data.
    Applies a series of contextual filters to suppress obvious false positives.
    """
    verified_df = _load_verified_results()
    ai_only = verified_df[verified_df["source"] == "ai_only"].copy()
    ai_only = ai_only.reset_index(drop=True)

    summary = FilterSummary(initial=len(ai_only))
    if ai_only.empty:
        return ai_only, summary

    filtered = _filter_by_ndvi(ai_only, min_ndvi=min_ndvi, summary=summary)
    filtered = _filter_by_confidence(filtered, min_confidence=min_confidence, summary=summary)
    filtered = _filter_by_road_distance(
        filtered,
        max_road_distance_m=max_road_distance_m,
        summary=summary,
    )
    filtered = _filter_by_water(filtered, water_geojson, summary=summary)
    filtered = _filter_by_alignment(
        filtered,
        radius_m=alignment_radius_m,
        min_neighbors=alignment_min_neighbors,
        min_eigen_ratio=alignment_min_eigen_ratio,
        summary=summary,
    )

    return filtered.reset_index(drop=True), summary


def persist_candidates(
    candidates: pd.DataFrame,
    summary: FilterSummary,
    output_csv: Path,
    output_geojson: Path,
):
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(output_csv, index=False)

    geo = gpd.GeoDataFrame(
        candidates.copy(),
        geometry=gpd.points_from_xy(candidates["lon"], candidates["lat"]),
        crs="EPSG:4326",
    )
    geo.to_file(output_geojson, driver="GeoJSON")

    summary_path = output_csv.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary.as_dict(), indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate filtered new pole candidates from AI detections")
    parser.add_argument("--min-confidence", type=float, default=0.45, help="Minimum AI confidence to retain")
    parser.add_argument("--min-ndvi", type=float, default=-0.15, help="Drop detections with NDVI below this value (likely water)")
    parser.add_argument("--max-road-distance", type=float, default=150.0, help="Drop detections farther than this distance from roads (meters)")
    parser.add_argument("--alignment-radius", type=float, default=80.0, help="Neighborhood radius for line alignment check (meters)")
    parser.add_argument("--alignment-neighbors", type=int, default=2, help="Minimum neighboring detections required for alignment")
    parser.add_argument("--alignment-ratio", type=float, default=5.0, help="Minimum eigenvalue ratio (linear structure threshold)")
    parser.add_argument("--water-geojson", type=Path, default=WATER_LAYER_PATH, help="Water polygons for masking bad detections")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROCESSED_DATA_DIR / "new_pole_candidates.csv",
        help="Output CSV path for filtered candidates",
    )
    parser.add_argument(
        "--output-geojson",
        type=Path,
        default=PROCESSED_DATA_DIR / "new_pole_candidates.geojson",
        help="Output GeoJSON path",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    candidates, summary = generate_new_pole_candidates(
        min_confidence=args.min_confidence,
        min_ndvi=args.min_ndvi,
        max_road_distance_m=args.max_road_distance,
        alignment_radius_m=args.alignment_radius,
        alignment_min_neighbors=args.alignment_neighbors,
        alignment_min_eigen_ratio=args.alignment_ratio,
        water_geojson=args.water_geojson,
    )

    persist_candidates(
        candidates,
        summary,
        output_csv=args.output,
        output_geojson=args.output_geojson,
    )

    print("New pole candidate filtering summary:")
    for key, value in summary.as_dict().items():
        print(f"- {key}: {value}")
    print(f"\nSaved {len(candidates)} candidates to {args.output}")
    print(f"GeoJSON export: {args.output_geojson}")


if __name__ == "__main__":
    main()
