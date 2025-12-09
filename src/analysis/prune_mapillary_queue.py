#!/usr/bin/env python
"""Down-sample Mapillary labeling queues to remove near-duplicate frames."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def prune_queue(queue_path: Path, stride: int, min_distance: float) -> pd.DataFrame:
    df = pd.read_csv(queue_path)
    if "sequence_id" not in df.columns:
        raise ValueError("Queue is missing 'sequence_id' column; cannot prune duplicates.")

    df = df.copy()
    if "capture_time" in df.columns:
        df_sorted = df.sort_values(["sequence_id", "capture_time", "image_id"], na_position="last")
    else:
        df_sorted = df.sort_values(["sequence_id", "image_id"])

    kept_indices = []

    for seq, group in df_sorted.groupby("sequence_id"):
        group_indices = group.index.tolist()
        group = group.reset_index()

        last_lat = last_lon = None
        keep_counter = 0

        for row in group.itertuples():
            index = group_indices[row.Index]
            lat = getattr(row, "lat", None)
            lon = getattr(row, "lon", None)

            if stride > 1 and (keep_counter % stride) != 0:
                keep_counter += 1
                continue

            if min_distance > 0 and last_lat is not None and lat is not None and lon is not None:
                dist = haversine_m(last_lat, last_lon, lat, lon)
                if dist < min_distance:
                    keep_counter += 1
                    continue

            kept_indices.append(index)
            keep_counter += 1
            if lat is not None and lon is not None:
                last_lat, last_lon = lat, lon

    pruned_df = df.loc[sorted(set(kept_indices))].reset_index(drop=True)
    return pruned_df


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove near-duplicate Mapillary frames from a labeling queue.")
    parser.add_argument("queue", type=Path, help="Path to mapillary_label_queue.csv or its containing directory.")
    parser.add_argument("--stride", type=int, default=3, help="Keep every Nth frame within each sequence (default 3).")
    parser.add_argument(
        "--min-distance", dest="min_distance", type=float, default=5.0,
        help="Minimum distance in meters between kept frames (default 5m).",
    )
    parser.add_argument("--in-place", action="store_true", help="Overwrite the queue rather than writing *_dedup.csv")
    args = parser.parse_args()

    queue_path = args.queue
    if queue_path.is_dir():
        queue_path = queue_path / "mapillary_label_queue.csv"
    if not queue_path.exists():
        raise FileNotFoundError(queue_path)

    original_df = pd.read_csv(queue_path)
    pruned_df = prune_queue(queue_path, args.stride, args.min_distance)

    out_path = queue_path if args.in_place else queue_path.with_name(queue_path.stem + "_dedup.csv")
    pruned_df.to_csv(out_path, index=False)

    print(f"Original frames: {len(original_df)}")
    print(f"Pruned frames:   {len(pruned_df)}")
    print(f"Saved to:        {out_path}")


if __name__ == "__main__":
    main()
