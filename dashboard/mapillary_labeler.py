#!/usr/bin/env python
"""
Streamlit-powered Mapillary labeling workflow.

Displays one street-level thumbnail at a time and lets a reviewer tag
it as "Pole", "Not a pole", or "Unsure". The selections are written
back to the queue CSV so downstream scripts can ingest the labels.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd
import streamlit as st
from PIL import Image


QUEUE_DEFAULT = Path("outputs/labels/mapillary_label_queue.csv")
MAPILLARY_MULTI_ROOT = Path("data/raw/mapillary_multi")


def _ensure_queue(queue_path: Path, metadata_path: Path | None = None) -> None:
    """
    Make sure the queue CSV exists with the required columns.
    Optionally bootstrap from a metadata CSV if the queue does not yet exist.
    """
    if queue_path.exists():
        df = pd.read_csv(queue_path)
    else:
        if metadata_path is None or not metadata_path.exists():
            raise FileNotFoundError(f"Neither queue nor metadata found for {queue_path}")
        df = pd.read_csv(metadata_path)
        if "image_id" not in df.columns:
            raise ValueError(f"Metadata {metadata_path} missing required 'image_id' column")
        # Create relative paths pointing to the images/ folder beside the metadata.
        image_rel_prefix = Path("images")
        df["relative_path"] = df["image_id"].astype(str).map(lambda img_id: str(image_rel_prefix / f"{img_id}.jpg"))

    for column, default in (("pole_present", ""), ("confidence", ""), ("notes", "")):
        if column not in df.columns:
            df[column] = default

    df.to_csv(queue_path, index=False)


@st.cache_data(show_spinner=False)
def _load_queue(queue_path: Path) -> pd.DataFrame:
    df = pd.read_csv(queue_path)
    for column in ("pole_present", "confidence", "notes"):
        if column not in df.columns:
            df[column] = ""
    return df


def _list_datasets() -> Dict[str, Tuple[Path, Path]]:
    """
    Build a mapping of dataset label -> (queue_path, base_dir_for_images).
    If a queue does not exist yet but metadata does, bootstrap it.
    """
    datasets: Dict[str, Tuple[Path, Path]] = {}

    if QUEUE_DEFAULT.exists():
        datasets["Prepared Queue (outputs/labels)"] = (QUEUE_DEFAULT, QUEUE_DEFAULT.parent)

    if MAPILLARY_MULTI_ROOT.exists():
        for slug_dir in sorted(p for p in MAPILLARY_MULTI_ROOT.iterdir() if p.is_dir()):
            metadata_path = slug_dir / "mapillary_metadata.csv"
            if not metadata_path.exists():
                continue
            queue_path = slug_dir / "mapillary_label_queue.csv"
            _ensure_queue(queue_path, metadata_path=metadata_path)
            datasets[f"Mapillary – {slug_dir.name}"] = (queue_path, slug_dir)

    if not datasets:
        raise FileNotFoundError("No Mapillary label queues found. Run src/analysis/mapillary_label_queue.py first.")
    return datasets


def _save_queue(queue_path: Path, df: pd.DataFrame) -> None:
    tmp_path = queue_path.with_suffix(".tmp.csv")
    df.to_csv(tmp_path, index=False)
    tmp_path.replace(queue_path)


def _resolve_image_path(base_dir: Path, relative_path: str, image_id: str | None = None) -> Path | None:
    candidate = Path(relative_path)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    if candidate.exists():
        return candidate
    if image_id:
        fallback = base_dir / "images" / f"{image_id}.jpg"
        if fallback.exists():
            return fallback
    return None


def _format_metadata(row: pd.Series) -> str:
    pieces = []
    for key in ("lat", "lon", "capture_time", "sequence_id", "camera_type", "thumb_url"):
        if key in row and pd.notna(row[key]) and row[key] != "":
            pieces.append(f"{key}: {row[key]}")
    return "\n".join(pieces)


def render_mapillary_labeler(include_title: bool = True) -> None:
    if include_title:
        st.title("Mapillary Pole Labeler")

    datasets = _list_datasets()
    dataset_name = st.sidebar.selectbox("Dataset", options=list(datasets.keys()))
    queue_path, base_dir = datasets[dataset_name]
    st.sidebar.write("Queue file:", f"`{queue_path}`")

    # Allow reviewers to filter for only unlabeled rows or to revisit all examples.
    view_mode = st.sidebar.radio("Rows to show", options=["Unlabeled only", "All rows"], index=0)

    df = _load_queue(queue_path)
    if "image_id" not in df.columns:
        df["image_id"] = df.index.astype(str)

    is_unlabeled = df["pole_present"].astype(str).str.strip() == ""
    pending_df = df[is_unlabeled] if view_mode == "Unlabeled only" else df

    st.sidebar.metric("Total images", len(df))
    st.sidebar.metric("Remaining unlabeled", int(is_unlabeled.sum()))

    if len(pending_df) == 0:
        st.success("All images in this dataset have labels. 🎉")
        return

    # Track cursor position per dataset.
    cursor_key = f"cursor::{dataset_name}"
    if cursor_key not in st.session_state:
        st.session_state[cursor_key] = 0

    cursor = st.session_state[cursor_key]
    if cursor >= len(pending_df):
        cursor = 0
        st.session_state[cursor_key] = 0

    record = pending_df.iloc[cursor]
    image_id = record.get("image_id")
    record_index = record.name  # actual DataFrame index

    img_path = _resolve_image_path(base_dir, record.get("relative_path", ""), str(image_id))
    if img_path is None:
        st.error(f"Image file not found for record {image_id}. Check queue paths.")
        st.stop()

    col_image, col_controls = st.columns([2.5, 1])

    with col_image:
        st.image(Image.open(img_path), use_column_width=True, caption=f"Image ID: {image_id}")

    with col_controls:
        st.subheader("Label")
        st.write(_format_metadata(record))

        default_conf = 0.9 if record.get("pole_present", "") == "pole" else 0.1
        confidence = st.slider("Confidence", min_value=0.0, max_value=1.0, value=float(record.get("confidence", default_conf) or default_conf))
        notes = st.text_area("Notes", value=str(record.get("notes", "")), height=100)

        def _commit(label_value: str) -> None:
            df.loc[record_index, "pole_present"] = label_value
            df.loc[record_index, "confidence"] = confidence
            df.loc[record_index, "notes"] = notes
            _save_queue(queue_path, df)
            st.session_state[cursor_key] = cursor + 1
            st.experimental_rerun()

        st.button("Pole", type="primary", use_container_width=True, on_click=_commit, args=("pole",))
        st.button("Not a pole", use_container_width=True, on_click=_commit, args=("negative",))

        def _skip() -> None:
            st.session_state[cursor_key] = cursor + 1
            st.experimental_rerun()

        st.button("Unsure / Skip", use_container_width=True, on_click=_skip)

        if st.button("Back", use_container_width=True):
            st.session_state[cursor_key] = max(cursor - 1, 0)
            st.experimental_rerun()

    if st.checkbox("Show progress table", value=False):
        st.dataframe(df[["image_id", "pole_present", "confidence", "notes"]])

    st.caption("Tip: use the sidebar to switch datasets or jump between labeled/unlabeled views.")


def main() -> None:
    st.set_page_config(page_title="Mapillary Pole Labeler", layout="wide")
    render_mapillary_labeler()


if __name__ == "__main__":
    main()
