"""Mapillary labeling API endpoints for PoleVision AI."""

from __future__ import annotations

import json
import math
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, validator

import sys

sys.path.append(str(Path(__file__).parent.parent.parent.parent.parent / "src"))
from config import OUTPUTS_DIR, RAW_DATA_DIR  # noqa: E402

router = APIRouter()

QUEUE_DEFAULT = OUTPUTS_DIR / "labels" / "mapillary_label_queue.csv"
MAPILLARY_MULTI_ROOT = RAW_DATA_DIR / "mapillary_multi"
DEFAULT_IMAGE_ROOT = RAW_DATA_DIR / "street_level" / "mapillary"


def _ensure_queue(queue_path: Path) -> None:
    """Ensure a labeling queue exists; bootstrap from metadata when needed."""
    if queue_path.exists():
        df = pd.read_csv(queue_path)
    else:
        metadata_path = queue_path.parent / "mapillary_metadata.csv"
        if not metadata_path.exists():
            raise FileNotFoundError(f"Mapillary metadata not found for {queue_path.parent}")
        df = pd.read_csv(metadata_path)
        if "image_id" not in df.columns:
            raise ValueError(f"'image_id' column missing in {metadata_path}")
        df["relative_path"] = df["image_id"].astype(str).map(lambda img_id: f"images/{img_id}.jpg")
    for column in ("pole_present", "confidence", "notes"):
        if column not in df.columns:
            df[column] = ""
        if column in {"pole_present", "notes"}:
            df[column] = df[column].fillna("")
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(queue_path, index=False)


def _get_queue_path(dataset: str) -> Path:
    dataset = dataset.strip() if dataset else "default"
    if dataset in ("default", "", "prepared"):
        if not QUEUE_DEFAULT.exists():
            _ensure_queue(QUEUE_DEFAULT)
        return QUEUE_DEFAULT
    slug_dir = MAPILLARY_MULTI_ROOT / dataset
    queue_path = slug_dir / "mapillary_label_queue.csv"
    _ensure_queue(queue_path)
    return queue_path


def _format_dataset_name(slug: str) -> str:
    return slug.replace("_", " ").title()


def _load_queue(dataset: str) -> pd.DataFrame:
    queue_path = _get_queue_path(dataset)
    df = pd.read_csv(queue_path)
    for column in ("pole_present", "confidence", "notes"):
        if column not in df.columns:
            df[column] = ""
        if column in {"pole_present", "notes"}:
            df[column] = df[column].fillna("")
    if "relative_path" not in df.columns:
        df["relative_path"] = df["image_id"].astype(str).map(lambda img_id: f"images/{img_id}.jpg")
    return df


class LabelRequest(BaseModel):
    dataset: str = Field(default="default")
    image_id: str
    pole_present: str
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    notes: Optional[str] = None

    @validator("pole_present")
    def validate_label(cls, value: str) -> str:
        allowed = {"pole", "negative", "unsure"}
        value = value.strip().lower()
        if value not in allowed:
            raise ValueError(f"pole_present must be one of {', '.join(sorted(allowed))}")
        return value


@router.get("/mapillary/datasets")
async def list_mapillary_datasets():
    """List all available Mapillary labeling datasets with progress stats."""
    datasets: List[Dict[str, object]] = []

    if QUEUE_DEFAULT.exists():
        df = _load_queue("default")
        unlabeled = int((df["pole_present"].astype(str).str.strip() == "").sum())
        datasets.append(
            {
                "id": "default",
                "name": "Prepared Queue",
                "total": int(len(df)),
                "remaining": unlabeled,
                "root": str(QUEUE_DEFAULT.parent),
            }
        )

    if MAPILLARY_MULTI_ROOT.exists():
        for slug_dir in sorted(p for p in MAPILLARY_MULTI_ROOT.iterdir() if p.is_dir()):
            metadata_path = slug_dir / "mapillary_metadata.csv"
            queue_path = slug_dir / "mapillary_label_queue.csv"
            if not metadata_path.exists() and not queue_path.exists():
                continue
            df = _load_queue(slug_dir.name)
            unlabeled = int((df["pole_present"].astype(str).str.strip() == "").sum())
            datasets.append(
                {
                    "id": slug_dir.name,
                    "name": f"Mapillary – {_format_dataset_name(slug_dir.name)}",
                    "total": int(len(df)),
                    "remaining": unlabeled,
                    "root": str(slug_dir),
                }
            )

    if not datasets:
        raise HTTPException(status_code=404, detail="No Mapillary datasets found.")

    return {"datasets": datasets}


@router.get("/mapillary/queue")
async def get_next_mapillary_item(
    dataset: str = Query(default="default"),
    include_labeled: bool = Query(default=False),
) -> JSONResponse:
    """Fetch the next item in the queue for labeling."""
    df = _load_queue(dataset)
    if include_labeled:
        subset = df
    else:
        mask_unlabeled = df["pole_present"].astype(str).str.strip() == ""
        subset = df[mask_unlabeled]

    if subset.empty:
        raise HTTPException(status_code=404, detail="No images remaining for labeling in this dataset.")

    row = subset.iloc[0]
    image_id = str(row.get("image_id", row.name))
    relative_path = str(row.get("relative_path", f"images/{image_id}.jpg"))

    metadata_keys = ["lat", "lon", "capture_time", "sequence_id", "camera_type", "thumb_url"]
    metadata = {}
    for key in metadata_keys:
        value = row.get(key)
        if isinstance(value, (float, int)) and (math.isnan(value) or math.isinf(value)):
            value = None
        metadata[key] = None if pd.isna(value) else value

    queue_path = _get_queue_path(dataset)
    total = int(len(df))
    remaining = int((df["pole_present"].astype(str).str.strip() == "").sum())

    raw_label = row.get("pole_present")
    if isinstance(raw_label, str):
        pole_present = raw_label.strip() or None
    else:
        pole_present = None

    entry = {
        "dataset": dataset,
        "row_index": int(row.name),
        "image_id": image_id,
        "relative_path": relative_path,
        "pole_present": pole_present,
        "confidence": float(row["confidence"]) if str(row.get("confidence", "")).strip() not in ("", "nan") else None,
        "notes": (row.get("notes") or "").strip(),
        "metadata": metadata,
        "image_url": f"/api/v1/mapillary/image?dataset={dataset}&image_id={image_id}",
    }

    return JSONResponse(
        {
            "dataset": dataset,
            "total": total,
            "remaining": remaining,
            "entry": entry,
            "queue_path": str(queue_path),
        }
    )


@router.get("/mapillary/image")
async def get_mapillary_image(dataset: str = Query(default="default"), image_id: str = Query(...)):
    """Serve the raw Mapillary thumbnail for labeling."""
    df = _load_queue(dataset)
    matches = df[df["image_id"].astype(str) == str(image_id)]
    if matches.empty:
        raise HTTPException(status_code=404, detail=f"Image {image_id} not found in dataset {dataset}.")
    row = matches.iloc[0]
    relative_path = str(row.get("relative_path", f"images/{image_id}.jpg"))
    queue_path = _get_queue_path(dataset)
    base_dirs = [queue_path.parent]
    if dataset in ("default", "", "prepared"):
        base_dirs.append(DEFAULT_IMAGE_ROOT)

    image_path: Optional[Path] = None
    for root in base_dirs:
        candidate = Path(relative_path)
        if not candidate.is_absolute():
            candidate = root / candidate
        if candidate.exists():
            image_path = candidate
            break
        fallback = root / "images" / f"{image_id}.jpg"
        if fallback.exists():
            image_path = fallback
            break

    if image_path is None:
        raise HTTPException(status_code=404, detail=f"Image file missing: {relative_path}")
    return FileResponse(image_path)


@router.post("/mapillary/label")
async def submit_mapillary_label(payload: LabelRequest = Body(...)):
    """Persist a reviewer label for a Mapillary thumbnail."""
    df = _load_queue(payload.dataset)
    matches = df[df["image_id"].astype(str) == str(payload.image_id)]
    if matches.empty:
        raise HTTPException(status_code=404, detail=f"Image {payload.image_id} not found.")

    idx = matches.index[0]
    df.loc[idx, "pole_present"] = payload.pole_present

    if payload.confidence is None:
        df.loc[idx, "confidence"] = ""
    else:
        df.loc[idx, "confidence"] = float(payload.confidence)

    df.loc[idx, "notes"] = payload.notes or ""

    queue_path = _get_queue_path(payload.dataset)
    tmp_path = queue_path.with_suffix(".tmp.csv")
    df.to_csv(tmp_path, index=False)
    tmp_path.replace(queue_path)

    remaining = int((df["pole_present"].astype(str).str.strip() == "").sum())

    return {
        "status": "success",
        "dataset": payload.dataset,
        "image_id": payload.image_id,
        "remaining": remaining,
        "total": int(len(df)),
    }
