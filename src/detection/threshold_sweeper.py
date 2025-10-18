"""
Sweep YOLO confidence/IoU thresholds against the labeled validation set.
Outputs a CSV summary with metrics for each threshold pair.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd

from config import (
    CHECKPOINTS_DIR,
    PROCESSED_DATA_DIR,
    CONFIDENCE_THRESHOLD,
    IOU_THRESHOLD,
    MODEL_INPUT_SIZE,
    OUTPUTS_DIR,
    THRESHOLD_EXPORT_PATH,
)
from detection.pole_detector import PoleDetector


def _parse_float_list(raw: str, fallback: List[float]) -> List[float]:
    if not raw:
        return fallback
    values = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        values.append(float(token))
    return values or fallback


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate detector performance across confidence/IoU thresholds."
    )
    parser.add_argument(
        "--weights",
        type=Path,
        default=None,
        help="Path to YOLO weights file (defaults to checkpoints/pole_detection/weights/best.pt if available).",
    )
    parser.add_argument(
        "--data-yaml",
        type=Path,
        default=PROCESSED_DATA_DIR / "pole_training_dataset" / "dataset.yaml",
        help="Dataset YAML file with train/val splits.",
    )
    parser.add_argument(
        "--conf-values",
        type=str,
        default="0.30,0.35,0.40,0.45,0.50",
        help="Comma-separated confidence thresholds to evaluate.",
    )
    parser.add_argument(
        "--iou-values",
        type=str,
        default="0.50,0.55,0.60",
        help="Comma-separated IoU thresholds to evaluate.",
    )
    parser.add_argument(
        "--split",
        type=str,
        default="val",
        help="Dataset split to evaluate (default: val).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Batch size for evaluation.",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=MODEL_INPUT_SIZE,
        help="Image size to evaluate at.",
    )
    parser.add_argument(
        "--write-best",
        action="store_true",
        help="Persist the top-performing thresholds to models/exports/detection_thresholds.json.",
    )

    args = parser.parse_args()

    weights = args.weights
    if weights is None:
        candidate = CHECKPOINTS_DIR / "pole_detection" / "weights" / "best.pt"
        if candidate.exists():
            weights = candidate

    detector = PoleDetector(
        model_path=weights,
        confidence=CONFIDENCE_THRESHOLD,
        iou=IOU_THRESHOLD,
    )

    conf_values = _parse_float_list(args.conf_values, [CONFIDENCE_THRESHOLD])
    iou_values = _parse_float_list(args.iou_values, [IOU_THRESHOLD])

    results_df = detector.sweep_thresholds(
        data_yaml=args.data_yaml,
        confidence_values=conf_values,
        iou_values=iou_values,
        split=args.split,
        batch_size=args.batch_size,
        imgsz=args.imgsz,
    )

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    analysis_dir = OUTPUTS_DIR / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    output_path = analysis_dir / f"threshold_sweep_{timestamp}.csv"
    if results_df.empty:
        print("No evaluation results were generated. Check dataset paths and logs.")
    else:
        results_df.to_csv(output_path, index=False)
        print("Saved threshold sweep results to:", output_path)

        sortable_cols = [col for col in [
            "metrics/mAP50-95(B)",
            "metrics/mAP50(B)",
            "metrics/precision(B)",
            "metrics/recall(B)"
        ] if col in results_df.columns]

        best_row: Optional[pd.Series] = None
        if sortable_cols:
            best_row_df = results_df.sort_values(sortable_cols, ascending=False).head(1)
            if not best_row_df.empty:
                best_row = best_row_df.iloc[0]
                print("\nTop-performing threshold combination:")
                print(best_row_df.to_string(index=False))
        elif "fitness" in results_df.columns:
            best_idx = results_df["fitness"].astype(float).idxmax()
            best_row = results_df.loc[best_idx]
            print("\nTop-performing threshold combination (via fitness):")
            print(results_df.loc[[best_idx]].to_string(index=False))
        else:
            print("Evaluation metrics columns not found in results; raw output saved for manual review.")

        if args.write_best and best_row is not None:
            payload = {
                "confidence_threshold": float(best_row["confidence_threshold"]),
                "iou_threshold": float(best_row["iou_threshold"]),
                "metrics": {
                    key: float(best_row[key])
                    for key in [
                        "metrics/precision(B)",
                        "metrics/recall(B)",
                        "metrics/mAP50(B)",
                        "metrics/mAP50-95(B)",
                        "fitness",
                    ]
                    if key in best_row.index
                },
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "source_csv": str(output_path),
            }
            THRESHOLD_EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with THRESHOLD_EXPORT_PATH.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            print(f"Persisted threshold overrides to {THRESHOLD_EXPORT_PATH}")


if __name__ == "__main__":
    main()
