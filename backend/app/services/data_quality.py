"""Helpers for enforcing data integrity on dashboard inputs."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd
from fastapi import HTTPException

LOGGER = logging.getLogger(__name__)


def ensure_columns(df: pd.DataFrame, required: Iterable[str], dataset_name: str) -> None:
    """Raise an HTTP error if any required dataframe columns are missing."""
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"{dataset_name} missing required columns: {', '.join(sorted(missing))}",
        )


def ensure_min_rows(df: pd.DataFrame, min_rows: int, dataset_name: str) -> None:
    """Ensure datasets contain at least ``min_rows`` rows before we trust metrics."""
    if len(df) < min_rows:
        raise HTTPException(
            status_code=503,
            detail=f"{dataset_name} only has {len(df)} rows; rerun the pipeline to refresh data.",
        )


def ensure_required_keys(data: Mapping[str, object], required: Iterable[str], dataset_name: str) -> None:
    """Ensure JSON-like payloads expose the required keys."""
    missing = [key for key in required if key not in data]
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"{dataset_name} missing keys: {', '.join(sorted(missing))}",
        )


def ensure_numeric_keys(data: Mapping[str, object], numeric_keys: Iterable[str], dataset_name: str) -> None:
    """Ensure each listed key can be interpreted as a number."""
    problematic = []
    for key in numeric_keys:
        value = data.get(key)
        try:
            float(value)
        except (TypeError, ValueError):
            problematic.append(key)
    if problematic:
        raise HTTPException(
            status_code=503,
            detail=f"{dataset_name} contains non-numeric values for: {', '.join(sorted(problematic))}",
        )


def safe_read_json(path: Path, description: str) -> Mapping[str, object]:
    """Load a JSON file and surface failures as 503 errors."""
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"{description} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=503, detail=f"{description} is invalid JSON: {path}") from exc


def file_sha256(path: Path) -> str:
    """Compute a SHA256 hash for provenance tracking."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "ensure_columns",
    "ensure_min_rows",
    "ensure_required_keys",
    "ensure_numeric_keys",
    "safe_read_json",
    "file_sha256",
]
