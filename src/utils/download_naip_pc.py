"""
Download REAL NAIP imagery from Microsoft Planetary Computer
FREE - No authentication required!
"""
import argparse
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional

import pandas as pd
import planetary_computer as pc
import rasterio
import rasterio.errors
from pystac_client import Client
from rasterio.merge import merge
from rasterio.transform import array_bounds
from rasterio.warp import transform_bounds
from shapely.geometry import box

sys.path.append(str(Path(__file__).parent.parent))
from config import IMAGERY_DIR, RAW_DATA_DIR  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _compute_bbox_from_poles(poles_csv: Path, margin: float = 0.02) -> List[float]:
    """Compute lat/lon bounding box from poles CSV with optional margin (degrees)."""
    poles_df = pd.read_csv(poles_csv)
    if poles_df.empty:
        raise ValueError(f"No poles found in {poles_csv}")

    min_lat = poles_df['lat'].min() - margin
    max_lat = poles_df['lat'].max() + margin
    min_lon = poles_df['lon'].min() - margin
    max_lon = poles_df['lon'].max() + margin

    bbox = [min_lon, min_lat, max_lon, max_lat]
    logger.info(f"Computed pole bounding box (deg): {bbox}")
    return bbox


def download_naip_real(
    poles_csv: Path,
    imagery_dir: Path,
    mosaic: bool = True,
    max_tiles: int = 20,
    years: Optional[List[int]] = None,
):
    """
    Download NAIP imagery covering the bounding box derived from the poles CSV.
    Optionally mosaics multiple tiles into a single GeoTIFF.
    """
    logger.info("=" * 80)
    logger.info("DOWNLOADING NAIP IMAGERY FOR REGION")
    logger.info("=" * 80)
    logger.info("Source: Microsoft Planetary Computer")
    logger.info("Dataset: USDA NAIP (National Agriculture Imagery Program)")
    logger.info("Resolution: 0.6 - 1.0 meters per pixel")
    logger.info("Format: Cloud-Optimized GeoTIFF (COG)")
    logger.info("Cost: FREE - No authentication required!")
    logger.info("")

    imagery_dir.mkdir(parents=True, exist_ok=True)

    bbox = _compute_bbox_from_poles(poles_csv)

    try:
        logger.info("Connecting to Microsoft Planetary Computer…")
        catalog = Client.open(
            "https://planetarycomputer.microsoft.com/api/stac/v1",
            modifier=pc.sign_inplace,
        )
        logger.info("✓ Connected successfully!")

        logger.info("\nSearching for NAIP imagery tiles…")
        if not years:
            years = [2022]

        items = []
        for year in years:
            timerange = f"{year}-01-01/{year}-12-31"
            logger.info(f"Searching NAIP collection for {timerange}…")
            search = catalog.search(
                collections=["naip"],
                bbox=bbox,
                datetime=timerange,
            )
            year_items = list(search.items())
            if not year_items:
                logger.warning(f"  ↳ No NAIP imagery found for {year}.")
                continue
            logger.info(f"  ↳ Found {len(year_items)} scenes for {year}.")
            items.extend(year_items)

        if not items:
            logger.error("No NAIP imagery found for requested extent.")
            return []

        logger.info(f"✓ Found {len(items)} scenes covering region.")

        downloaded_paths = []
        for item in sorted(items, key=lambda x: x.datetime, reverse=True):
            asset = item.assets.get("image")
            if not asset:
                logger.warning(f"Skipping item {item.id} (no image asset).")
                continue

            output_path = imagery_dir / f"{item.id}.tif"
            if output_path.exists():
                logger.info(f"• Skipping existing tile {output_path.name}")
                downloaded_paths.append(output_path)
                continue

            signed_href = pc.sign(asset.href)
            logger.info(f"• Downloading {item.id} -> {output_path.name}")
            try:
                urllib.request.urlretrieve(signed_href, output_path)
                downloaded_paths.append(output_path)
            except urllib.error.HTTPError as http_err:
                logger.warning(f"  ↳ Skipping {item.id} (HTTP {http_err.code})")
                if output_path.exists():
                    output_path.unlink(missing_ok=True)
                continue

            if max_tiles and len(downloaded_paths) >= max_tiles:
                logger.info(f"Reached max_tiles={max_tiles}, stopping additional downloads.")
                break

        if not downloaded_paths:
            logger.error("No tiles downloaded.")
            return []

        logger.info(f"\nTotal tiles available: {len(downloaded_paths)}")

        if not mosaic:
            return downloaded_paths

        logger.info("\nCreating mosaic from downloaded tiles…")
        datasets = []
        for path in downloaded_paths:
            try:
                datasets.append(rasterio.open(path))
            except rasterio.errors.RasterioIOError as err:  # type: ignore[attr-defined]
                logger.warning(f"Skipping corrupt tile {path.name}: {err}")
        if not datasets:
            logger.error("No valid NAIP tiles available for mosaic.")
            return downloaded_paths
        mosaic_array, mosaic_transform = merge(datasets)

        meta = datasets[0].meta.copy()
        meta.update(
            {
                "height": mosaic_array.shape[1],
                "width": mosaic_array.shape[2],
                "transform": mosaic_transform,
                "driver": "GTiff",
            }
        )

        mosaic_path = IMAGERY_DIR / "naip_mosaic.tif"
        mosaic_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(mosaic_path, "w", **meta) as dest:
            dest.write(mosaic_array)

        for ds in datasets:
            ds.close()

        logger.info(f"✓ Mosaic saved to {mosaic_path}")

        minx, miny, maxx, maxy = array_bounds(meta["height"], meta["width"], mosaic_transform)
        bounds_wgs84 = rasterio.warp.transform_bounds(meta["crs"], "EPSG:4326", minx, miny, maxx, maxy)
        logger.info(f"   Mosaic bounds (lon/lat): {bounds_wgs84}")
        logger.info("🎯 Ready for crop extraction across the entire grid.")

        return downloaded_paths

    except Exception as exc:
        logger.error(f"Download failed: {exc}")
        import traceback

        traceback.print_exc()
        return []


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download NAIP imagery covering pole grid.")
    parser.add_argument(
        "--poles",
        type=Path,
        default=RAW_DATA_DIR / "osm_poles_harrisburg_real.csv",
        help="CSV containing pole lat/lon (default: OSM Harrisburg dataset)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=IMAGERY_DIR / "naip_tiles",
        help="Directory to store downloaded NAIP tiles",
    )
    parser.add_argument(
        "--no-mosaic",
        action="store_true",
        help="Skip mosaic generation (keep individual tiles only)",
    )
    parser.add_argument(
        "--max-tiles",
        type=int,
        default=20,
        help="Maximum number of NAIP tiles to download (newest first).",
    )
    parser.add_argument(
        "--years",
        type=str,
        default="2022",
        help="Comma-separated list of years to pull (e.g. 2021,2022 for multi-season).",
    )
    args = parser.parse_args()

    years = sorted({int(y.strip()) for y in args.years.split(",") if y.strip()})

    logger.info("Attempting to download NAIP imagery for operations grid…")
    tiles = download_naip_real(
        args.poles,
        args.output_dir,
        mosaic=not args.no_mosaic,
        max_tiles=args.max_tiles,
        years=years,
    )

    if tiles:
        logger.info(f"\n✅ SUCCESS: {len(tiles)} tiles available in {args.output_dir}")
    else:
        logger.error("\n❌ NAIP imagery download failed. See logs for details.")
