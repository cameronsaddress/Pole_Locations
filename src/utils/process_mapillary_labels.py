"""
Convert labeled Mapillary thumbnails into YOLO training crops.

Prerequisites:
1. Run `harvest_mapillary.py` to populate `data/raw/mapillary/images` and metadata CSV.
2. Create a CSV named `mapillary_labels.csv` with columns:
       image_id,label
       12345,pole
       67890,negative
   Valid labels: `pole`, `negative` (anything else is ignored).

This script copies the labeled images into the existing `pole_training_dataset`
structure so they can be included in retraining.
"""
import argparse
import shutil
from pathlib import Path

import pandas as pd

from config import PROCESSED_DATA_DIR, RAW_DATA_DIR

VALID_LABELS = {"pole", "negative"}


def ingest_mapillary_labels(
    metadata_csv: Path,
    labels_csv: Path,
    output_dir: Path,
) -> None:
    if not metadata_csv.exists():
        raise FileNotFoundError(f"Mapillary metadata not found: {metadata_csv}")
    if not labels_csv.exists():
        raise FileNotFoundError(f"Label CSV not found: {labels_csv}")

    metadata = pd.read_csv(metadata_csv)
    labels = pd.read_csv(labels_csv)

    df = labels.merge(metadata, left_on="image_id", right_on="image_id", how="inner")
    df = df[df["label"].isin(VALID_LABELS)].dropna(subset=["thumb_url"])

    if df.empty:
        print("No labeled Mapillary records to ingest.")
        return

    images_root = output_dir / "images"
    labels_root = output_dir / "labels"
    images_root.mkdir(parents=True, exist_ok=True)
    labels_root.mkdir(parents=True, exist_ok=True)

    raw_images_dir = metadata_csv.parent / "images"

    copied = 0
    for _, row in df.iterrows():
        image_id = row["image_id"]
        label = row["label"]
        src_path = raw_images_dir / f"{image_id}.jpg"
        if not src_path.exists():
            continue

        target_stem = f"mapillary_{image_id}"
        dst_path = images_root / f"{target_stem}.jpg"
        shutil.copy(src_path, dst_path)

        # YOLO format: class_id center_x center_y width height (normalized)
        class_id = 0 if label == "pole" else 1
        label_path = labels_root / f"{target_stem}.txt"
        if class_id == 0:
            label_path.write_text("0 0.5 0.5 0.6 0.8\n")
        else:
            label_path.write_text("")  # negative samples -> empty label file
        copied += 1

    print(f"Ingested {copied} Mapillary thumbnails into {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Copy labeled Mapillary imagery into the training dataset.")
    parser.add_argument(
        "--metadata",
        type=Path,
        default=RAW_DATA_DIR / "mapillary" / "mapillary_metadata.csv",
        help="Metadata CSV produced by harvest_mapillary.py",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=RAW_DATA_DIR / "mapillary" / "mapillary_labels.csv",
        help="CSV with human labels (image_id,label).",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=PROCESSED_DATA_DIR / "pole_training_dataset",
        help="Existing pole training dataset directory.",
    )
    args = parser.parse_args()

    ingest_mapillary_labels(args.metadata, args.labels, args.dataset)


if __name__ == "__main__":
    main()
