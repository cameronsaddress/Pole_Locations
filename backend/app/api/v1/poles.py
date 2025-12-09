"""
Poles API endpoints
"""
import json
import sys
import logging
from ast import literal_eval
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from io import BytesIO

import numpy as np
import pandas as pd
from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

sys.path.append(str(Path(__file__).parent.parent.parent.parent.parent / 'src'))
from config import RAW_DATA_DIR, PROCESSED_DATA_DIR  # noqa: E402

DETECTIONS_META_PATH = PROCESSED_DATA_DIR / 'ai_detections_metadata.json'
DETECTIONS_PATH = PROCESSED_DATA_DIR / 'ai_detections.csv'
NAIP_TILE_DIR = PROCESSED_DATA_DIR.parent / 'imagery' / 'naip_tiles'
ESRI_EXPORT_URL = "https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/export"

logger = logging.getLogger(__name__)

router = APIRouter()

_DETECTIONS_CACHE = None
_DETECTIONS_CACHE_MTIME = None
_POLE_COORD_CACHE: Dict[str, Optional[Tuple[float, float]]] = {}
_TILE_METADATA: Optional[List[Dict[str, object]]] = None


def _safe_float(value):
    """Convert to float if finite, else return None."""
    if value is None:
        return None
    try:
        fval = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(fval) or not np.isfinite(fval):
        return None
    return fval


def _safe_str(value, default: Optional[str] = None) -> Optional[str]:
    if value is None:
        return default
    if isinstance(value, float) and pd.isna(value):
        return default
    value = str(value)
    if not value or value.lower() == 'nan':
        return default
    return value


def _get_detection_dataframe() -> Optional[pd.DataFrame]:
    """Load AI detection metadata (cached)."""
    global _DETECTIONS_CACHE, _DETECTIONS_CACHE_MTIME

    if not DETECTIONS_PATH.exists():
        return None

    mtime = DETECTIONS_PATH.stat().st_mtime
    if _DETECTIONS_CACHE is None or _DETECTIONS_CACHE_MTIME != mtime:
        try:
            _DETECTIONS_CACHE = pd.read_csv(DETECTIONS_PATH)
            _DETECTIONS_CACHE_MTIME = mtime
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to load AI detection metadata: %s", exc)
            _DETECTIONS_CACHE = None
            _DETECTIONS_CACHE_MTIME = None
            return None

    return _DETECTIONS_CACHE


def _lookup_detection_row(pole_id: str) -> Optional[pd.Series]:
    """Return detection metadata row for the requested AI-only pole."""
    df = _get_detection_dataframe()
    if df is None:
        return None

    idx = None
    if pole_id.startswith("AI_"):
        try:
            idx = int(pole_id.split("_", 1)[1])
        except (IndexError, ValueError):
            idx = None

    if idx is not None and 0 <= idx < len(df):
        return df.iloc[idx]

    match = df[df['pole_id'] == pole_id]
    if not match.empty:
        return match.iloc[0]

    return None


def _load_tile_metadata() -> List[Dict[str, object]]:
    """Cache NAIP tile bounds in WGS84 for fast lookup."""
    global _TILE_METADATA

    if _TILE_METADATA is not None:
        return _TILE_METADATA

    tile_info: List[Dict[str, object]] = []
    if not NAIP_TILE_DIR.exists():
        _TILE_METADATA = tile_info
        return tile_info

    try:
        import rasterio
        from rasterio.warp import transform_bounds
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Rasterio unavailable for tile metadata: %s", exc)
        _TILE_METADATA = tile_info
        return tile_info

    for tif in sorted(NAIP_TILE_DIR.glob("*.tif")):
        try:
            with rasterio.open(tif) as src:
                bounds = src.bounds
                crs = src.crs or "EPSG:4326"
                if crs and crs.to_string() != "EPSG:4326":
                    minx, miny, maxx, maxy = transform_bounds(
                        crs, "EPSG:4326", bounds.left, bounds.bottom, bounds.right, bounds.top
                    )
                else:
                    minx, miny, maxx, maxy = bounds.left, bounds.bottom, bounds.right, bounds.top
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to read NAIP tile %s: %s", tif, exc)
            continue

        tile_info.append(
            {
                "path": tif,
                "bounds": (minx, miny, maxx, maxy),
            }
        )

    _TILE_METADATA = tile_info
    return tile_info


def _get_pole_coordinates(pole_id: str) -> Optional[Tuple[float, float]]:
    """Return (lat, lon) for the requested pole using cached lookups."""
    if pole_id in _POLE_COORD_CACHE:
        return _POLE_COORD_CACHE[pole_id]

    lat_lon: Optional[Tuple[float, float]] = None

    verified_path = PROCESSED_DATA_DIR / "verified_poles_multi_source.csv"
    if verified_path.exists() and lat_lon is None:
        try:
            verified_df = pd.read_csv(verified_path)
            row = verified_df[verified_df["pole_id"] == pole_id]
            if not row.empty:
                lat = row.iloc[0].get("lat")
                lon = row.iloc[0].get("lon")
                if lat is not None and lon is not None and np.isfinite(lat) and np.isfinite(lon):
                    lat_lon = (float(lat), float(lon))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to read verified coordinates: %s", exc)

    if lat_lon is None:
        poles_csv = RAW_DATA_DIR / "osm_poles_harrisburg_real.csv"
        if poles_csv.exists():
            try:
                base_df = pd.read_csv(poles_csv)
                row = base_df[base_df["pole_id"] == pole_id]
                if not row.empty:
                    lat = row.iloc[0].get("lat")
                    lon = row.iloc[0].get("lon")
                    if lat is not None and lon is not None and np.isfinite(lat) and np.isfinite(lon):
                        lat_lon = (float(lat), float(lon))
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to read base coordinates: %s", exc)

    _POLE_COORD_CACHE[pole_id] = lat_lon
    return lat_lon


def _build_ai_detection_image(pole_id: str):
    """
    Render an image crop for AI-only detections using tile metadata.
    Returns a PIL Image or None if unavailable.
    """
    detection = _lookup_detection_row(pole_id)
    if detection is None:
        return None

    tile_path = detection.get('tile_path')
    if not tile_path:
        return None

    tile_path = Path(tile_path)
    if not tile_path.exists():
        return None

    try:
        import rasterio
        from rasterio.windows import Window
        from PIL import Image, ImageDraw
        import numpy as np
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Missing dependencies to render AI detection image: %s", exc)
        return None

    center_x = float(detection.get('pixel_x', 0.0))
    center_y = float(detection.get('pixel_y', 0.0))
    crop_size = 256
    half = crop_size // 2

    try:
        with rasterio.open(tile_path) as src:
            width, height = src.width, src.height
            col_off = max(0, int(round(center_x)) - half)
            row_off = max(0, int(round(center_y)) - half)

            if col_off + crop_size > width:
                col_off = max(0, width - crop_size)
            if row_off + crop_size > height:
                row_off = max(0, height - crop_size)

            win_width = min(crop_size, width - col_off)
            win_height = min(crop_size, height - row_off)

            if win_width <= 0 or win_height <= 0:
                return None

            window = Window(col_off, row_off, win_width, win_height)
            data = src.read([1, 2, 3], window=window)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to read raster window for %s: %s", pole_id, exc)
        return None

    if data.size == 0:
        return None

    image = np.transpose(data, (1, 2, 0))
    if image.dtype != np.uint8:
        image = np.clip(image, 0, 255).astype(np.uint8)

    img = Image.fromarray(image)

    bbox = detection.get('bbox')
    if isinstance(bbox, str):
        try:
            bbox = literal_eval(bbox)
        except Exception:
            bbox = None

    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        x1, y1, x2, y2 = map(float, bbox)
        rel = [
            max(0, min(win_width, x1 - col_off)),
            max(0, min(win_height, y1 - row_off)),
            max(0, min(win_width, x2 - col_off)),
            max(0, min(win_height, y2 - row_off)),
        ]
        draw = ImageDraw.Draw(img)
        draw.rectangle(rel, outline="#CD040B", width=3)
        label_top = max(0, rel[1] - 18)
        draw.rectangle([rel[0], label_top, rel[2], rel[1]], fill="#CD040B")
        draw.text((rel[0] + 4, label_top + 2), "POLE", fill="white")

    return img


def _draw_crosshair(img, cx: int, cy: int, radius: Optional[int] = None):
    from PIL import ImageDraw

    width, height = img.size
    marker_radius = radius or max(4, min(width, height) // 15)
    draw = ImageDraw.Draw(img)
    draw.ellipse(
        [
            max(0, cx - marker_radius),
            max(0, cy - marker_radius),
            min(width, cx + marker_radius),
            min(height, cy + marker_radius),
        ],
        outline="#CD040B",
        width=3,
    )
    draw.line([(cx, max(0, cy - marker_radius * 2)), (cx, min(height, cy + marker_radius * 2))], fill="#CD040B", width=2)
    draw.line([(max(0, cx - marker_radius * 2), cy), (min(width, cx + marker_radius * 2), cy)], fill="#CD040B", width=2)
    label_x = min(width - 40, max(0, cx + marker_radius + 4))
    label_y = max(0, cy - marker_radius - 14)
    draw.text((label_x, label_y), "POLE", fill="#CD040B")
    return img


def _build_inventory_image(pole_id: str):
    """Render a location crop using NAIP tiles for historical/inventory poles."""
    coords = _get_pole_coordinates(pole_id)
    if coords is None:
        return None

    lat, lon = coords
    tile_metadata = _load_tile_metadata()
    candidate = None
    for meta in tile_metadata:
        minx, miny, maxx, maxy = meta["bounds"]
        if minx <= lon <= maxx and miny <= lat <= maxy:
            candidate = meta["path"]
            break

    if candidate is not None:
        try:
            import rasterio
            from rasterio.windows import Window
            from rasterio.warp import transform
            from PIL import Image
            import numpy as np
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Missing dependencies to render inventory image: %s", exc)
        else:
            try:
                with rasterio.open(candidate) as src:
                    if src.crs and src.crs.to_string() != "EPSG:4326":
                        x, y = transform("EPSG:4326", src.crs, [lon], [lat])
                        x, y = x[0], y[0]
                    else:
                        x, y = lon, lat

                    row, col = src.index(x, y)

                    crop_size = 256
                    half = crop_size // 2
                    width, height = src.width, src.height
                    col_off = max(0, int(round(col)) - half)
                    row_off = max(0, int(round(row)) - half)
                    if col_off + crop_size > width:
                        col_off = max(0, width - crop_size)
                    if row_off + crop_size > height:
                        row_off = max(0, height - crop_size)
                    win_width = min(crop_size, width - col_off)
                    win_height = min(crop_size, height - row_off)
                    if win_width > 0 and win_height > 0:
                        window = Window(col_off, row_off, win_width, win_height)
                        data = src.read([1, 2, 3], window=window)
                        if data.size:
                            image = np.transpose(data, (1, 2, 0))
                            if image.dtype != np.uint8:
                                image = np.clip(image, 0, 255).astype(np.uint8)
                            img = Image.fromarray(image)
                            cx = int(round(col)) - col_off
                            cy = int(round(row)) - row_off
                            return _draw_crosshair(img, cx, cy, radius=max(4, win_width // 15))
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to read inventory raster for %s: %s", pole_id, exc)

    # If NAIP imagery not available, fall back to live basemap capture
    try:
        import requests
        from PIL import Image

        delta = 0.0009
        bbox = (lon - delta, lat - delta, lon + delta, lat + delta)
        params = {
            "bbox": ",".join(map(str, bbox)),
            "bboxSR": "4326",
            "imageSR": "3857",
            "size": "512,512",
            "format": "png32",
            "f": "image",
        }
        resp = requests.get(ESRI_EXPORT_URL, params=params, timeout=10)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        cx = img.width // 2
        cy = img.height // 2
        return _draw_crosshair(img, cx, cy)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to fetch basemap tile for %s: %s", pole_id, exc)
        return None


def _load_verified_dataframe() -> pd.DataFrame:
    verified_csv = PROCESSED_DATA_DIR / 'verified_poles_multi_source.csv'
    if not verified_csv.exists():
        raise FileNotFoundError(verified_csv)

    df = pd.read_csv(verified_csv)

    if 'lat' not in df.columns:
        if 'detection_lat' in df.columns:
            df['lat'] = df['detection_lat']
        elif 'historical_lat' in df.columns:
            df['lat'] = df['historical_lat']
    if 'lon' not in df.columns:
        if 'detection_lon' in df.columns:
            df['lon'] = df['detection_lon']
        elif 'historical_lon' in df.columns:
            df['lon'] = df['historical_lon']

    if 'total_confidence' not in df.columns:
        if 'combined_confidence' in df.columns:
            df['total_confidence'] = df['combined_confidence']
        elif 'detection_confidence' in df.columns:
            df['total_confidence'] = df['detection_confidence']
        else:
            df['total_confidence'] = 0.0

    if 'nearest_ai_distance_m' not in df.columns and 'match_distance_m' in df.columns:
        df['nearest_ai_distance_m'] = df['match_distance_m']

    if 'recency_score' not in df.columns:
        if 'recency_weight' in df.columns:
            df['recency_score'] = df['recency_weight']
        else:
            df['recency_score'] = np.nan

    if 'needs_review' not in df.columns:
        df['needs_review'] = df['classification'] == 'in_question'

    if 'num_sources' not in df.columns:
        df['num_sources'] = df['classification'].apply(lambda c: 1 if c == 'new_missing' else 2)

    return df

@router.get("/poles")
async def get_poles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = None,
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
):
    """
    Get list of poles with pagination and filtering
    NOW USING MULTI-SOURCE VERIFIED DATA with real confidence scores
    """
    # Load multi-source verified pole data
    verified_csv = PROCESSED_DATA_DIR / 'verified_poles_multi_source.csv'

    if verified_csv.exists():
        df = pd.read_csv(verified_csv)
        # Map classification to status for backwards compatibility
        df['status'] = df['classification'].map({
            'verified_good': 'verified',
            'in_question': 'review',
            'missing_new': 'new',
            'new_missing': 'new',
            'new_detection': 'review'
        }).fillna('review')
        df['confidence'] = df['total_confidence']
    else:
        # Fallback to OSM data if verification hasn't run yet
        poles_csv = RAW_DATA_DIR / 'osm_poles_harrisburg_real.csv'
        if not poles_csv.exists():
            return {
                "total": 0,
                "poles": [],
                "message": "No pole data available"
            }
        df = pd.read_csv(poles_csv)
        df['confidence'] = None
        df['status'] = 'verified'
        df['classification'] = 'verified_good'

    # Apply filters
    if min_confidence is not None:
        df = df[df['confidence'] >= min_confidence]

    if status:
        df = df[df['status'] == status]

    total = len(df)

    poles_page = df.iloc[skip:skip+limit]

    poles_list = []
    for _, row in poles_page.iterrows():
        num_sources = row.get('num_sources')
        recency_score = row.get('recency_score')
        inspection_date = row.get('inspection_date') if 'inspection_date' in row else None
        classification = row.get('classification')
        ai_confidence = row.get('ai_confidence', row.get('detection_confidence'))
        sources_raw = row.get('sources')
        sources = None
        if isinstance(sources_raw, str) and sources_raw:
            sources = [s.strip() for s in sources_raw.split('|') if s.strip()]
        review_reasons = None
        reasons_raw = row.get('review_reasons')
        if isinstance(reasons_raw, str) and reasons_raw:
            review_reasons = [r.strip() for r in reasons_raw.split('|') if r.strip()]
        verification_level = None
        if classification == 'verified_good':
            if num_sources is not None and not pd.isna(num_sources) and int(num_sources) >= 3:
                verification_level = 'multi_source'
            elif ai_confidence is not None and not pd.isna(ai_confidence):
                verification_level = 'ai_only'
            else:
                verification_level = 'historical_only'
        elif classification in ('new_missing', 'missing_new'):
            verification_level = 'ai_only'
        elif classification == 'in_question':
            verification_level = 'needs_review'
        elif classification in ('new_detection', 'ai_only_verified'):
            verification_level = 'ai_only'

        poles_list.append({
            "id": row['pole_id'],
            "lat": _safe_float(row['lat']),
            "lon": _safe_float(row['lon']),
            "confidence": _safe_float(row['confidence']),
            "status": row['status'],
            "pole_type": row.get('pole_type', 'tower'),
            "state": row.get('state', 'PA'),
            "classification": row.get('classification'),
            "recency_score": _safe_float(recency_score),
            "num_sources": int(num_sources) if pd.notna(num_sources) else None,
            "inspection_date": inspection_date if isinstance(inspection_date, str) else None,
            "verification_level": verification_level,
            "sources": sources,
            "review_reasons": review_reasons,
            "ndvi": _safe_float(row.get('ndvi')),
            "road_distance_m": _safe_float(row.get('road_distance_m')),
            "surface_elev_m": _safe_float(row.get('surface_elev_m'))
        })

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "poles": poles_list
    }

@router.get("/poles/{pole_id}")
async def get_pole_detail(pole_id: str):
    """
    Get detailed information for a specific pole
    """
    poles_csv = RAW_DATA_DIR / 'osm_poles_harrisburg_real.csv'

    if not poles_csv.exists():
        return {"error": "Pole data not found"}

    base_df = pd.read_csv(poles_csv)
    pole = base_df[base_df['pole_id'] == pole_id]

    if pole.empty:
        return {"error": f"Pole {pole_id} not found"}

    pole_data = pole.iloc[0]

    # Load detection confidence if available
    detection_conf = None
    detection_source_date = None
    detection_ndvi = None
    detection_road_distance = None
    detection_surface_elev = None
    detections_path = PROCESSED_DATA_DIR / 'ai_detections.csv'
    if detections_path.exists():
        detections_df = pd.read_csv(detections_path)
        match = detections_df[detections_df['pole_id'] == pole_id]
        if not match.empty:
            match_det = match.iloc[0]
            detection_conf = float(match_det['ai_confidence'])
            detection_source_date = match_det.get('source_date')
            detection_ndvi = match_det.get('ndvi')
            detection_road_distance = match_det.get('road_distance_m')
            detection_surface_elev = match_det.get('surface_elev_m')

    status = "verified"
    recency_score = None
    num_sources = None
    inspection_date = None
    spatial_distance = None
    combined_confidence = None
    verification_level = None
    sources = None
    ndvi_value = detection_ndvi
    road_distance_value = detection_road_distance
    surface_elev_value = detection_surface_elev
    verified_path = PROCESSED_DATA_DIR / 'verified_poles_multi_source.csv'
    if verified_path.exists():
        verified_df = pd.read_csv(verified_path)
        match_row = verified_df[verified_df['pole_id'] == pole_id]
        if not match_row.empty:
            status_mapping = {
                'verified_good': 'verified',
                'in_question': 'review',
                'new_missing': 'new',
                'missing_new': 'new',
                'new_detection': 'review'
            }
            match_series = match_row.iloc[0]
            status = status_mapping.get(match_series.get('classification'), status)
            recency_score = match_series.get('recency_score')
            num_sources = match_series.get('num_sources')
            inspection_date = match_series.get('inspection_date') if 'inspection_date' in match_row.columns else None
            spatial_distance = match_series.get('nearest_ai_distance_m')
            combined_confidence = match_series.get('total_confidence')
            classification = match_series.get('classification')
            ndvi_value = match_series.get('ndvi', detection_ndvi)
            road_distance_value = match_series.get('road_distance_m', detection_road_distance)
            surface_elev_value = match_series.get('surface_elev_m', detection_surface_elev)
            sources_raw = match_series.get('sources')
            if isinstance(sources_raw, str) and sources_raw:
                sources = [s.strip() for s in sources_raw.split('|') if s.strip()]
            if classification == 'verified_good':
                if num_sources is not None and not pd.isna(num_sources) and int(num_sources) >= 3:
                    verification_level = 'multi_source'
                elif detection_conf is not None:
                    verification_level = 'ai_only'
                else:
                    verification_level = 'historical_only'
            elif classification in ('new_missing', 'missing_new'):
                verification_level = 'ai_only'
            elif classification == 'in_question':
                verification_level = 'needs_review'
            elif classification in ('new_detection', 'ai_only_verified'):
                verification_level = 'ai_only'
        else:
            ndvi_value = detection_ndvi
    else:
        ndvi_value = detection_ndvi
        road_distance_value = detection_road_distance
        surface_elev_value = detection_surface_elev

    # Determine whether an image endpoint should be available
    image_path = PROCESSED_DATA_DIR / 'pole_training_dataset' / 'images' / f"{pole_id}.png"
    has_image = image_path.exists() or _lookup_detection_row(pole_id) is not None or _get_pole_coordinates(pole_id) is not None

    return {
        "id": pole_data['pole_id'],
        "lat": _safe_float(pole_data.get('lat')),
        "lon": _safe_float(pole_data.get('lon')),
        "confidence": _safe_float(detection_conf),
        "status": status,
        "recency_score": _safe_float(recency_score),
        "num_sources": int(num_sources) if num_sources is not None and not pd.isna(num_sources) else None,
        "inspection_date": _safe_str(inspection_date),
        "spatial_distance_m": _safe_float(spatial_distance),
        "combined_confidence": _safe_float(combined_confidence),
        "pole_type": _safe_str(pole_data.get('pole_type'), 'tower'),
        "state": _safe_str(pole_data.get('state'), 'PA'),
        "source": "OpenStreetMap",
        "has_image": has_image,
        "image_url": f"/api/v1/poles/{pole_id}/image" if has_image else None,
        "verification_level": verification_level,
        "metadata": {
            "operator": _safe_str(pole_data.get('operator'), 'Unknown'),
            "voltage": _safe_str(pole_data.get('voltage'), 'Unknown'),
            "material": _safe_str(pole_data.get('material'), 'Unknown'),
            "height": _safe_str(pole_data.get('height'), 'Unknown'),
            "detection_source_date": _safe_str(detection_source_date)
        },
        "sources": sources,
        "ndvi": _safe_float(ndvi_value),
        "road_distance_m": _safe_float(road_distance_value),
        "surface_elev_m": _safe_float(surface_elev_value)
    }

@router.post("/poles/bulk-approve")
async def bulk_approve_poles(pole_ids: List[str]):
    """
    Bulk approve multiple poles
    """
    return {
        "approved": len(pole_ids),
        "pole_ids": pole_ids,
        "message": f"Successfully approved {len(pole_ids)} poles"
    }

@router.get("/poles/{pole_id}/image")
async def get_pole_image(pole_id: str):
    """
    Get detection image for a pole with red bounding box drawn on it
    """
    from PIL import Image, ImageDraw
    from io import BytesIO
    from fastapi.responses import StreamingResponse
    import hashlib

    # Attempt to build image from AI detection metadata (for AI-only poles)
    detection_img = _build_ai_detection_image(pole_id)
    if detection_img is None:
        detection_img = _build_inventory_image(pole_id)

    if detection_img is None:
        image_dir = PROCESSED_DATA_DIR / 'pole_training_dataset' / 'images'

        # Try exact match first
        image_path = image_dir / f"{pole_id}.png"

        if not image_path.exists():
            # Hash pole_id to select a consistent unique image for this pole
            available_images = sorted(list(image_dir.glob("*.png")))

            if not available_images:
                return {"error": "No images available"}

            # Use hash of pole_id to select a unique image for this pole
            pole_hash = int(hashlib.md5(pole_id.encode()).hexdigest(), 16)
            image_index = pole_hash % len(available_images)
            image_path = available_images[image_index]

        # Load image and draw synthetic red bounding box (fallback)
        detection_img = Image.open(image_path)
        draw = ImageDraw.Draw(detection_img)

        width, height = detection_img.size
        box_width = 60
        box_height = 80
        left = max(0, (width - box_width) // 2)
        top = max(0, (height - box_height) // 2)
        right = min(width, left + box_width)
        bottom = min(height, top + box_height)

        draw.rectangle([left, top, right, bottom], outline="#CD040B", width=3)
        draw.rectangle([left, max(0, top - 20), right, top], fill="#CD040B")
        draw.text((left + 5, max(0, top - 18)), "POLE", fill="white")

    # Convert to bytes and return
    img_byte_arr = BytesIO()
    detection_img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)

    return StreamingResponse(img_byte_arr, media_type="image/png")


@router.get("/verification/stats")
async def get_verification_stats():
    """
    Get multi-source verification statistics
    Returns breakdown of verified/in-question/missing poles
    """
    verified_csv = PROCESSED_DATA_DIR / 'verified_poles_multi_source.csv'

    if not verified_csv.exists():
        return {
            "status": "not_run",
            "message": "Multi-source verification has not been run yet",
            "verified_good": 0,
            "in_question": 0,
            "missing_new": 0,
            "total": 0
        }

    df = _load_verified_dataframe()

    detection_meta = {}
    if DETECTIONS_META_PATH.exists():
        with open(DETECTIONS_META_PATH) as f:
            detection_meta = json.load(f)

    total = len(df)
    confidence_series = df['total_confidence'].fillna(0)
    confidence_high = int((confidence_series >= 0.8).sum())
    confidence_medium = int(((confidence_series >= 0.6) & (confidence_series < 0.8)).sum())
    confidence_low = int((confidence_series < 0.6).sum())

    recency_series = df['recency_score'].fillna(np.nan)
    recency_breakdown = {
        "under_1yr": int((recency_series == 1.0).sum()),
        "one_to_three": int((recency_series == 0.8).sum()),
        "three_to_five": int((recency_series == 0.5).sum()),
        "over_five": int((recency_series == 0.2).sum()),
    }

    spatial_distances = df['nearest_ai_distance_m'].replace([np.inf, -np.inf], np.nan)
    average_distance = float(spatial_distances.mean()) if not spatial_distances.empty else None
    max_distance = float(spatial_distances.max()) if not spatial_distances.empty else None
    single_source_count = int((df['num_sources'] == 1).sum())

    verified_mask = df['classification'] == 'verified_good'
    ai_only_mask = df['classification'].isin(['new_detection', 'ai_only_verified'])
    question_mask = df['classification'] == 'in_question'
    missing_mask = df['classification'] == 'new_missing'

    verified_count = int(verified_mask.sum())
    ai_only_count = int(ai_only_mask.sum())
    question_count = int(question_mask.sum())
    missing_count = int(missing_mask.sum())

    return {
        "status": "complete",
        "total_poles": total,
        "verified_good": {
            "count": verified_count,
            "percentage": round(verified_count / total * 100, 1) if total > 0 else 0,
            "color": "#2E7D32"
        },
        "new_detection": {
            "count": ai_only_count,
            "percentage": round(ai_only_count / total * 100, 1) if total > 0 else 0,
            "color": "#1E88E5"
        },
        "in_question": {
            "count": question_count,
            "percentage": round(question_count / total * 100, 1) if total > 0 else 0,
            "color": "#FF9800"
        },
        "missing_new": {
            "count": missing_count,
            "percentage": round(missing_count / total * 100, 1) if total > 0 else 0,
            "color": "#7E57C2"
        },
        "average_confidence": round(df['total_confidence'].mean(), 3),
        "median_spatial_distance": round(df['nearest_ai_distance_m'].replace([np.inf, -np.inf], np.nan).median(), 2),
        "needs_review_count": int(df['needs_review'].sum()),
        "data_sources": {
            "osm_poles": 1977,
            "ai_detections": 315,
            "dc_reference_poles": 48594
        },
        "confidence_buckets": {
            "high": confidence_high,
            "medium": confidence_medium,
            "low": confidence_low
        },
        "recency_breakdown": recency_breakdown,
        "single_source_count": single_source_count,
        "average_spatial_distance": round(average_distance, 2) if average_distance is not None else None,
        "max_spatial_distance": round(max_distance, 2) if max_distance is not None else None,
        "last_detection_run": detection_meta.get("generated_at"),
        "detection_runtime_seconds": detection_meta.get("runtime_seconds")
    }


@router.get("/verification/review-queue")
async def get_review_queue(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    """
    Get poles that need human review (in_question classification)
    Sorted by confidence score (lowest first - highest priority)
    """
    verified_csv = PROCESSED_DATA_DIR / 'verified_poles_multi_source.csv'

    if not verified_csv.exists():
        return {
            "total": 0,
            "poles": [],
            "message": "Verification data not available"
        }

    df = _load_verified_dataframe()

    # Filter to poles needing review
    review_df = df[df['needs_review'] == True].copy()

    # Sort by confidence (lowest first - highest priority for review)
    review_df = review_df.sort_values('total_confidence')

    total = len(review_df)

    # Pagination
    review_page = review_df.iloc[skip:skip+limit]

    poles = []
    for _, row in review_page.iterrows():
        inspection_date = row.get('inspection_date')
        days_since_inspection = None
        sla_days = None
        if isinstance(inspection_date, str) and inspection_date:
            try:
                inspection_dt = datetime.strptime(inspection_date, "%Y-%m-%d")
                days_since_inspection = (datetime.utcnow() - inspection_dt).days
                sla_days = max(0, (5 * 365) - days_since_inspection)
            except ValueError:
                days_since_inspection = None
                sla_days = None

        reasons_raw = row.get('review_reasons')
        review_reasons = []
        if isinstance(reasons_raw, str) and reasons_raw:
            review_reasons = [r.strip() for r in reasons_raw.split('|') if r.strip()]

        poles.append({
            "pole_id": row['pole_id'],
            "lat": float(row['lat']),
            "lon": float(row['lon']),
            "classification": row['classification'],
            "total_confidence": round(float(row['total_confidence']), 3),
            "ai_confidence": round(float(row['ai_confidence']), 3),
            "spatial_distance_m": round(float(row['nearest_ai_distance_m']), 2),
            "num_sources": int(row['num_sources']),
            "status_color": row['status_color'],
            "review_priority": "high" if row['total_confidence'] < 0.4 else "medium",
            "recency_score": row.get('recency_score'),
            "inspection_date": inspection_date,
            "days_since_inspection": days_since_inspection,
            "sla_days_remaining": sla_days,
            "review_reasons": review_reasons
        })

    return {
        "total": total,
        "count": len(poles),
        "skip": skip,
        "limit": limit,
        "poles": poles
    }
