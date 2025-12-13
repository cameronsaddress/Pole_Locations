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

# Global Cache for Roads to prevent re-reading checks
_ROADS_CACHE = None

def annotate_with_roads(
    detections_df: pd.DataFrame,
    roads_path: Optional[Path] = None,
) -> pd.DataFrame:
    """Append nearest-road distance (meters) to each detection."""
    global _ROADS_CACHE
    
    if detections_df.empty:
        detections_df = detections_df.copy()
        detections_df["road_distance_m"] = pd.NA
        return detections_df
        
    # Get Roads GDF
    roads_gdf = None
    
    # Check Cache
    if _ROADS_CACHE is not None:
        roads_gdf = _ROADS_CACHE
    else:
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
        elif roads_path:
             roads_gdf = gpd.read_file(roads_path)
             
        # Optimize & Cache
        if roads_gdf is not None and not roads_gdf.empty:
            roads_gdf = roads_gdf[["geometry"]].dropna().reset_index(drop=True)
            if roads_gdf.crs is None:
                roads_gdf.set_crs("EPSG:4326", inplace=True)
            # Project to UTM for metric distance
            try:
                utm = roads_gdf.estimate_utm_crs()
                roads_gdf = roads_gdf.to_crs(utm)
            except:
                pass # Stay in WGS84 (deg) if fails
            
            # Force spatial index build
            _ = roads_gdf.sindex
            _ROADS_CACHE = roads_gdf
    
    if roads_gdf is None or roads_gdf.empty:
         detections_df = detections_df.copy()
         detections_df["road_distance_m"] = pd.NA
         return detections_df
         
    # Prepare Detections
    detections_gdf = gpd.GeoDataFrame(
        detections_df.copy(),
        geometry=gpd.points_from_xy(detections_df["lon"], detections_df["lat"]),
        crs="EPSG:4326",
    )
    detections_projected = detections_gdf.to_crs(roads_gdf.crs)
    
    # Calculate Nearest Distance (Vectorized)
    # Using sindex.nearest which is highly optimized
    nearest_idxs = roads_gdf.sindex.nearest(
        detections_projected.geometry, 
        return_all=False, 
        return_distance=False
    )
    
    # Get geometries to compute actual distance
    nearest_roads_geom = roads_gdf.geometry.iloc[nearest_idxs[1]].reset_index(drop=True)
    input_geoms = detections_projected.geometry.iloc[nearest_idxs[0]].reset_index(drop=True)
    
    dists = input_geoms.distance(nearest_roads_geom)
    
    # Assign back
    results = pd.Series(index=detections_projected.index, dtype=float)
    results.iloc[nearest_idxs[0]] = dists.values
    
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
        
    # Scan Tiles (Should allow caching this index too, but it's fast)
    tif_files = list(dsm_dir.glob("*.tif"))
    if not tif_files:
        detections_df = detections_df.copy()
        detections_df["surface_elev_m"] = pd.NA
        return detections_df

    tiles = []
    tile_geoms = []
    
    for tif in tif_files:
        try:
            with rasterio.open(tif) as src:
                b = src.bounds
                # Assume 4326 for bounds or simple box
                geom = box(b.left, b.bottom, b.right, b.top)
                tiles.append({"path": tif, "crs": src.crs})
                tile_geoms.append(geom)
        except RasterioIOError:
            continue
            
    if not tiles:
        detections_df = detections_df.copy()
        detections_df["surface_elev_m"] = pd.NA
        return detections_df
        
    tree = STRtree(tile_geoms)
    
    # Group points by which tile they fall into to minimize File I/O
    # 1. Query all points against tree
    points = [Point(xy) for xy in zip(detections_df.lon, detections_df.lat)]
    
    # query returns [point_indices, tile_indices]
    idx_pts, idx_tiles = tree.query(points, predicate="intersects")
    
    # Build Map: Tile Index -> List of (Point Index, Point Geom)
    tile_to_points = {}
    for pt_idx, tile_idx in zip(idx_pts, idx_tiles):
        if tile_idx not in tile_to_points:
            tile_to_points[tile_idx] = []
        tile_to_points[tile_idx].append(pt_idx)
        
    # Results container
    surface_elevs = pd.Series(index=detections_df.index, dtype=float)
    height_ag_vals = pd.Series(index=detections_df.index, dtype=float)
    
    # Iterate Tiles (Process Batch)
    for tile_idx, pt_indices in tile_to_points.items():
        tile = tiles[tile_idx]
        tif_path = tile["path"]
        
        try:
            with rasterio.open(tif_path) as src:
                # Prepare Transformer if needed
                transformer = None
                if src.crs and src.crs.to_string() != "EPSG:4326":
                     transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                
                # Process all points for this tile
                for pid in pt_indices:
                    lat = detections_df.iloc[pid]["lat"]
                    lon = detections_df.iloc[pid]["lon"]
                    
                    x, y = (lon, lat)
                    if transformer:
                        x, y = transformer.transform(lon, lat)
                        
                    # Sample Center
                    try:
                        r, c = src.index(x, y)
                        val = src.read(1, window=Window(c, r, 1, 1))[0, 0]
                        if val < -1000: center = None
                        else: center = float(val)
                    except: center = None
                    
                    if center is None: continue
                    
                    # Sample Surroundings (5m approx) to estimate ground
                    offset = 0.000045 # Roughly 5m
                    surrounds = []
                    for dx, dy in [(-offset,0), (offset,0), (0,-offset), (0,offset)]:
                        sx, sy = (lon+dx, lat+dy)
                        if transformer:
                            sx, sy = transformer.transform(sx, sy)
                        try:
                            sr, sc = src.index(sx, sy)
                            sval = src.read(1, window=Window(sc, sr, 1, 1))[0,0]
                            if sval > -1000: surrounds.append(float(sval))
                        except: pass
                    
                    ground = sorted(surrounds)[len(surrounds)//2] if surrounds else center
                    hag = center - ground
                    
                    surface_elevs.iloc[pid] = center
                    height_ag_vals.iloc[pid] = hag
                    
        except Exception as e:
            logger.warning(f"Error reading DSM tile {tif_path}: {e}")
            continue

    detections_df = detections_df.copy()
    detections_df["surface_elev_m"] = surface_elevs
    detections_df["height_ag_m"] = height_ag_vals
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


from src.ingestion.connectors.openinframap import GridConnector

def annotate_with_grid(detections_df: pd.DataFrame) -> pd.DataFrame:
    """Append nearest-grid-backbone distance (meters)."""
    grid = GridConnector()
    if grid.gdf is None:
        detections_df["grid_distance_m"] = pd.NA
        return detections_df
        
    lat_lons = list(zip(detections_df["lat"], detections_df["lon"]))
    dists = grid.get_nearest_powerline_dists(lat_lons)
    
    detections_df = detections_df.copy()
    detections_df["grid_distance_m"] = dists
    return detections_df

def annotate_context_features(
    detections_df: pd.DataFrame,
    roads_path: Optional[Path] = None,
    dsm_dir: Optional[Path] = None,
    water_path: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Enrich detection DataFrame with contextual features from roads, DSM, water, and Power Grid.
    """
    annotated = annotate_with_roads(detections_df, roads_path=roads_path)
    annotated = annotate_with_dsm(annotated, dsm_dir=dsm_dir)
    annotated = annotate_with_water(annotated, water_path=water_path)
    annotated = annotate_with_grid(annotated)
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
        grid_distance = row.get("grid_distance_m")
        
        # LOGIC UPGRADE:
        # A pole is valid if it is near a Road OR near a Utility Line.
        # Previously, we REJECTED if ANY road_distance > max.
        # Now, we only reject if BOTH are too far (or missing).
        
        is_near_road = pd.notna(road_distance) and float(road_distance) <= max_road_distance_m
        is_near_grid = pd.notna(grid_distance) and float(grid_distance) <= max_road_distance_m # Using same threshold for now
        
        if not is_near_road and not is_near_grid:
            reasons.append(f"too_far_from_infra (road={road_distance}, grid={grid_distance})")

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
             # However, standard DSM (1m or 1/3 arc-second) often fails to resolve thin poles,
             # returning ground elevation (HAG ~ 0).
             # Therefore, we CANNOT filter based on low HAG without massive False Negatives.
             # We only use HAG to BOOST confidence, not to reject.
             pass

        kept_row = row.copy()
        kept_row["filter_reasons"] = reasons

        if reasons and drop_failures:
            dropped_rows.append(kept_row)
        else:
            filtered_rows.append(kept_row)

    filtered_df = pd.DataFrame(filtered_rows) if filtered_rows else pd.DataFrame(columns=detections_df.columns)
    dropped_df = pd.DataFrame(dropped_rows) if dropped_rows else pd.DataFrame(columns=detections_df.columns)
    return filtered_df, dropped_df
