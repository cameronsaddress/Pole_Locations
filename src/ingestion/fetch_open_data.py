"""
Fetch publicly available datasets to enrich the Harrisburg pilot footprint.

Downloads:
  - PAMAP 2022 orthoimagery excerpt (GeoTIFF)
  - NLCD 2019 land-cover excerpt (GeoTIFF)
  - NHD water features (GeoJSON)
  - PennDOT roadway centerlines (GeoJSON)

All downloads are scoped to the Harrisburg AOI to keep payloads lightweight.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

import requests

from config import IMAGERY_DIR, PROCESSED_DATA_DIR
from pyproj import Transformer

BBOX = (-77.05, 40.20, -76.80, 40.40)  # xmin, ymin, xmax, ymax for Harrisburg
TIMEOUT = 120


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def download_pamap_imagery() -> Path:
    """Export a PAMAP orthoimage tile covering the AOI."""
    imagery_dir = IMAGERY_DIR / "pamap"
    _ensure_dir(imagery_dir)
    output_path = imagery_dir / "tiles" / "pemaimagery_2021_2023_harrisburg.png"
    if output_path.exists():
        return output_path

    _ensure_dir(output_path.parent)
    url = "https://imagery.pasda.psu.edu/arcgis/rest/services/pasda/PEMAImagery2021_2023/MapServer/export"
    params = {
        "bbox": ",".join(map(str, BBOX)),
        "bboxSR": 4326,
        "imageSR": 4326,
        "size": "2048,2048",
        "format": "png",
        "f": "image",
    }
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    output_path.write_bytes(resp.content)
    return output_path


def download_nlcd() -> Path:
    """Download NLCD 2019 land cover clip via MRLC WCS."""
    context_dir = PROCESSED_DATA_DIR / "context"
    _ensure_dir(context_dir)
    output_path = context_dir / "nlcd_2019_harrisburg.tif"
    if output_path.exists():
        return output_path

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    x_min, y_min = transformer.transform(BBOX[0], BBOX[1])
    x_max, y_max = transformer.transform(BBOX[2], BBOX[3])
    xmin, xmax = sorted([x_min, x_max])
    ymin, ymax = sorted([y_min, y_max])

    url = "https://www.mrlc.gov/geoserver/mrlc_download/wcs"
    params = (
        ("service", "WCS"),
        ("version", "2.0.1"),
        ("request", "GetCoverage"),
        ("coverageId", "mrlc_download__NLCD_2019_Land_Cover_L48"),
        ("subset", f"X({xmin},{xmax})"),
        ("subset", f"Y({ymin},{ymax})"),
        ("format", "image/tiff"),
    )
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    output_path.write_bytes(resp.content)
    return output_path


def download_nhd_water() -> Path:
    """Grab NHD flowlines intersecting the AOI."""
    context_dir = PROCESSED_DATA_DIR / "context"
    _ensure_dir(context_dir)
    output_path = context_dir / "nhd_water.geojson"
    if output_path.exists():
        return output_path

    geometry = {
        "xmin": BBOX[0],
        "ymin": BBOX[1],
        "xmax": BBOX[2],
        "ymax": BBOX[3],
        "spatialReference": {"wkid": 4326},
    }
    url = "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/2/query"
    params = {
        "geometry": json.dumps(geometry),
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "outSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "where": "1=1",
        "outFields": "*",
        "f": "geojson",
    }
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    output_path.write_text(resp.text)
    return output_path


def download_road_centerlines() -> Path:
    """Fetch TIGER roadway centerlines (local scale) as GeoJSON."""
    context_dir = PROCESSED_DATA_DIR / "context"
    _ensure_dir(context_dir)
    output_path = context_dir / "transport_roads.geojson"
    if output_path.exists():
        return output_path

    geometry = {
        "xmin": BBOX[0],
        "ymin": BBOX[1],
        "xmax": BBOX[2],
        "ymax": BBOX[3],
        "spatialReference": {"wkid": 4326},
    }
    url = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation/MapServer/2/query"
    params = {
        "geometry": json.dumps(geometry),
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "outSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "where": "1=1",
        "outFields": "*",
        "geometryPrecision": 6,
        "f": "geojson",
    }
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    output_path.write_text(resp.text)
    return output_path


def main() -> None:
    print("Downloading PAMAP imagery…")
    pamap_path = download_pamap_imagery()
    print(f"  → {pamap_path}")

    print("Downloading NLCD land cover…")
    nlcd_path = download_nlcd()
    print(f"  → {nlcd_path}")

    print("Fetching NHD water features…")
    nhd_path = download_nhd_water()
    print(f"  → {nhd_path}")

    print("Fetching roadway centerlines…")
    roads_path = download_road_centerlines()
    print(f"  → {roads_path}")

    print("Open datasets staged successfully.")


if __name__ == "__main__":
    main()
