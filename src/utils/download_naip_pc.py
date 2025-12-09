"""
Download REAL NAIP imagery from Microsoft Planetary Computer
FREE - No authentication required!
"""
import argparse
import logging
import sys
import urllib.error
import urllib.request
import time
from pathlib import Path
from typing import List, Optional

import pandas as pd
import planetary_computer as pc
import rasterio
import rasterio.errors
from rasterio.windows import Window
from pystac_client import Client
from rasterio.merge import merge
from rasterio.transform import array_bounds
from rasterio.warp import transform_bounds
from shapely.geometry import box

sys.path.append(str(Path(__file__).parent.parent))
from config import IMAGERY_DIR, RAW_DATA_DIR  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _validate_tile(path: Path, sample_size: int = 512) -> bool:
    """
    Validate that a GeoTIFF can be opened and that representative windows are readable.
    """
    try:
        with rasterio.open(path) as dataset:
            if dataset.count < 3:
                logger.warning("Tile %s has unexpected band count: %d", path.name, dataset.count)
                return False

            width, height = dataset.width, dataset.height
            window_w = min(sample_size, width)
            window_h = min(sample_size, height)
            corners = [
                (0, 0),
                (max(0, width - window_w), 0),
                (0, max(0, height - window_h)),
                (max(0, width - window_w), max(0, height - window_h)),
            ]
            for col, row in corners:
                window = Window(col, row, window_w, window_h)
                dataset.read(1, window=window)

            dataset.checksum(1)
        return True
    except rasterio.errors.RasterioIOError as err:
        logger.warning("Tile %s failed validation: %s", path.name, err)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Unexpected validation error for %s: %s", path.name, exc)

    return False


def _download_with_retries(href: str, destination: Path, attempts: int = 3, sleep_seconds: float = 2.0) -> bool:
    """Download a tile with retry + validation."""
    for attempt in range(1, attempts + 1):
        try:
            urllib.request.urlretrieve(href, destination)
        except urllib.error.HTTPError as http_err:
            logger.warning(
                "  ↳ HTTP error downloading %s (attempt %d/%d): %s",
                destination.name,
                attempt,
                attempts,
                http_err,
            )
            if destination.exists():
                destination.unlink(missing_ok=True)
            if http_err.code >= 500 and attempt < attempts:
                time.sleep(sleep_seconds)
                continue
            return False
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "  ↳ Error downloading %s (attempt %d/%d): %s",
                destination.name,
                attempt,
                attempts,
                exc,
            )
            if destination.exists():
                destination.unlink(missing_ok=True)
            if attempt < attempts:
                time.sleep(sleep_seconds)
                continue
            return False

        if _validate_tile(destination):
            return True

        logger.warning(
            "  ↳ Validation failed for %s (attempt %d/%d); retrying…",
            destination.name,
            attempt,
            attempts,
        )
        destination.unlink(missing_ok=True)
        if attempt < attempts:
            time.sleep(sleep_seconds)

    return False


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
    metadata_manifest: Optional[Path] = None,
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
            preview = catalog.search(collections=["naip"], bbox=bbox)
            preview_items = list(preview.items())
            if not preview_items:
                logger.error("NAIP search returned no scenes; aborting.")
                return []
            latest_year = max(item.datetime.year for item in preview_items if item.datetime)
            years = [latest_year]
            logger.info(f"No year specified; defaulting to latest available {latest_year}.")

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
        manifest_records = []
        for item in sorted(items, key=lambda x: x.datetime, reverse=True):
            asset = item.assets.get("image")
            if not asset:
                logger.warning(f"Skipping item {item.id} (no image asset).")
                continue

            output_path = imagery_dir / f"{item.id}.tif"
            if output_path.exists():
                if _validate_tile(output_path):
                    logger.info(f"• Skipping existing tile {output_path.name}")
                    downloaded_paths.append(output_path)
                    manifest_records.append(
                        {
                            "item_id": item.id,
                            "datetime": item.datetime.isoformat() if item.datetime else None,
                            "href": asset.href,
                            "path": str(output_path),
                            "epsg": item.properties.get("epsg"),
                            "gsd": item.properties.get("gsd"),
                        }
                    )
                    continue
                logger.warning(f"• Existing tile {output_path.name} failed validation; re-downloading.")
                output_path.unlink(missing_ok=True)

            signed_href = pc.sign(asset.href)
            logger.info(f"• Downloading {item.id} -> {output_path.name}")
            if not _download_with_retries(signed_href, output_path):
                logger.warning(f"  ↳ Skipping {item.id} after repeated download failures.")
                continue

            downloaded_paths.append(output_path)
            manifest_records.append(
                {
                    "item_id": item.id,
                    "datetime": item.datetime.isoformat() if item.datetime else None,
                    "href": asset.href,
                    "path": str(output_path),
                    "epsg": item.properties.get("epsg"),
                    "gsd": item.properties.get("gsd"),
                }
            )

            if max_tiles and len(downloaded_paths) >= max_tiles:
                logger.info(f"Reached max_tiles={max_tiles}, stopping additional downloads.")
                break

        if metadata_manifest:
            manifest_df = pd.DataFrame(manifest_records)
            metadata_manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest_df.to_json(metadata_manifest, orient="records", indent=2)
            logger.info(f"✓ Manifest written to {metadata_manifest}")

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
        default="",
        help="Comma-separated list of years to pull (e.g. 2021,2022). If omitted, uses the most recent available.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=IMAGERY_DIR / "naip_tiles_manifest.json",
        help="Where to write a manifest JSON enumerating downloaded tiles.",
    )
    args = parser.parse_args()

    years = sorted({int(y.strip()) for y in args.years.split(",") if y.strip()}) if args.years else None

    logger.info("Attempting to download NAIP imagery for operations grid…")
    tiles = download_naip_real(
        args.poles,
        args.output_dir,
        mosaic=not args.no_mosaic,
        max_tiles=args.max_tiles,
        years=years,
        metadata_manifest=args.manifest,
    )

    if tiles:
        logger.info(f"\n✅ SUCCESS: {len(tiles)} tiles available in {args.output_dir}")
    else:
        logger.error("\n❌ NAIP imagery download failed. See logs for details.")
