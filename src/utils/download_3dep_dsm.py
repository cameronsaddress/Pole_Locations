"""Download USGS 3DEP DSM tiles via Microsoft Planetary Computer STAC."""
import argparse
from pathlib import Path
from typing import List

import pandas as pd
import planetary_computer as pc
from pystac_client import Client

from config import PROCESSED_DATA_DIR, RAW_DATA_DIR


def _compute_bbox(poles_csv: Path, margin_deg: float = 0.02) -> List[float]:
    df = pd.read_csv(poles_csv)
    if df.empty:
        raise ValueError("Pole CSV contained no rows; cannot build bounding box")
    min_lat = df['lat'].min() - margin_deg
    max_lat = df['lat'].max() + margin_deg
    min_lon = df['lon'].min() - margin_deg
    max_lon = df['lon'].max() + margin_deg
    return [min_lon, min_lat, max_lon, max_lat]


def download_3dep_dsm_tiles(poles_csv: Path, output_dir: Path, limit: int = 20) -> List[Path]:
    bbox = _compute_bbox(poles_csv)
    output_dir.mkdir(parents=True, exist_ok=True)

    catalog = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
    search = catalog.search(collections=["3dep-lidar-dsm"], bbox=bbox, max_items=limit)
    items = list(search.items())

    import requests

    downloaded: List[Path] = []
    for item in items:
        asset = item.assets.get("data")
        if not asset:
            continue
        target = output_dir / f"{item.id}.tif"
        if target.exists():
            downloaded.append(target)
            continue
        signed_href = pc.sign(asset.href)
        response = requests.get(signed_href, stream=True, timeout=60)
        response.raise_for_status()
        with open(target, "wb") as f:
            for chunk in response.iter_content(chunk_size=1 << 20):
                if chunk:
                    f.write(chunk)
        downloaded.append(target)

    return downloaded


def main():
    parser = argparse.ArgumentParser(description="Download 3DEP DSM tiles covering the pole footprint")
    parser.add_argument(
        "--poles",
        type=Path,
        default=RAW_DATA_DIR / "osm_poles_harrisburg_real.csv",
        help="CSV containing pole lat/lon"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROCESSED_DATA_DIR / "3dep_dsm",
        help="Directory to store DSM tiles"
    )
    parser.add_argument("--limit", type=int, default=20, help="Maximum number of DSM tiles to download")
    args = parser.parse_args()

    paths = download_3dep_dsm_tiles(args.poles, args.output, limit=args.limit)
    print(f"Downloaded {len(paths)} DSM tiles to {args.output}")


if __name__ == "__main__":
    main()
