"""Enrich detection DataFrames with contextual features and filter implausible hits."""
from pathlib import Path
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

import geopandas as gpd
import pandas as pd
import rasterio
from rasterio.errors import RasterioIOError
from rasterio.windows import Window
from shapely.geometry import Point, box
from shapely.prepared import prep
from pyproj import Transformer
from shapely.strtree import STRtree

from src.config import (
    PROCESSED_DATA_DIR,
    FILTER_MAX_ROAD_DISTANCE_M,
    FILTER_MIN_SURFACE_ELEV_M,
    FILTER_NDVI_LOWER,
    FILTER_NDVI_UPPER,
    FILTER_DROP_FAILURES,
)


from src.ingestion.connectors.pasda_roads import PASDAConnector

def annotate_with_roads(
    detections_df: pd.DataFrame,
    roads_path: Optional[Path] = None,
) -> pd.DataFrame:
    """Append nearest-road distance (meters) to each detection."""
    
    # Try PASDA first (Superior for PA)
    pasda = PASDAConnector()
    if pasda.get_roads_gdf() is not None:
        roads_gdf = pasda.get_roads_gdf()
    elif roads_path is None:
        # Fallback to OSM
        roads_path = PROCESSED_DATA_DIR / "roads_osm.geojson"
        if roads_path.exists():
            roads_gdf = gpd.read_file(roads_path)
        else:
            roads_gdf = gpd.GeoDataFrame()
    else:
        roads_gdf = gpd.read_file(roads_path)

    if roads_gdf.empty or detections_df.empty:
        detections_df = detections_df.copy()
        detections_df["road_distance_m"] = pd.NA
        return detections_df
    
    # ... Rest of logic stays similar but using the selected gdf ...
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
    
    # Optimize using Spatial Index (sindex)
    # We want the distance from each detection to the NEAREST road.
    # calculate nearest geometry using sindex
    
    if road_geoms.empty:
         detections_df = detections_df.copy()
         detections_df["road_distance_m"] = pd.NA
         return detections_df

    # Ensure sindex exists
    _ = road_geoms.sindex
    
    # For every detection, find the nearest road index
    # validation: query_bulk is efficient
    # We can use geometry.distance to the nearest only
    
    # But simpler: use direct apply is slow.
    # We use nearest_points from shapely.ops? No, existing sindex method is better.
    
    # roads_projected.sindex.nearest returns indices of [input_geom_idx, tree_geom_idx]
    
    # Let's stick to a robust method:
    # 1. For each point, find the nearest items in the index (with a buffer if possible, or just nearest).
    # GeoPandas has `sindex.nearest` which is great.
    
    nearest_idxs = roads_projected.sindex.nearest(
        detections_projected.geometry, 
        return_all=False, 
        return_distance=False
    )
    # nearest_idxs is [input_indices, right_indices]
    
    # Calculate distance only to the identified nearest road
    # Map detection index to road geometry
    
    distances = []
    # nearest_idxs[0] are indices in detections_projected
    # nearest_idxs[1] are indices in roads_projected (iloc)
    
    # Sort by query index to align? No, detections_projected has an index.
    
    # Let's align them.
    # Create a Series of nearest road geometries aligned with detections
    nearest_roads = roads_projected.geometry.iloc[nearest_idxs[1]].reset_index(drop=True)
    # Align the input geoms
    input_geoms = detections_projected.geometry.iloc[nearest_idxs[0]].reset_index(drop=True)
    
    # Compute distances
    computed_dists = input_geoms.distance(nearest_roads)
    
    # Now map back to original index
    # We need to assign these distances to the ORIGINAL index of detections_df
    # nearest_idxs[0] corresponds to iloc in detections_projected.
    
    results = pd.Series(index=detections_projected.index, dtype=float)
    results.iloc[nearest_idxs[0]] = computed_dists.values
    
    detections_df = detections_df.copy()
    detections_df["road_distance_m"] = results
    return detections_df


def annotate_with_dsm(
    detections_df: pd.DataFrame,
    dsm_dir: Optional[Path] = None,
) -> pd.DataFrame:
    """Sample USGS 3DEP DSM tiles at detection points to obtain surface height."""
    if dsm_dir is None:
        dsm_dir = PROCESSED_DATA_DIR / "3dep_dsm"

    if detections_df.empty or not dsm_dir.exists():
        detections_df = detections_df.copy()
        detections_df["surface_elev_m"] = pd.NA
        return detections_df
        
    tif_files = list(dsm_dir.glob("*.tif"))
    if not tif_files:
        logger.warning(f"No DSM tiles found in {dsm_dir}")
        detections_df = detections_df.copy()
        detections_df["surface_elev_m"] = pd.NA
        return detections_df

    tiles: List[Dict] = []
    tile_geoms = []
    
    # Pre-scan tiles
    for i, tif in enumerate(dsm_dir.glob("*.tif")):
        try:
            # lightweight open just to get bounds first?
            # Rasterio open is somewhat lazy but repeated open is bad.
            # We keep them open? No, too many file descriptors.
            # Just read bounds.
            with rasterio.open(tif) as src:
                b = src.bounds
                # Create box for index (Project to 4326 if needed)
                if src.crs and src.crs.to_string() != "EPSG:4326":
                     from rasterio.warp import transform_bounds
                     # transform_bounds(src_crs, dst_crs, left, bottom, right, top)
                     left, bottom, right, top = transform_bounds(src.crs, "EPSG:4326", b.left, b.bottom, b.right, b.top)
                     geom = box(left, bottom, right, top)
                else:
                     geom = box(b.left, b.bottom, b.right, b.top)
                
                tiles.append({
                    "path": tif,
                    "src": None, 
                    "bounds": geom,
                    "crs": src.crs
                })
                tile_geoms.append(geom)

        except RasterioIOError:
            continue

    if not tiles:
        detections_df = detections_df.copy()
        detections_df["surface_elev_m"] = pd.NA
        return detections_df
        
    # Build Spatial Index
    tree = STRtree(tile_geoms)

    def sample_height(lat: float, lon: float) -> Optional[float]:
        pt = Point(lon, lat)
        
        # Query Index
        # query returns indices of geometries that intersect 'pt'
        indices = tree.query(pt, predicate="intersects")
        
        for idx in indices:
            tile = tiles[idx]
            tif_path = tile["path"]
            
            # Now open the file
            try:
                with rasterio.open(tif_path) as src:
                    transformer = None
                    if src.crs and src.crs.to_string() != "EPSG:4326":
                         transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                    
                    x, y = (lon, lat)
                    if transformer:
                        x, y = transformer.transform(lon, lat)
                        
                    try:
                        row, col = src.index(x, y)
                    except Exception:
                        continue
                        
                    if row < 0 or col < 0 or row >= src.height or col >= src.width:
                        continue
                        
                    value = src.read(1, window=Window(col, row, 1, 1))
                    if value.size == 0:
                        continue
                        
                    val = float(value[0, 0])
                    if val > -1000: # Valid data
                        return val
            except Exception:
                continue

        return None

    def calculate_local_hag(row) -> pd.Series:
        lat, lon = row["lat"], row["lon"]
        center_elev = sample_height(lat, lon)
        
        if center_elev is None:
            return pd.Series([pd.NA, pd.NA], index=["surface_elev_m", "height_ag_m"])
            
        # Sample surroundings (approx 5 meters away)
        # 1 deg lat ~= 111km -> 5m ~= 0.000045 deg
        offset = 0.000045
        surrounding_elevs = []
        for dlat, dlon in [(-offset, 0), (offset, 0), (0, -offset), (0, offset)]:
            elev = sample_height(lat + dlat, lon + dlon)
            if elev is not None:
                surrounding_elevs.append(elev)
        
        if not surrounding_elevs:
             return pd.Series([center_elev, pd.NA], index=["surface_elev_m", "height_ag_m"])
             
        # Estimate ground as the median of surroundings to avoid noise
        # Using min might overestimate height if one point is in a hole
        # Using median is robust.
        ground_elev = sorted(surrounding_elevs)[len(surrounding_elevs)//2]
        height_ag = center_elev - ground_elev
        
        return pd.Series([center_elev, height_ag], index=["surface_elev_m", "height_ag_m"])

    detections_df = detections_df.copy()
    # Apply calculation
    cols = detections_df.apply(calculate_local_hag, axis=1)
    detections_df["surface_elev_m"] = cols["surface_elev_m"]
    detections_df["height_ag_m"] = cols["height_ag_m"]

    # for tile in tiles:
    #     tile["src"].close()

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
            
        height_ag = row.get("height_ag_m")
        if pd.notna(height_ag):
             hag_val = float(height_ag)
             # Utility poles are typically > 9m tall.
             # Allow ample margin for DSM resolution/aliasing artifacts.
             # If HAG is < 3m, it's almost certainly not a pole (likely ground/shadow).
             if hag_val < 3.0:
                 reasons.append(f"low_height_filtered_({hag_val:.1f}m)")

        kept_row = row.copy()
        kept_row["filter_reasons"] = reasons

        if reasons and drop_failures:
            dropped_rows.append(kept_row)
        else:
            filtered_rows.append(kept_row)

    filtered_df = pd.DataFrame(filtered_rows) if filtered_rows else pd.DataFrame(columns=detections_df.columns)
    dropped_df = pd.DataFrame(dropped_rows) if dropped_rows else pd.DataFrame(columns=detections_df.columns)
    return filtered_df, dropped_df
