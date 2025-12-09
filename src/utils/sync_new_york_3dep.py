"""Download USGS 3DEP DSM tiles for New York counties."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

from config import RAW_DATA_DIR, PROCESSED_DATA_DIR
from utils.download_3dep_dsm import download_3dep_dsm_tiles

LOGGER = logging.getLogger("sync-ny-3dep")

COUNTY_SHAPE_URL = "https://www2.census.gov/geo/tiger/TIGER2023/COUNTY/tl_2023_us_county.zip"


def _normalize_slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("'", "")


def ensure_county_poles(statewide_csv: Path, county_name: str, geom, output_csv: Path) -> None:
    statewide = pd.read_csv(statewide_csv)
    if not {"lat", "lon"}.issubset(statewide.columns):
        raise ValueError("Statewide CSV missing lat/lon columns")

    poles_gdf = gpd.GeoDataFrame(
        statewide,
        geometry=gpd.points_from_xy(statewide["lon"], statewide["lat"]),
        crs="EPSG:4326",
    )

    subset = poles_gdf[poles_gdf.geometry.within(geom)]
    if subset.empty:
        subset = poles_gdf[poles_gdf.geometry.intersects(geom)]
    if subset.empty:
        centroid = geom.centroid
        subset = gpd.GeoDataFrame(
            pd.DataFrame([
                {
                    "pole_id": f"{_normalize_slug(county_name).upper()}-CENTROID",
                    "lat": centroid.y,
                    "lon": centroid.x,
                    "source": "placeholder",
                }
            ]),
            geometry=[centroid],
            crs="EPSG:4326",
        )

    subset.drop(columns="geometry").to_csv(output_csv, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download 3DEP DSM tiles for NY counties.")
    parser.add_argument("--state-osm", type=Path, default=RAW_DATA_DIR / "osm_poles_multi" / "osm_poles_new_york_state.csv")
    parser.add_argument("--output-root", type=Path, default=PROCESSED_DATA_DIR / "3dep_dsm_multi" / "new_york_state")
    parser.add_argument("--limit", type=int, default=10, help="Max DSM tiles per county (0 = all)")
    parser.add_argument("--counties", type=str, nargs="*", help="Optional list of county slugs to restrict to.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    counties = gpd.read_file(COUNTY_SHAPE_URL)
    ny = counties[counties["STATEFP"] == "36"].to_crs("EPSG:4326")

    if args.counties:
        wanted = {_normalize_slug(c) for c in args.counties}
        ny = ny[ny["NAME"].map(lambda n: _normalize_slug(n) in wanted)]

    if ny.empty:
        raise RuntimeError("No counties selected for 3DEP download")

    args.output_root.mkdir(parents=True, exist_ok=True)

    for county in ny.itertuples():
        slug = _normalize_slug(county.NAME)
        county_name = f"New York - {county.NAME} County"
        LOGGER.info("Processing %s", county_name)

        county_pole_csv = RAW_DATA_DIR / "osm_poles_multi" / f"osm_poles_new_york_{slug}.csv"
        if not county_pole_csv.exists():
            ensure_county_poles(args.state_osm, county.NAME, county.geometry, county_pole_csv)
            LOGGER.info("  Seeded county pole CSV at %s", county_pole_csv)

        output_dir = args.output_root / slug
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            tiles = download_3dep_dsm_tiles(county_pole_csv, output_dir, limit=args.limit)
            LOGGER.info("  Downloaded %d DSM tiles", len(tiles))
        except Exception as exc:  # pragma: no cover
            LOGGER.error("  3DEP download failed for %s: %s", county_name, exc)


if __name__ == "__main__":
    main()
