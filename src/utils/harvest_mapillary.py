"""
Harvest street-level imagery metadata from Mapillary for corridor enrichment.

Requires a Mapillary access token:
  export MAPILLARY_TOKEN=<token>
Token is free to generate from https://www.mapillary.com/dashboard/developer
"""
import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

import pandas as pd
import requests

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import RAW_DATA_DIR, PROCESSED_DATA_DIR


MAPILLARY_API = "https://graph.mapillary.com/images"
USER_AGENT = "PoleLocations/1.0"
MAX_BBOX_AREA = 0.009


def _compute_bbox(poles_csv: Path, margin_deg: float = 0.015) -> List[float]:
    df = pd.read_csv(poles_csv)
    if df.empty:
        raise ValueError("Pole CSV is empty; cannot derive bounding box.")
    min_lat = df["lat"].min() - margin_deg
    max_lat = df["lat"].max() + margin_deg
    min_lon = df["lon"].min() - margin_deg
    max_lon = df["lon"].max() + margin_deg
    return [min_lon, min_lat, max_lon, max_lat]


def _split_bbox(bbox: List[float], max_area: float = MAX_BBOX_AREA) -> List[List[float]]:
    min_lon, min_lat, max_lon, max_lat = bbox
    width = max_lon - min_lon
    height = max_lat - min_lat
    if width <= 0 or height <= 0:
        raise ValueError("Invalid bounding box derived from poles CSV.")

    # Subdivide the box until each tile respects the Mapillary area constraint.
    tiles_lon = tiles_lat = 1
    while (width / tiles_lon) * (height / tiles_lat) > max_area:
        if (width / tiles_lon) >= (height / tiles_lat):
            tiles_lon += 1
        else:
            tiles_lat += 1

    lon_step = width / tiles_lon
    lat_step = height / tiles_lat
    tiles: List[List[float]] = []
    for i in range(tiles_lon):
        lon_start = min_lon + i * lon_step
        lon_end = max_lon if i == tiles_lon - 1 else min_lon + (i + 1) * lon_step
        for j in range(tiles_lat):
            lat_start = min_lat + j * lat_step
            lat_end = max_lat if j == tiles_lat - 1 else min_lat + (j + 1) * lat_step
            tiles.append([lon_start, lat_start, lon_end, lat_end])
    return tiles


def _fetch_bbox_images(token: str, bbox: List[float], limit: int) -> List[dict]:
    if limit <= 0:
        return []

    fields = ",".join(
        [
            "id",
            "thumb_1024_url",
            "computed_geometry",
            "capture_time",
            "sequence",
            "camera_type",
        ]
    )
    params = {
        "access_token": token,
        "fields": fields,
        "bbox": ",".join(str(v) for v in bbox),
        "limit": min(100, limit),
    }

    items: List[dict] = []
    next_url: Optional[str] = MAPILLARY_API
    remaining = limit

    while next_url and remaining > 0:
        try:
            response = requests.get(
                next_url,
                params=params if next_url == MAPILLARY_API else None,
                timeout=30,
                headers={"User-Agent": USER_AGENT},
            )
        except requests.RequestException as exc:
            print(f"Mapillary request error ({next_url}): {exc}")
            break
        if not response.ok:
            message = "Unknown error"
            try:
                payload = response.json()
                message = payload.get("error", {}).get("message", message)
            except ValueError:
                message = response.text[:200]
            print(f"Mapillary request failed ({response.status_code}): {message}")
            break

        payload = response.json()
        data = payload.get("data", [])
        items.extend(data)
        remaining -= len(data)

        if remaining <= 0:
            break

        paging = payload.get("paging", {})
        next_url = paging.get("next")

    return items


def fetch_mapillary_images(token: str, bbox: List[float], limit: int = 300) -> pd.DataFrame:
    if limit <= 0:
        return pd.DataFrame()

    tiles = _split_bbox(bbox)
    items: List[dict] = []

    for tile in tiles:
        if len(items) >= limit:
            break
        remaining = limit - len(items)
        items.extend(_fetch_bbox_images(token, tile, remaining))

    records: List[dict] = []
    for item in items[:limit]:
        geometry = item.get("computed_geometry") or {}
        coordinates = geometry.get("coordinates") or [None, None]
        sequence = item.get("sequence")
        if isinstance(sequence, dict):
            sequence_id = sequence.get("id")
        else:
            sequence_id = sequence
        records.append(
            {
                "image_id": item.get("id"),
                "thumb_url": item.get("thumb_1024_url"),
                "lon": coordinates[0],
                "lat": coordinates[1],
                "capture_time": item.get("capture_time"),
                "sequence_id": sequence_id,
                "camera_type": item.get("camera_type"),
            }
        )
    return pd.DataFrame(records)


def download_thumbnails(df: pd.DataFrame, output_dir: Path) -> None:
    for _, row in df.iterrows():
        image_id = row["image_id"]
        url = row["thumb_url"]
        if not url or pd.isna(url):
            continue
        dest = output_dir / "images" / f"{image_id}.jpg"
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            resp = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            dest.write_bytes(resp.content)
        except requests.RequestException:
            continue


def main():
    parser = argparse.ArgumentParser(description="Download Mapillary imagery metadata for the pole footprint")
    parser.add_argument(
        "--poles",
        type=Path,
        default=RAW_DATA_DIR / "osm_poles_harrisburg_real.csv",
        help="Pole CSV used to define bounding box",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=RAW_DATA_DIR / "mapillary",
        help="Output directory to store imagery and metadata",
    )
    parser.add_argument("--limit", type=int, default=300, help="Maximum number of images to fetch")
    parser.add_argument(
        "--token",
        type=str,
        default=os.getenv("MAPILLARY_TOKEN"),
        help="Mapillary access token (falls back to MAPILLARY_TOKEN env)",
    )
    args = parser.parse_args()

    if not args.token:
        raise SystemExit("Mapillary token is required. Set MAPILLARY_TOKEN environment variable or use --token.")

    bbox = _compute_bbox(args.poles)
    imagery_dir = args.output
    imagery_dir.mkdir(parents=True, exist_ok=True)

    metadata = fetch_mapillary_images(args.token, bbox, limit=args.limit)
    if metadata.empty:
        print("No imagery returned from Mapillary.")
        return

    download_thumbnails(metadata, imagery_dir)
    metadata.to_csv(imagery_dir / "mapillary_metadata.csv", index=False)
    print(f"Saved {len(metadata)} Mapillary records to {imagery_dir}")


if __name__ == "__main__":
    main()
