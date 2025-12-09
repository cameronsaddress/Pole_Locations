#!/usr/bin/env python
"""
Quick spatial audit comparing AI detections against historical pole records.

Outputs precision/recall style metrics plus per-record distance tables so we
can understand detector performance immediately after each training run.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.warp import transform_bounds
from scipy.spatial import cKDTree
from shapely.geometry import Point, box
from shapely.ops import unary_union
from pyproj import CRS, Transformer

LOGGER = logging.getLogger("ai-match-audit")


@dataclass
class MatchResults:
    recall: float
    precision: float
    historical_total: int
    detections_total: int
    matched_historical: int
    matched_detections: int
    threshold_m: float
    historical_distances: np.ndarray
    detection_distances: np.ndarray
    historical_matches: pd.DataFrame
    detection_matches: pd.DataFrame


def load_historical(path: Path) -> gpd.GeoDataFrame:
    df = pd.read_csv(path)
    if not {"lat", "lon"}.issubset(df.columns):
        raise ValueError(f"Historical data must contain 'lat' and 'lon'. Columns: {df.columns.tolist()}")
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["lon"], df["lat"]),
        crs="EPSG:4326",
    )
    return gdf


def load_detections(path: Path, source_column: Optional[str], source_values: Optional[list[str]]) -> gpd.GeoDataFrame:
    df = pd.read_csv(path)
    if df.empty:
        raise ValueError(f"Detections file {path} is empty – run inference first.")
    if not {"lat", "lon"}.issubset(df.columns):
        raise ValueError(f"Detections must contain 'lat' and 'lon'. Columns: {df.columns.tolist()}")
    if source_column:
        if source_column not in df.columns:
            LOGGER.warning("Source column '%s' not found in detections; skipping filter.", source_column)
        elif source_values:
            df = df[df[source_column].isin(source_values)].copy()
            LOGGER.info("Filtered detections to %d rows matching %s in '%s'", len(df), source_values, source_column)
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["lon"], df["lat"]),
        crs="EPSG:4326",
    )
    return gdf


def build_imagery_coverage(tile_dir: Optional[Path]) -> Optional[gpd.GeoSeries]:
    if tile_dir is None:
        return None
    tifs = sorted(tile_dir.glob("*.tif"))
    if not tifs:
        LOGGER.warning("No imagery tiles found under %s; skipping coverage clipping.", tile_dir)
        return None

    polygons = []
    for tif in tifs:
        try:
            with rasterio.open(tif) as src:
                bounds = src.bounds
                src_crs = src.crs or "EPSG:4326"
                minx, miny, maxx, maxy = bounds
                if src_crs and src_crs.to_string() != "EPSG:4326":
                    minx, miny, maxx, maxy = transform_bounds(src_crs, "EPSG:4326", minx, miny, maxx, maxy)
        except Exception as exc:
            LOGGER.warning("Failed to read bounds from %s: %s", tif, exc)
            continue
        polygons.append(box(minx, miny, maxx, maxy))

    if not polygons:
        LOGGER.warning("Unable to derive coverage polygons from tiles in %s.", tile_dir)
        return None

    coverage = unary_union(polygons)
    return gpd.GeoSeries([coverage], crs="EPSG:4326")


def project_to_metric(gdf: gpd.GeoDataFrame) -> tuple[np.ndarray, np.ndarray, CRS]:
    if gdf.empty:
        raise ValueError("Cannot project empty GeoDataFrame.")
    try:
        metric_crs = gdf.estimate_utm_crs()
    except Exception:  # pragma: no cover - defensive
        metric_crs = None
    if metric_crs is None:
        metric_crs = CRS.from_epsg(3857)
    transformer = Transformer.from_crs(gdf.crs, metric_crs, always_xy=True)
    xs, ys = transformer.transform(gdf.geometry.x.to_numpy(), gdf.geometry.y.to_numpy())
    return np.column_stack([xs, ys]), transformer, metric_crs


def compute_matches(
    historical_gdf: gpd.GeoDataFrame,
    detections_gdf: gpd.GeoDataFrame,
    threshold_m: float,
) -> MatchResults:
    hist_coords, hist_transformer, metric_crs = project_to_metric(historical_gdf)
    if detections_gdf.empty:
        detection_distances = np.array([])
        historical_distances = np.full(len(historical_gdf), np.inf)
        matched_hist_mask = np.zeros(len(historical_gdf), dtype=bool)
        matches_df = historical_gdf.assign(
            nearest_detection_id=None,
            nearest_detection_conf=None,
            distance_m=historical_distances,
        )
        detection_matches = detections_gdf.assign(
            nearest_pole_id=None,
            distance_m=np.inf,
        )
        return MatchResults(
            recall=0.0,
            precision=0.0,
            historical_total=len(historical_gdf),
            detections_total=0,
            matched_historical=0,
            matched_detections=0,
            threshold_m=threshold_m,
            historical_distances=historical_distances,
            detection_distances=detection_distances,
            historical_matches=matches_df,
            detection_matches=detection_matches,
        )

    det_coords = np.column_stack(
        Transformer.from_crs(detections_gdf.crs, metric_crs, always_xy=True).transform(
            detections_gdf.geometry.x.to_numpy(),
            detections_gdf.geometry.y.to_numpy(),
        )
    )

    hist_to_det_tree = cKDTree(det_coords)
    historical_distances, nearest_det_idx = hist_to_det_tree.query(hist_coords, k=1)
    matched_hist_mask = historical_distances <= threshold_m

    det_to_hist_tree = cKDTree(hist_coords)
    detection_distances, nearest_hist_idx = det_to_hist_tree.query(det_coords, k=1)
    matched_det_mask = detection_distances <= threshold_m

    matches_df = historical_gdf.copy()
    matches_df["distance_m"] = historical_distances
    matches_df["matched"] = matched_hist_mask
    matches_df["nearest_detection_id"] = detections_gdf.iloc[nearest_det_idx]["pole_id"].to_numpy()
    matches_df["nearest_detection_conf"] = detections_gdf.iloc[nearest_det_idx].get("confidence", pd.Series([None]*len(nearest_det_idx))).to_numpy()

    detection_matches = detections_gdf.copy()
    detection_matches["distance_m"] = detection_distances
    detection_matches["matched"] = matched_det_mask
    detection_matches["nearest_pole_id"] = historical_gdf.iloc[nearest_hist_idx]["pole_id"].to_numpy()

    recall = float(matched_hist_mask.sum() / len(historical_gdf)) if len(historical_gdf) else 0.0
    precision = float(matched_det_mask.sum() / len(detections_gdf)) if len(detections_gdf) else 0.0

    return MatchResults(
        recall=recall,
        precision=precision,
        historical_total=len(historical_gdf),
        detections_total=len(detections_gdf),
        matched_historical=int(matched_hist_mask.sum()),
        matched_detections=int(matched_det_mask.sum()),
        threshold_m=threshold_m,
        historical_distances=historical_distances,
        detection_distances=detection_distances,
        historical_matches=matches_df,
        detection_matches=detection_matches,
    )


def summarize(results: MatchResults) -> dict[str, float | int]:
    def pct(value: int, total: int) -> float:
        return float(value / total * 100.0) if total else 0.0

    hist_distances = results.historical_distances[np.isfinite(results.historical_distances)]
    det_distances = results.detection_distances[np.isfinite(results.detection_distances)]

    summary = {
        "historical_total": results.historical_total,
        "detections_total": results.detections_total,
        "matched_historical": results.matched_historical,
        "matched_detections": results.matched_detections,
        "recall": results.recall,
        "recall_pct": pct(results.matched_historical, results.historical_total),
        "precision": results.precision,
        "precision_pct": pct(results.matched_detections, results.detections_total),
        "threshold_m": results.threshold_m,
        "historical_median_distance": float(np.median(hist_distances)) if hist_distances.size else float("nan"),
        "historical_p95_distance": float(np.percentile(hist_distances, 95)) if hist_distances.size else float("nan"),
        "detection_median_distance": float(np.median(det_distances)) if det_distances.size else float("nan"),
        "detection_p95_distance": float(np.percentile(det_distances, 95)) if det_distances.size else float("nan"),
    }
    return summary


def print_summary(summary: dict[str, float | int]) -> None:
    LOGGER.info("=== AI Match Audit ===")
    LOGGER.info("Historical poles (in coverage): %d", summary["historical_total"])
    LOGGER.info("AI detections:                 %d", summary["detections_total"])
    LOGGER.info(
        "Recall:    %.2f%% (%d matched within %.1fm)",
        summary["recall_pct"],
        summary["matched_historical"],
        summary["threshold_m"],
    )
    LOGGER.info(
        "Precision: %.2f%% (%d matched within %.1fm)",
        summary["precision_pct"],
        summary["matched_detections"],
        summary["threshold_m"],
    )
    LOGGER.info(
        "Historical distance median / p95: %.2fm / %.2fm",
        summary["historical_median_distance"],
        summary["historical_p95_distance"],
    )
    LOGGER.info(
        "Detection distance median / p95:  %.2fm / %.2fm",
        summary["detection_median_distance"],
        summary["detection_p95_distance"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit AI detections against historical poles.")
    parser.add_argument("--detections", type=Path, default=Path("data/processed/ai_detections.csv"), help="CSV of AI detections (requires lat/lon).")
    parser.add_argument("--historical", type=Path, default=Path("data/raw/osm_poles_harrisburg_real.csv"), help="Historical pole inventory CSV with lat/lon columns.")
    parser.add_argument("--coverage-tiles", type=Path, default=Path("data/imagery/naip_tiles"), help="Directory of NAIP imagery tiles (.tif) to determine coverage.")
    parser.add_argument("--threshold-m", type=float, default=30.0, help="Distance threshold in meters for considering a match.")
    parser.add_argument("--source-column", type=str, default="source", help="Column used to filter real detections (set empty string to disable).")
    parser.add_argument("--source-filter", type=str, nargs="+", default=["ai_detection"], help="Allowed values in the source column (ignored if source-column missing/empty).")
    parser.add_argument("--export-prefix", type=Path, help="Optional path prefix for exporting match tables (will create *_historical.csv and *_detections.csv).")
    parser.add_argument("--metrics-json", type=Path, help="Optional JSON file to write the summary metrics.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    LOGGER.info("Loading historical poles from %s", args.historical)
    historical = load_historical(args.historical)

    coverage = build_imagery_coverage(args.coverage_tiles)
    if coverage is not None:
        LOGGER.info("Clipping historical poles to imagery coverage")
        historical = historical[historical.geometry.within(coverage.iloc[0])].reset_index(drop=True)

    LOGGER.info("Historical poles after coverage clip: %d", len(historical))

    LOGGER.info("Loading AI detections from %s", args.detections)
    source_column = args.source_column or None
    source_values = args.source_filter if args.source_filter else None
    detections = load_detections(args.detections, source_column, source_values)
    LOGGER.info("Detections loaded: %d", len(detections))

    results = compute_matches(historical, detections, args.threshold_m)
    summary = summarize(results)
    print_summary(summary)

    if args.metrics_json:
        args.metrics_json.parent.mkdir(parents=True, exist_ok=True)
        with args.metrics_json.open("w", encoding="utf-8") as fp:
            json.dump(summary, fp, indent=2)
        LOGGER.info("Wrote summary metrics to %s", args.metrics_json)

    if args.export_prefix:
        args.export_prefix.parent.mkdir(parents=True, exist_ok=True)
        hist_path = args.export_prefix.with_name(args.export_prefix.name + "_historical.csv")
        det_path = args.export_prefix.with_name(args.export_prefix.name + "_detections.csv")
        results.historical_matches.to_csv(hist_path, index=False)
        results.detection_matches.to_csv(det_path, index=False)
        LOGGER.info("Exported historical matches to %s", hist_path)
        LOGGER.info("Exported detection matches to %s", det_path)


if __name__ == "__main__":
    main()
