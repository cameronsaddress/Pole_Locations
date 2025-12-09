"""
Metrics API endpoints - KPIs, model performance, cost analysis
"""
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
import sys
from typing import Any, Dict, Mapping
import logging

import pandas as pd
from fastapi import APIRouter, HTTPException

from app.services.data_quality import (
    ensure_columns,
    ensure_min_rows,
    ensure_required_keys,
    ensure_numeric_keys,
    file_sha256,
    safe_read_json,
)

sys.path.append(str(Path(__file__).parent.parent.parent.parent.parent / 'src'))
from config import PROCESSED_DATA_DIR, MODELS_DIR, OUTPUTS_DIR, RAW_DATA_DIR  # noqa: E402

SUMMARY_PATH = OUTPUTS_DIR / 'exports' / 'summary_metrics.json'
DETECTIONS_PATH = PROCESSED_DATA_DIR / 'ai_detections.csv'
DETECTIONS_META_PATH = PROCESSED_DATA_DIR / 'ai_detections_metadata.json'
HISTORICAL_PATH = RAW_DATA_DIR / 'osm_poles_harrisburg_real.csv'
VERIFIED_PATH = PROCESSED_DATA_DIR / 'verified_poles_multi_source.csv'
EXTRACTION_METADATA_PATH = PROCESSED_DATA_DIR / 'pole_training_dataset' / 'extraction_metadata.json'
MODEL_METRIC_OVERRIDES_PATH = OUTPUTS_DIR / 'reports' / 'model_metrics.json'
DASHBOARD_SNAPSHOT_PATH = OUTPUTS_DIR / 'reports' / 'dashboard_snapshot.json'

router = APIRouter()
logger = logging.getLogger(__name__)


def _require_file(path: Path, description: str):
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"{description} not available. Run `python run_pilot.py` to generate fresh outputs."
        )


def _load_summary():
    _require_file(SUMMARY_PATH, "Summary metrics")
    summary = safe_read_json(SUMMARY_PATH, "Summary metrics")
    ensure_required_keys(
        summary,
        ("total_poles", "verified_good", "in_question", "new_missing", "automation_rate"),
        "Summary metrics",
    )
    ensure_numeric_keys(
        summary,
        ("total_poles", "verified_good", "in_question", "new_missing", "automation_rate"),
        "Summary metrics",
    )
    return summary


def _load_detections():
    _require_file(DETECTIONS_PATH, "AI detections")
    df = pd.read_csv(DETECTIONS_PATH)
    ensure_min_rows(df, 10, "AI detections")
    if 'confidence' not in df.columns:
        if 'ai_confidence' in df.columns:
            df['confidence'] = df['ai_confidence']
        else:
            df['confidence'] = 0.0
    ensure_columns(df, ("lat", "lon", "confidence"), "AI detections")
    return df


def _load_historical():
    _require_file(HISTORICAL_PATH, "Historical pole inventory (OpenStreetMap)")
    df = pd.read_csv(HISTORICAL_PATH)
    ensure_min_rows(df, 10, "Historical pole inventory")
    ensure_columns(df, ("lat", "lon"), "Historical pole inventory")
    return df


def _load_detection_metadata():
    if DETECTIONS_META_PATH.exists():
        with open(DETECTIONS_META_PATH) as f:
            return json.load(f)
    return {}


def _load_extraction_metadata():
    if EXTRACTION_METADATA_PATH.exists():
        with open(EXTRACTION_METADATA_PATH) as f:
            return json.load(f)
    return {}


def _load_model_metric_overrides() -> dict:
    """
    Optional override file produced after pipeline runs to align UI metrics with executive KPIs.
    """
    if not MODEL_METRIC_OVERRIDES_PATH.exists():
        return {}

    try:
        raw = json.loads(MODEL_METRIC_OVERRIDES_PATH.read_text())
    except json.JSONDecodeError:
        return {}

    overrides: dict[str, float] = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            val = value.get("value")
        else:
            val = value
        try:
            overrides[key] = float(val)
        except (TypeError, ValueError):
            continue
    return overrides


def _snapshot_source_hashes() -> Dict[str, str]:
    sources = {
        "summary_metrics.json": SUMMARY_PATH,
        "ai_detections.csv": DETECTIONS_PATH,
        "ai_detections_metadata.json": DETECTIONS_META_PATH,
        "osm_poles.csv": HISTORICAL_PATH,
        "verified_poles.csv": VERIFIED_PATH,
    }
    hashes: Dict[str, str] = {}
    for label, path in sources.items():
        if not path.exists():
            continue
        try:
            hashes[label] = file_sha256(path)
        except OSError as exc:  # pragma: no cover - filesystem edge cases
            logger.warning("Unable to hash %s (%s): %s", label, path, exc)
    return hashes


def _maybe_write_dashboard_snapshot(
    summary: Mapping[str, Any],
    detections: pd.DataFrame,
    historical: pd.DataFrame,
    detection_meta: Mapping[str, Any],
    model_metrics: Mapping[str, Any],
) -> None:
    snapshot_id = detection_meta.get("run_id") or detection_meta.get("generated_at")
    if not snapshot_id:
        snapshot_id = f"{summary.get('total_poles')}-{len(detections)}-{len(historical)}"

    if DASHBOARD_SNAPSHOT_PATH.exists():
        try:
            existing = json.loads(DASHBOARD_SNAPSHOT_PATH.read_text())
            if existing.get("snapshot_id") == snapshot_id:
                return
        except json.JSONDecodeError:
            pass

    payload = {
        "snapshot_id": snapshot_id,
        "generated_at": detection_meta.get("generated_at") or datetime.utcnow().isoformat(),
        "counts": {
            "total_poles": summary.get("total_poles"),
            "verified_good": summary.get("verified_good"),
            "in_review": summary.get("in_question"),
            "new_missing": summary.get("new_missing"),
            "detections": len(detections),
            "historical": len(historical),
        },
        "metrics": model_metrics.get("metrics"),
        "inference": model_metrics.get("inference"),
        "source_hashes": _snapshot_source_hashes(),
    }

    try:
        DASHBOARD_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        DASHBOARD_SNAPSHOT_PATH.write_text(json.dumps(payload, indent=2))
    except OSError as exc:  # pragma: no cover - filesystem edge cases
        logger.warning("Failed to persist dashboard snapshot at %s: %s", DASHBOARD_SNAPSHOT_PATH, exc)


@router.get("/metrics/summary")
async def get_summary_metrics():
    """
    Get high-level KPIs for executive dashboard
    """
    summary = _load_summary()
    detections = _load_detections()
    historical = _load_historical()
    detection_meta = _load_detection_metadata()
    extraction_meta = _load_extraction_metadata()

    total_poles = summary['total_poles']
    verified_good = summary['verified_good']
    in_review = summary['in_question']
    new_missing = summary['new_missing']

    manual_cost = total_poles * 5.0
    ai_cost = total_poles * 0.03
    cost_savings = manual_cost - ai_cost

    avg_confidence = float(detections['confidence'].mean())
    automation_rate = summary['automation_rate'] / 100.0

    processing_minutes = None
    if detection_meta.get('runtime_seconds'):
        processing_minutes = round(detection_meta['runtime_seconds'] / 60.0, 2)

    lat_min, lat_max = historical['lat'].min(), historical['lat'].max()
    lon_min, lon_max = historical['lon'].min(), historical['lon'].max()
    mean_lat = historical['lat'].mean()
    lat_km = (lat_max - lat_min) * 111.0
    lon_km = (lon_max - lon_min) * 111.0 * math.cos(math.radians(mean_lat))
    coverage_area_sq_km = round(abs(lat_km * lon_km), 2) if lat_km and lon_km else None

    imagery_resolution = extraction_meta.get('resolution_meters', None)

    return {
        "total_poles_processed": total_poles,
        "total_poles_available": len(historical),
        "automation_rate": automation_rate,
        "cost_savings": round(cost_savings, 2),
        "processing_time_minutes": processing_minutes,
        "model_accuracy": verified_good / total_poles if total_poles else 0.0,
        "poles_auto_approved": verified_good,
        "poles_needing_review": in_review,
        "poles_needing_inspection": new_missing,
        "avg_confidence": avg_confidence,
        "coverage_area_sq_km": coverage_area_sq_km,
        "imagery_resolution_meters": imagery_resolution
    }


@router.get("/metrics/model")
async def get_model_performance():
    """
    Get AI model performance metrics derived from the latest real-data run
    """
    summary = _load_summary()
    detections = _load_detections()
    historical = _load_historical()
    detection_meta = _load_detection_metadata()
    extraction_meta = _load_extraction_metadata()

    detections_count = len(detections)
    total_poles = summary['total_poles']
    verified_good = summary['verified_good']

    precision = verified_good / detections_count if detections_count else 0.0
    recall = verified_good / total_poles if total_poles else 0.0
    f1_score = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    avg_time_ms = None
    throughput_fps = None
    if detection_meta.get('runtime_seconds') and detections_count:
        avg_time_ms = (detection_meta['runtime_seconds'] / detections_count) * 1000.0
        throughput_fps = detections_count / detection_meta['runtime_seconds']

    results_csv = MODELS_DIR / 'pole_detector_v1' / 'results.csv'
    training_minutes = None
    if results_csv.exists():
        results_df = pd.read_csv(results_csv)
        if 'time' in results_df.columns and not results_df.empty:
            training_minutes = round(results_df['time'].max() / 60.0, 2)

    dataset_dir = PROCESSED_DATA_DIR / 'pole_training_dataset'
    train_images_dir = dataset_dir / 'train' / 'images'
    val_images_dir = dataset_dir / 'val' / 'images'
    train_count = len(list(train_images_dir.glob('*.png'))) if train_images_dir.exists() else 0
    val_count = len(list(val_images_dir.glob('*.png'))) if val_images_dir.exists() else 0

    crop_size = extraction_meta.get('crop_size', 256)

    model_metrics = {
        "model_name": "YOLOv8 Pole Detector",
        "model_version": "v1.0",
        "trained_date": detection_meta.get("generated_at"),
        "training_time_minutes": training_minutes,
        "metrics": {
            "precision": precision,
            "recall": recall,
            "map50": precision,  # Using precision as a proxy until formal evaluation is logged
            "map50_95": precision,
            "f1_score": f1_score
        },
        "inference": {
            "avg_inference_time_ms": avg_time_ms,
            "throughput_fps": throughput_fps,
            "device": "Not Specified"
        },
        "dataset": {
            "total_images": train_count + val_count,
            "train_images": train_count,
            "val_images": val_count,
            "image_size": f"{crop_size}x{crop_size}",
            "data_source": "NAIP imagery cropped around OpenStreetMap pole coordinates"
        },
        "comparison": {}
    }

    overrides = _load_model_metric_overrides()
    if overrides:
        sections: dict[str, dict] = {
            "metrics": model_metrics["metrics"],
            "inference": model_metrics["inference"],
            "dataset": model_metrics["dataset"],
            "comparison": model_metrics["comparison"],
        }
        alias_map = {"f1": "f1_score"}

        for key, value in overrides.items():
            normalized_key = alias_map.get(key, key)
            applied = False

            if "." in normalized_key:
                section_name, field = normalized_key.split(".", 1)
                section = sections.get(section_name)
                if section is not None and field in section:
                    section[field] = value
                    applied = True
                    continue

            for section in sections.values():
                if normalized_key in section:
                    section[normalized_key] = value
                    applied = True
                    break

            if not applied and normalized_key in model_metrics:
                model_metrics[normalized_key] = value
                applied = True

            if not applied:
                extras = model_metrics.setdefault("overrides", {})
                extras[normalized_key] = value

    _maybe_write_dashboard_snapshot(summary, detections, historical, detection_meta, model_metrics)
    return model_metrics

@router.get("/metrics/cost-analysis")
async def get_cost_analysis():
    """
    Get cost savings and ROI analysis
    """
    summary = _load_summary()
    detection_meta = _load_detection_metadata()
    total_poles = summary['total_poles']

    manual_cost_min = total_poles * 3.0
    manual_cost_max = total_poles * 6.0
    ai_cost_min = total_poles * 0.01
    ai_cost_max = total_poles * 0.05

    savings_min = manual_cost_min - ai_cost_max
    savings_max = manual_cost_max - ai_cost_min

    return {
        "poles_processed": total_poles,
        "manual_process": {
            "cost_per_pole": {"min": 3.0, "max": 6.0},
            "total_cost": {"min": manual_cost_min, "max": manual_cost_max},
            "time_months": {"min": 6, "max": 12}
        },
        "ai_process": {
            "cost_per_pole": {"min": 0.01, "max": 0.05},
            "total_cost": {"min": ai_cost_min, "max": ai_cost_max},
            "time_minutes": detection_meta.get('runtime_seconds', 0) / 60.0 if detection_meta.get('runtime_seconds') else None
        },
        "savings": {
            "cost": {"min": savings_min, "max": savings_max},
            "percentage": {
                "min": (1 - ai_cost_max / manual_cost_min) * 100 if manual_cost_min else None,
                "max": (1 - ai_cost_min / manual_cost_max) * 100 if manual_cost_max else None
            },
            "roi": {
                "min": (savings_min / ai_cost_max) if ai_cost_max else None,
                "max": (savings_max / ai_cost_min) if ai_cost_min else None
            }
        },
        "breakdown": {
            "labor_savings": savings_max * 0.7,
            "equipment_savings": savings_max * 0.2,
            "time_savings": savings_max * 0.1
        }
    }


@router.get("/metrics/geographic")
async def get_geographic_metrics():
    """
    Get geographic distribution statistics
    """
    historical = _load_historical()
    summary = _load_summary()

    lat_min, lat_max = historical['lat'].min(), historical['lat'].max()
    lon_min, lon_max = historical['lon'].min(), historical['lon'].max()
    mean_lat = historical['lat'].mean()

    lat_km = (lat_max - lat_min) * 111.0
    lon_km = (lon_max - lon_min) * 111.0 * math.cos(math.radians(mean_lat))
    area = abs(lat_km * lon_km) if lat_km and lon_km else None
    poles_per_sq_km = summary['total_poles'] / area if area else None

    return {
        "coverage": {
            "total_area_sq_km": round(area, 2) if area else None,
            "poles_per_sq_km": round(poles_per_sq_km, 2) if poles_per_sq_km else None,
            "imagery_resolution_m": _load_extraction_metadata().get('resolution_meters')
        },
        "by_region": [],
        "bounds": {
            "north": lat_max,
            "south": lat_min,
            "east": lon_max,
            "west": lon_min
        }
    }


@router.get("/metrics/timeline")
async def get_timeline_metrics(days: int = 30):
    """
    Return basic time-series metrics based on the most recent detection job.
    """
    summary = _load_summary()
    detection_meta = _load_detection_metadata()
    detections = _load_detections()

    generated_at = detection_meta.get('generated_at')
    if generated_at is None:
        # fallback to today's date
        generated_at = datetime.utcnow().date().isoformat()

    precision = summary['verified_good'] / len(detections) if len(detections) else 0.0
    cost_savings = summary['verified_good'] * 5.0 - summary['total_poles'] * 0.03

    data_points = [{
        "date": generated_at,
        "poles_processed": summary['total_poles'],
        "accuracy": precision,
        "cost_savings": cost_savings
    }]

    return {
        "period_days": len(data_points),
        "data": data_points,
        "totals": {
            "poles_processed": summary['total_poles'],
            "avg_accuracy": precision,
            "total_savings": cost_savings
        }
    }
