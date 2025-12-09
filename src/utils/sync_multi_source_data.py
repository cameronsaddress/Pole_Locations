"""
Orchestrate multi-source data collection (poles, aerial imagery, street-level, LiDAR)
for multiple adjacent counties so the detector can be trained on broader coverage.

Sources:
  • OpenStreetMap (pole inventory)
  • Microsoft Planetary Computer NAIP tiles (aerial imagery)
  • PASDA / PEMA orthophotos (state leaf-off imagery)
  • Mapillary street-level metadata + thumbnails
  • USGS 3DEP DSM rasters (height context)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import osmnx as ox
import pandas as pd

import sys

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
sys.path.append(str(PROJECT_ROOT))

from config import IMAGERY_DIR, PROCESSED_DATA_DIR, RAW_DATA_DIR  # noqa: E402
from utils.download_naip_pc import download_naip_real  # noqa: E402
from utils.download_3dep_dsm import download_3dep_dsm_tiles  # noqa: E402
from utils.download_pema_imagery import _compute_bbox as pema_bbox  # noqa: E402
from utils.download_pema_imagery import _download_tile as pema_download_tile  # noqa: E402
from utils.download_pema_imagery import _generate_tiles as pema_generate_tiles  # noqa: E402
from utils.harvest_mapillary import fetch_mapillary_images, download_thumbnails  # noqa: E402

LOGGER = logging.getLogger("sync-multi-source")


@dataclass(frozen=True)
class AreaConfig:
    slug: str
    name: str
    state: str
    center_lat: float
    center_lon: float
    radius_km: float = 25.0
    place_query: Optional[str] = None


DEFAULT_AREAS: Dict[str, AreaConfig] = {
    "dauphin_pa": AreaConfig(
        slug="dauphin_pa",
        name="Dauphin County, PA",
        state="PA",
        center_lat=40.2732,
        center_lon=-76.8867,
        radius_km=28.0,
    ),
    "cumberland_pa": AreaConfig(
        slug="cumberland_pa",
        name="Cumberland County, PA",
        state="PA",
        center_lat=40.2000,
        center_lon=-77.2630,
        radius_km=28.0,
    ),
    "york_pa": AreaConfig(
        slug="york_pa",
        name="York County, PA",
        state="PA",
        center_lat=39.9626,
        center_lon=-76.7277,
        radius_km=30.0,
    ),
    "new_york_state": AreaConfig(
        slug="new_york_state",
        name="New York State, USA",
        state="NY",
        center_lat=42.9134,
        center_lon=-75.5963,
        radius_km=400.0,
        place_query="New York State, United States",
    ),
}


# Directories
POLE_OUTPUT_DIR = RAW_DATA_DIR / "osm_poles_multi"
NAIP_BASE_DIR = IMAGERY_DIR / "naip_multi_county"
MAPILLARY_BASE_DIR = RAW_DATA_DIR / "mapillary_multi"
PEMA_BASE_DIR = IMAGERY_DIR / "pema_tiles_multi"
THREEDEP_BASE_DIR = PROCESSED_DATA_DIR / "3dep_dsm_multi"
STATUS_PATH = RAW_DATA_DIR / "naip_multi_county" / "download_status.json"
OSM_CACHE_DIR = RAW_DATA_DIR / "osm_cache"

os.environ.setdefault("OSMNX_CACHE", "true")
os.environ.setdefault("OSMNX_CACHE_FOLDER", str(OSM_CACHE_DIR.resolve()))
ox.settings.use_cache = True
ox.settings.cache_folder = str(OSM_CACHE_DIR.resolve())
ox.settings.log_console = False


def ensure_dirs() -> None:
    for directory in [
        POLE_OUTPUT_DIR,
        NAIP_BASE_DIR,
        MAPILLARY_BASE_DIR,
        PEMA_BASE_DIR,
        THREEDEP_BASE_DIR,
        STATUS_PATH.parent,
        OSM_CACHE_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)


def load_status() -> dict:
    if STATUS_PATH.exists():
        try:
            return json.loads(STATUS_PATH.read_text())
        except json.JSONDecodeError:
            LOGGER.warning("Existing status file %s is not valid JSON; starting fresh.", STATUS_PATH)
    return {}


def save_status(status: dict) -> None:
    STATUS_PATH.write_text(json.dumps(status, indent=2))


def _extract_point_geometry(lat_series: pd.Series, lon_series: pd.Series) -> Tuple[pd.Series, pd.Series]:
    mask = lat_series.notna() & lon_series.notna()
    return lat_series[mask], lon_series[mask]


def download_osm_poles_for_area(area: AreaConfig, output_dir: Path, tags: Optional[dict] = None) -> Path:
    LOGGER.info("Fetching OpenStreetMap poles for %s", area.name)
    output_dir.mkdir(parents=True, exist_ok=True)
    radius_m = int(area.radius_km * 1000)
    center = (area.center_lat, area.center_lon)

    # Use broader tag set, then filter down.
    tag_filter = tags or {"power": True, "man_made": True}

    if area.place_query:
        LOGGER.info("Using place query '%s' for OSM download", area.place_query)
        try:
            gdf = ox.geometries_from_place(area.place_query, tags=tag_filter)
        except Exception as exc:
            LOGGER.warning("Place query failed (%s); falling back to radius search: %s", area.place_query, exc)
            gdf = ox.geometries_from_point(center, dist=radius_m, tags=tag_filter)
    else:
        gdf = ox.geometries_from_point(center, dist=radius_m, tags=tag_filter)

    def _is_pole(row: pd.Series) -> bool:
        power = str(row.get("power", "")).lower()
        man_made = str(row.get("man_made", "")).lower()
        return (
            power in {"pole", "tower", "portal", "catenary_mast"}
            or man_made in {"utility_pole", "utility_pole_base", "power_pole"}
        )

    if gdf.empty:
        raise RuntimeError(f"No OSM geometries returned for {area.name}.")

    filtered = gdf[gdf.apply(_is_pole, axis=1)]
    if filtered.empty:
        raise RuntimeError(f"OSM query returned data but no poles/towers for {area.name}.")

    records = []
    for idx, row in filtered.iterrows():
        geom = row.geometry
        if geom is None:
            continue
        if geom.geom_type == "Point":
            lon, lat = geom.x, geom.y
        else:
            centroid = geom.centroid
            lon, lat = centroid.x, centroid.y
        if np.isnan(lat) or np.isnan(lon):
            continue
        element_id = idx[1] if isinstance(idx, tuple) else idx
        pole_id = f"{area.slug.upper()}-{element_id}"
        records.append(
            {
                "pole_id": pole_id,
                "lat": lat,
                "lon": lon,
                "state": area.state,
                "status": "verified",
                "inspection_date": "2024-01-01",
                "source": "OpenStreetMap",
                "power": row.get("power"),
                "man_made": row.get("man_made"),
                "operator": row.get("operator"),
                "voltage": row.get("voltage"),
            }
        )

    df = pd.DataFrame(records)
    poles_path = output_dir / f"osm_poles_{area.slug}.csv"
    df.to_csv(poles_path, index=False)
    LOGGER.info("Saved %d poles to %s", len(df), poles_path)
    return poles_path


def compute_bbox_from_poles(poles_csv: Path, margin_deg: float = 0.02) -> Tuple[float, float, float, float]:
    df = pd.read_csv(poles_csv)
    if df.empty:
        raise ValueError(f"{poles_csv} contained no rows; cannot derive bounding box")
    min_lat = df["lat"].min() - margin_deg
    max_lat = df["lat"].max() + margin_deg
    min_lon = df["lon"].min() - margin_deg
    max_lon = df["lon"].max() + margin_deg
    return min_lon, min_lat, max_lon, max_lat


def download_naip_for_area(area: AreaConfig, poles_csv: Path, years: Optional[List[int]], max_tiles: int) -> List[Path]:
    imagery_dir = NAIP_BASE_DIR / area.slug
    manifest = imagery_dir / "manifest.json"
    imagery_dir.mkdir(parents=True, exist_ok=True)
    LOGGER.info("Downloading NAIP tiles for %s into %s", area.name, imagery_dir)
    return download_naip_real(
        poles_csv=poles_csv,
        imagery_dir=imagery_dir,
        mosaic=False,
        max_tiles=max_tiles,
        years=years,
        metadata_manifest=manifest,
    )


def download_pema_for_area(area: AreaConfig, poles_csv: Path, tile_span: float, size: int) -> List[Path]:
    if area.state.upper() != "PA":
        LOGGER.info("Skipping PEMA orthophotos for %s (state %s not supported)", area.name, area.state)
        return []
    bbox = pema_bbox(poles_csv, 0.02)
    tiles = pema_generate_tiles(bbox, tile_span)
    output_dir = PEMA_BASE_DIR / area.slug
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: List[Path] = []
    for idx, tile in enumerate(tiles, start=1):
        dest = output_dir / f"{area.slug}_pema_{idx:03d}.tif"
        if dest.exists():
            downloaded.append(dest)
            continue
        if pema_download_tile(tile, dest, size):
            downloaded.append(dest)
    LOGGER.info("Downloaded %d PEMA tiles for %s", len(downloaded), area.name)
    if downloaded:
        manifest = output_dir / "manifest.json"
        manifest.write_text(
            json.dumps(
                [{"index": i + 1, "bbox": tiles[i], "path": str(path)} for i, path in enumerate(downloaded)],
                indent=2,
            )
        )
    return downloaded


def download_3dep_for_area(area: AreaConfig, poles_csv: Path, limit: int) -> List[Path]:
    output_dir = THREEDEP_BASE_DIR / area.slug
    LOGGER.info("Fetching 3DEP DSM tiles for %s", area.name)
    return download_3dep_dsm_tiles(poles_csv, output_dir, limit=limit)


def download_mapillary_for_area(area: AreaConfig, poles_csv: Path, limit: int, token: Optional[str]) -> Tuple[Path, int]:
    if not token:
        LOGGER.warning("MAPILLARY_TOKEN not provided; skipping street-level imagery for %s.", area.name)
        return Path(), 0

    bbox = compute_bbox_from_poles(poles_csv, margin_deg=0.01)
    try:
        df = fetch_mapillary_images(token, list(bbox), limit=limit)
    except Exception as exc:
        LOGGER.error("Mapillary request failed for %s: %s", area.name, exc)
        return Path(), 0
    if df.empty:
        LOGGER.warning("No Mapillary imagery returned for %s.", area.name)
        return Path(), 0

    area_dir = MAPILLARY_BASE_DIR / area.slug
    area_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = area_dir / "mapillary_metadata.csv"
    df.to_csv(metadata_path, index=False)
    download_thumbnails(df, area_dir)
    LOGGER.info("Saved %d Mapillary thumbnails to %s", len(df), area_dir)
    return metadata_path, len(df)


def sync_area(
    area: AreaConfig,
    args: argparse.Namespace,
    status: dict,
) -> None:
    LOGGER.info("=" * 90)
    LOGGER.info("SYNCING DATA SOURCES FOR %s", area.name)
    LOGGER.info("=" * 90)

    try:
        poles_csv = download_osm_poles_for_area(area, POLE_OUTPUT_DIR)
    except Exception as exc:
        LOGGER.error("Failed to download poles for %s: %s", area.name, exc)
        return

    if not args.skip_naip:
        try:
            naip_tiles = download_naip_for_area(area, poles_csv, years=args.naip_years, max_tiles=args.naip_max_tiles)
            LOGGER.info("NAIP tiles synced: %d", len(naip_tiles))
        except Exception as exc:
            LOGGER.error("NAIP download failed for %s: %s", area.name, exc)

    if not args.skip_pema:
        try:
            pema_tiles = download_pema_for_area(area, poles_csv, tile_span=args.pema_tile_span, size=args.pema_tile_size)
            LOGGER.info("PEMA tiles synced: %d", len(pema_tiles))
        except Exception as exc:
            LOGGER.error("PEMA download failed for %s: %s", area.name, exc)

    if not args.skip_3dep:
        try:
            dsm_tiles = download_3dep_for_area(area, poles_csv, limit=args.dsm_limit)
            LOGGER.info("3DEP DSM tiles synced: %d", len(dsm_tiles))
        except Exception as exc:
            LOGGER.error("3DEP download failed for %s: %s", area.name, exc)

    if not args.skip_mapillary:
        metadata_path, count = download_mapillary_for_area(area, poles_csv, limit=args.mapillary_limit, token=args.mapillary_token)
        if metadata_path:
            LOGGER.info("Mapillary assets saved to %s (%d images)", metadata_path.parent, count)

    status_entry = status.get(area.slug, {})
    status_entry.update(
        {
            "last_sync": pd.Timestamp.utcnow().isoformat(),
            "osm_poles": str(POLE_OUTPUT_DIR / f"osm_poles_{area.slug}.csv"),
            "naip_dir": str(NAIP_BASE_DIR / area.slug),
            "mapillary_dir": str(MAPILLARY_BASE_DIR / area.slug),
            "pema_dir": str(PEMA_BASE_DIR / area.slug),
            "dsm_dir": str(THREEDEP_BASE_DIR / area.slug),
        }
    )
    status[area.slug] = status_entry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync multi-source pole data for multiple counties.")
    parser.add_argument(
        "--areas",
        type=str,
        default="all",
        help="Comma-separated list of area slugs to sync (default: all known areas).",
    )
    parser.add_argument("--naip-years", type=int, nargs="+", default=None, help="Specific NAIP acquisition years to request.")
    parser.add_argument("--naip-max-tiles", type=int, default=18, help="Maximum NAIP tiles per area.")
    parser.add_argument("--mapillary-limit", type=int, default=400, help="Maximum Mapillary thumbnails per area.")
    parser.add_argument("--pema-tile-span", type=float, default=0.045, help="PEMA tile span in degrees.")
    parser.add_argument("--pema-tile-size", type=int, default=2048, help="PEMA tile pixel size.")
    parser.add_argument("--dsm-limit", type=int, default=25, help="Number of 3DEP DSM tiles to request.")
    parser.add_argument("--skip-mapillary", action="store_true", help="Skip Mapillary downloads.")
    parser.add_argument("--skip-naip", action="store_true", help="Skip NAIP imagery downloads.")
    parser.add_argument("--skip-pema", action="store_true", help="Skip PEMA orthophoto downloads.")
    parser.add_argument("--skip-3dep", action="store_true", help="Skip 3DEP DSM downloads.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()
    args.mapillary_token = os.getenv("MAPILLARY_TOKEN")
    if args.skip_mapillary:
        args.mapillary_token = None
    elif not args.mapillary_token:
        LOGGER.warning(
            "MAPILLARY_TOKEN environment variable not set. To include street-level imagery, export MAPILLARY_TOKEN or rerun with --skip-mapillary."
        )
        args.skip_mapillary = True
    return args


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        force=True,
    )
    LOGGER.setLevel(logging.DEBUG if args.verbose else logging.INFO)

    ensure_dirs()
    status = load_status()

    if args.areas.lower() == "all":
        selected = list(DEFAULT_AREAS.values())
    else:
        slugs = [area.strip().lower() for area in args.areas.split(",") if area.strip()]
        unknown = [slug for slug in slugs if slug not in DEFAULT_AREAS]
        if unknown:
            raise SystemExit(
                f"Unknown area slugs: {', '.join(unknown)}. Known areas: {', '.join(DEFAULT_AREAS.keys())}"
            )
        selected = [DEFAULT_AREAS[slug] for slug in slugs]

    LOGGER.info("Selected areas: %s", ", ".join(area.slug for area in selected))

    for area in selected:
        sync_area(area, args, status)

    save_status(status)
    LOGGER.info("Completed multi-source data sync.")


if __name__ == "__main__":
    main()
