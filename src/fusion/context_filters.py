"""Enrich detection DataFrames with contextual features and filter implausible hits."""
from pathlib import Path
from typing import List, Optional, Tuple

import geopandas as gpd
import pandas as pd
import rasterio
from rasterio.errors import RasterioIOError
from rasterio.windows import Window
from shapely.geometry import Point, box
from shapely.prepared import prep
from pyproj import Transformer

from src.config import (
    PROCESSED_DATA_DIR,
    FILTER_MAX_ROAD_DISTANCE_M,
    FILTER_MIN_SURFACE_ELEV_M,
    FILTER_NDVI_LOWER,
    FILTER_NDVI_UPPER,
    FILTER_DROP_FAILURES,
)


def annotate_with_roads(
    detections_df: pd.DataFrame,
    roads_path: Optional[Path] = None,
) -> pd.DataFrame:
    """Append nearest-road distance (meters) to each detection if roads data is available."""
    if roads_path is None:
        roads_path = PROCESSED_DATA_DIR / "roads_osm.geojson"

    if not roads_path.exists() or detections_df.empty:
        detections_df = detections_df.copy()
        detections_df["road_distance_m"] = pd.NA
        return detections_df

    roads_gdf = gpd.read_file(roads_path)
    if roads_gdf.empty:
        detections_df = detections_df.copy()
        detections_df["road_distance_m"] = pd.NA
        return detections_df

    roads_gdf = roads_gdf[["geometry"]].dropna().reset_index(drop=True)
    roads_crs = roads_gdf.crs or "EPSG:4326"

    detections_gdf = gpd.GeoDataFrame(
        detections_df.copy(),
        geometry=gpd.points_from_xy(detections_df["lon"], detections_df["lat"]),
        crs="EPSG:4326",
    )

    roads_projected = roads_gdf.to_crs(roads_crs)
    detections_projected = detections_gdf.to_crs(roads_crs)

    try:
        metric_crs = roads_projected.estimate_utm_crs()
    except Exception:
        metric_crs = None

    if metric_crs:
        roads_projected = roads_projected.to_crs(metric_crs)
        detections_projected = detections_projected.to_crs(metric_crs)

    road_geoms = roads_projected.geometry
    distances = detections_projected.geometry.apply(lambda geom: float(road_geoms.distance(geom).min()))
    detections_df = detections_df.copy()
    detections_df["road_distance_m"] = distances
    return detections_df


def annotate_with_dsm(
    detections_df: pd.DataFrame,
    dsm_dir: Optional[Path] = None,
) -> pd.DataFrame:
    """Sample USGS 3DEP DSM tiles at detection points to obtain surface height."""
    if dsm_dir is None:
        dsm_dir = PROCESSED_DATA_DIR / "3dep_dsm"

    if detections_df.empty or not dsm_dir.exists() or not list(dsm_dir.glob("*.tif")):
        detections_df = detections_df.copy()
        detections_df["surface_elev_m"] = pd.NA
        return detections_df

    tiles: List[Dict] = []
    for tif in dsm_dir.glob("*.tif"):
        try:
            src = rasterio.open(tif)
        except RasterioIOError:
            continue
        bounds = src.bounds
        tiles.append({
            "path": tif,
            "src": src,
            "bounds": box(bounds.left, bounds.bottom, bounds.right, bounds.top),
            "transformer": None if src.crs and src.crs.to_string() == "EPSG:4326" else Transformer.from_crs("EPSG:4326", src.crs, always_xy=True),
        })

    def sample_height(lat: float, lon: float) -> Optional[float]:
        pt = Point(lon, lat)
        for tile in tiles:
            if not tile["bounds"].contains(pt):
                continue
            x, y = (lon, lat)
            if tile["transformer"] is not None:
                x, y = tile["transformer"].transform(lon, lat)
            try:
                row, col = tile["src"].index(x, y)
            except Exception:
                continue
            if row < 0 or col < 0 or row >= tile["src"].height or col >= tile["src"].width:
                continue
            try:
                value = tile["src"].read(1, window=Window(col, row, 1, 1))
            except RasterioIOError:
                continue
            if value.size == 0:
                continue
            val = float(value[0, 0])
            if not pd.isna(val):
                return val
        return None

    detections_df = detections_df.copy()
    detections_df["surface_elev_m"] = detections_df.apply(lambda r: sample_height(r["lat"], r["lon"]), axis=1)

    for tile in tiles:
        tile["src"].close()

    return detections_df


def annotate_with_water(
    detections_df: pd.DataFrame,
    water_path: Optional[Path] = None,
) -> pd.DataFrame:
    """Flag detections that fall inside OSM water polygons."""
    detections_df = detections_df.copy()
    if detections_df.empty:
        detections_df["in_water"] = False
        return detections_df

    if water_path is None:
        water_path = PROCESSED_DATA_DIR / "water_osm.geojson"

    if not water_path.exists():
        detections_df["in_water"] = False
        return detections_df

    water_gdf = gpd.read_file(water_path)
    if water_gdf.empty:
        detections_df["in_water"] = False
        return detections_df

    water_gdf = water_gdf.to_crs("EPSG:4326")
    water_union = prep(water_gdf.unary_union)

    detections_gdf = gpd.GeoDataFrame(
        detections_df,
        geometry=gpd.points_from_xy(detections_df["lon"], detections_df["lat"]),
        crs="EPSG:4326",
    )
    detections_gdf["in_water"] = detections_gdf.geometry.apply(water_union.contains)
    detections_gdf.drop(columns=["geometry"], inplace=True)
    return pd.DataFrame(detections_gdf)


def annotate_context_features(
    detections_df: pd.DataFrame,
    roads_path: Optional[Path] = None,
    dsm_dir: Optional[Path] = None,
    water_path: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Enrich detection DataFrame with contextual features from roads, DSM, and water layers.
    """
    annotated = annotate_with_roads(detections_df, roads_path=roads_path)
    annotated = annotate_with_dsm(annotated, dsm_dir=dsm_dir)
    annotated = annotate_with_water(annotated, water_path=water_path)
    return annotated


def filter_implausible_detections(
    detections_df: pd.DataFrame,
    max_road_distance_m: float = FILTER_MAX_ROAD_DISTANCE_M,
    min_surface_elev_m: float = FILTER_MIN_SURFACE_ELEV_M,
    ndvi_bounds: Tuple[float, float] = (FILTER_NDVI_LOWER, FILTER_NDVI_UPPER),
    drop_failures: bool = FILTER_DROP_FAILURES,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Remove detections that violate contextual heuristics.

    Returns:
        (filtered_df, dropped_df) with dropped_df containing a `filter_reasons` column.
    """
    detections_df = detections_df.copy()
    if detections_df.empty:
        detections_df["filter_reasons"] = [[] for _ in range(len(detections_df))]
        return detections_df, pd.DataFrame(columns=detections_df.columns)

    lower_ndvi, upper_ndvi = ndvi_bounds
    filtered_rows: List[pd.Series] = []
    dropped_rows: List[pd.Series] = []

    for _, row in detections_df.iterrows():
        reasons: List[str] = []

        road_distance = row.get("road_distance_m")
        if pd.notna(road_distance) and float(road_distance) > max_road_distance_m:
            reasons.append(f"road_distance>{max_road_distance_m}m")

        ndvi = row.get("ndvi")
        if pd.notna(ndvi) and not (lower_ndvi <= float(ndvi) <= upper_ndvi):
            reasons.append("ndvi_out_of_range")

        if bool(row.get("in_water", False)):
            reasons.append("in_water_polygon")

        surface_elev = row.get("surface_elev_m")
        if pd.notna(surface_elev) and float(surface_elev) < min_surface_elev_m:
            reasons.append(f"surface_elev<{min_surface_elev_m}m")

        kept_row = row.copy()
        kept_row["filter_reasons"] = reasons

        if reasons and drop_failures:
            dropped_rows.append(kept_row)
        else:
            filtered_rows.append(kept_row)

    filtered_df = pd.DataFrame(filtered_rows) if filtered_rows else pd.DataFrame(columns=detections_df.columns)
    dropped_df = pd.DataFrame(dropped_rows) if dropped_rows else pd.DataFrame(columns=detections_df.columns)
    return filtered_df, dropped_df
