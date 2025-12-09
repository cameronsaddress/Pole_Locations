"""Split New York State into counties and download NAIP imagery per county."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable, List

import geopandas as gpd
import pandas as pd

from config import RAW_DATA_DIR, IMAGERY_DIR
from utils.download_naip_pc import download_naip_real

LOGGER = logging.getLogger("sync-ny-counties")


COUNTY_SHAPE_URL = "https://www2.census.gov/geo/tiger/TIGER2023/COUNTY/tl_2023_us_county.zip"


def _normalize_slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("'", "")


def _ensure_dirs(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download NAIP imagery per New York county.")
    parser.add_argument("--state-osm", type=Path, default=RAW_DATA_DIR / "osm_poles_multi" / "osm_poles_new_york_state.csv",
                        help="CSV of statewide OSM poles (lat/lon columns).")
    parser.add_argument("--output-root", type=Path, default=IMAGERY_DIR / "naip_multi_county" / "new_york_state",
                        help="Root directory to store county imagery.")
    parser.add_argument("--max-tiles", type=int, default=0, help="Max NAIP tiles per county (0 = all).")
    parser.add_argument("--year", type=int, nargs="*", default=None, help="NAIP acquisition years to request.")
    parser.add_argument("--counties", type=str, nargs="*", help="Optional list of county slugs to restrict to.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not args.state_osm.exists():
        raise FileNotFoundError(f"State OSM CSV missing: {args.state_osm}")

    LOGGER.info("Loading statewide OSM poles from %s", args.state_osm)
    poles_df = pd.read_csv(args.state_osm)
    if not {"lat", "lon"}.issubset(poles_df.columns):
        raise ValueError("OSM CSV must contain 'lat' and 'lon' columns")
    poles_gdf = gpd.GeoDataFrame(
        poles_df,
        geometry=gpd.points_from_xy(poles_df["lon"], poles_df["lat"]),
        crs="EPSG:4326",
    )

    LOGGER.info("Fetching New York county geometries from TIGER/Line …")
    counties = gpd.read_file(COUNTY_SHAPE_URL)
    ny_counties = counties[counties["STATEFP"] == "36"].to_crs("EPSG:4326")

    if args.counties:
        wanted = {_normalize_slug(c) for c in args.counties}
        ny_counties = ny_counties[ny_counties["NAME"].map(lambda n: _normalize_slug(n) in wanted)]

    if ny_counties.empty:
        raise RuntimeError("No counties selected after filtering.")

    for county in ny_counties.itertuples():
        slug = _normalize_slug(county.NAME)
        county_name = f"New York - {county.NAME} County"
        LOGGER.info("Processing county: %s", county_name)

        pole_subset = poles_gdf[poles_gdf.geometry.within(county.geometry)]
        if pole_subset.empty:
            pole_subset = poles_gdf[poles_gdf.geometry.intersects(county.geometry)]
        if pole_subset.empty:
            LOGGER.warning("No poles found for %s; seeding centroid placeholder", county_name)
            centroid = county.geometry.centroid
            pole_subset = gpd.GeoDataFrame(
                pd.DataFrame([
                    {
                        "pole_id": f"{slug.upper()}-CENTROID",
                        "lat": centroid.y,
                        "lon": centroid.x,
                        "source": "placeholder",
                    }
                ]),
                geometry=[centroid],
                crs="EPSG:4326",
            )

        county_pole_csv = RAW_DATA_DIR / "osm_poles_multi" / f"osm_poles_new_york_{slug}.csv"
        pole_subset.drop(columns="geometry").to_csv(county_pole_csv, index=False)
        LOGGER.info("  Saved %d poles to %s", len(pole_subset), county_pole_csv)

        imagery_dir = args.output_root / slug
        _ensure_dirs(imagery_dir)

        try:
            download_naip_real(
                poles_csv=county_pole_csv,
                imagery_dir=imagery_dir,
                mosaic=False,
                max_tiles=args.max_tiles,
                years=args.year,
                metadata_manifest=imagery_dir / "manifest.json",
            )
        except Exception as exc:  # pragma: no cover
            LOGGER.error("  NAIP download failed for %s: %s", county_name, exc)
            continue

        LOGGER.info("Completed %s", county_name)


if __name__ == "__main__":
    main()
