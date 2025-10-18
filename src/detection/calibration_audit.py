"""Compute pixel-to-geospatial calibration metrics for detection tiles."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import rowcol
from rasterio.warp import transform as warp_transform


def _to_dataset_coords(
    src: rasterio.io.DatasetReader,
    lon: np.ndarray,
    lat: np.ndarray,
) -> np.ndarray:
    """Convert WGS84 coordinates into dataset CRS coordinates."""
    if src.crs and src.crs.to_string() != "EPSG:4326":
        xs, ys = warp_transform("EPSG:4326", src.crs, lon, lat)
    else:
        xs, ys = lon, lat
    xs_arr = np.asarray(xs)
    ys_arr = np.asarray(ys)
    return np.vstack([xs_arr, ys_arr])


def audit_calibration_metrics(
    detections_df: pd.DataFrame,
    max_records: Optional[int] = None,
) -> pd.DataFrame:
    """
    Audit pixel<->geospatial alignment for each tile present in the detections DataFrame.

    Args:
        detections_df: DataFrame containing at least `tile_path`, `lat`, `lon`, `pixel_x`, `pixel_y`.
        max_records: Optional cap per tile to speed up audits.

    Returns:
        DataFrame summarising mean, median, and RMSE errors in meters and pixels per tile.
    """
    required_cols = {"tile_path", "lat", "lon", "pixel_x", "pixel_y"}
    if detections_df.empty or not required_cols.issubset(detections_df.columns):
        return pd.DataFrame()

    metrics: Dict[str, Dict[str, float]] = {}
    grouped = detections_df.groupby("tile_path")

    for tile_path, group in grouped:
        path_obj = Path(tile_path)
        if not path_obj.exists():
            continue
        sample = group.copy()
        if max_records is not None and len(sample) > max_records:
            sample = sample.head(max_records)

        with rasterio.open(path_obj) as src:
            coords = _to_dataset_coords(src, sample["lon"].to_numpy(), sample["lat"].to_numpy())
            rows, cols = rowcol(src.transform, coords[0], coords[1])
            rows = np.asarray(rows, dtype=float)
            cols = np.asarray(cols, dtype=float)

            pixel_x = sample["pixel_x"].to_numpy(dtype=float)
            pixel_y = sample["pixel_y"].to_numpy(dtype=float)

            dx_px = cols - pixel_x
            dy_px = rows - pixel_y

            pixel_size_x = abs(src.transform.a)
            pixel_size_y = abs(src.transform.e)

            dx_m = dx_px * pixel_size_x
            dy_m = dy_px * pixel_size_y

            dist_px = np.hypot(dx_px, dy_px)
            dist_m = np.hypot(dx_m, dy_m)

            metrics[str(path_obj)] = {
                "tile": str(path_obj.name),
                "count": float(len(sample)),
                "mean_error_px": float(np.mean(dist_px)),
                "median_error_px": float(np.median(dist_px)),
                "rmse_px": float(np.sqrt(np.mean(dist_px ** 2))),
                "mean_error_m": float(np.mean(dist_m)),
                "median_error_m": float(np.median(dist_m)),
                "rmse_m": float(np.sqrt(np.mean(dist_m ** 2))),
            }

    if not metrics:
        return pd.DataFrame()

    return pd.DataFrame(metrics.values())
