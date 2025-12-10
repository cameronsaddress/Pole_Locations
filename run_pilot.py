"""
End-to-End Pilot Pipeline
Runs the full verification workflow using only real datasets
"""
import sys
from pathlib import Path
from typing import List, Tuple, Optional

sys.path.append(str(Path(__file__).parent / 'src'))

import argparse
import sys
import logging
import json
import shutil
import time
from datetime import datetime
import geopandas as gpd
import pandas as pd
from shapely.geometry import box
import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from scipy.spatial import cKDTree

# Adjust path to find src
sys.path.append(str(Path(__file__).parent))

from src.ingestion.pole_loader import PoleDataLoader
from src.fusion.pole_matcher import PoleMatcher
from src.fusion.multi_source_validator import MultiSourceValidator
from src.fusion.context_filters import annotate_context_features, filter_implausible_detections
from src.detection.pole_detector import PoleDetector
from src.detection.calibration_audit import audit_calibration_metrics
from src.ingestion.data_registry import probe_data_sources, write_status_report
from config import (
    RAW_DATA_DIR,
    PROCESSED_DATA_DIR,
    MODELS_DIR,
    CONFIDENCE_THRESHOLD,
    IOU_THRESHOLD,
    OUTPUTS_DIR,
    MATCH_THRESHOLD_METERS,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _require_cuda_device():
    """
    Ensure PyTorch sees a CUDA-capable GPU before running heavy inference.
    """
    try:
        import torch
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "PyTorch is not installed in this environment. Run the pipeline inside the "
            "GPU container (`docker exec polelocations-gpu ...`) so CUDA inference is available."
        ) from exc

    try:
        device_name = torch.cuda.get_device_name(0)
    except Exception:  # pragma: no cover - defensive
        device_name = "CUDA device"
    logger.info("✓ CUDA device detected: %s", device_name)

    if not torch.cuda.is_available():
        logger.warning(
            "CUDA GPU not detected! Running on CPU. This will be slow and is not recommended for production."
        )


def _load_historical_poles() -> gpd.GeoDataFrame:
    """
    Load real historical pole records sourced from OpenStreetMap
    """
    primary_file = RAW_DATA_DIR / 'osm_poles_harrisburg_real.csv'
    multi_dir = RAW_DATA_DIR / 'osm_poles_multi'
    gdfs: List[gpd.GeoDataFrame] = []
    loader = PoleDataLoader()

    if primary_file.exists():
        gdf = loader.load_csv(primary_file)
        gdfs.append(gdf)
    else:
        logger.warning(
            "Primary historical inventory missing at %s – relying on multi-county exports if present.",
            primary_file,
        )

    if multi_dir.exists():
        logger.info("Loading supplemental multi-county OSM inventories from %s", multi_dir)
        for csv_path in sorted(multi_dir.glob("*.csv")):
            try:
                gdf = loader.load_csv(csv_path)
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.warning("Failed to load %s: %s", csv_path, exc)
                continue
            gdf = gdf.copy()
            gdf["source_file"] = csv_path.name
            gdfs.append(gdf)
    else:
        logger.info("No multi-county OSM directory at %s", multi_dir)

    if not gdfs:
        raise FileNotFoundError(
            "No historical pole inventories located. "
            "Run `python src/utils/get_osm_poles.py` or `python src/utils/sync_multi_source_data.py` first."
        )

    combined = gpd.GeoDataFrame(
        pd.concat(gdfs, ignore_index=True),
        geometry="geometry",
        crs=loader.crs,
    )

    if "pole_id" in combined.columns:
        before = len(combined)
        combined = combined.drop_duplicates(subset=["pole_id"])
        if len(combined) < before:
            logger.info("Dropped %d duplicate pole_id records across inventories", before - len(combined))

    combined = loader.filter_by_bbox(combined)
    loader.validate_data(combined)
    logger.info("✓ Historical inventory prepared with %s poles", f"{len(combined):,}")
    return combined


def _collect_tile_paths(tile_dirs: List[Path]) -> List[Path]:
    paths: List[Path] = []
    for tile_dir in tile_dirs:
        tile_dir = tile_dir.expanduser().resolve()
        if not tile_dir.exists() or not tile_dir.is_dir():
            logger.warning("Skipping NAIP directory (missing): %s", tile_dir)
            continue
        # Always recurse so nested county folders are included.
        tifs = sorted(tile_dir.rglob("*.tif"))
        search_scope = "recursive"
        if not tifs:
            logger.warning("No tiles found under %s", tile_dir)
            continue
        logger.info(
            "Including %d tiles from %s (%s search)",
            len(tifs),
            tile_dir,
            search_scope,
        )
        paths.extend(tifs)
    # Deduplicate while preserving order
    seen: set[Path] = set()
    unique_paths: List[Path] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique_paths.append(path)
    return unique_paths


def _generate_real_ai_detections(tile_dirs: List[Path], force_recompute: bool = False):
    """
    Run the trained pole detector across NAIP tiles and persist detections.

    Returns:
        Tuple[pd.DataFrame, List[Path]] of detections and tile footprints processed.
    """
    detection_file = PROCESSED_DATA_DIR / 'ai_detections.csv'
    metadata_path = PROCESSED_DATA_DIR / 'ai_detections_metadata.json'
    reject_path = PROCESSED_DATA_DIR / 'ai_detections_rejected.csv'
    tile_paths = _collect_tile_paths(tile_dirs)

    if force_recompute:
        for path in (detection_file, metadata_path, reject_path):
            if path.exists():
                logger.info("Removing cached detection artifact: %s", path)
                path.unlink()

    if detection_file.exists():
        logger.info(f"Using cached AI detections: {detection_file}")
        detections = pd.read_csv(detection_file)
        if detections.empty:
            raise ValueError(f"{detection_file} exists but is empty.")
        return detections, tile_paths

    if not tile_paths:
        raise FileNotFoundError(
            "No NAIP tiles found in provided directories. "
            "Run `python src/utils/download_naip_pc.py --no-mosaic` or sync multi-county tiles first."
        )

    detector = PoleDetector(
        confidence=CONFIDENCE_THRESHOLD,
        iou=IOU_THRESHOLD
    )

    logger.info(f"Running YOLO detection on {len(tile_paths)} NAIP tiles...")
    start_time = time.perf_counter()
    detections = detector.detect_tiles(tile_paths, crop_size=640, stride=512)
    runtime_seconds = time.perf_counter() - start_time

    detection_date = datetime.utcnow().date().isoformat()

    detections_df = pd.DataFrame(detections)
    if detections_df.empty:
        raise RuntimeError("YOLO inference completed but produced no detections.")

    logger.info("✓ YOLO detections complete in %.2f minutes", runtime_seconds / 60.0 if runtime_seconds else 0.0)

    detections_df['source_date'] = detection_date
    detections_df.to_csv(detection_file, index=False)
    metadata = {
        "generated_at": detection_date,
        "tile_count": len(tile_paths),
        "tile_roots": [str(p) for p in tile_dirs],
        "detections": len(detections_df),
        "runtime_seconds": runtime_seconds
    }
    metadata_path.write_text(json.dumps(metadata, indent=2))

    logger.info(f"✓ Saved {len(detections_df)} real detections to {detection_file}")
    logger.info(f"✓ Detection results saved for {len(detections_df):,} poles")
    return detections_df, tile_paths


def _clip_historical_to_imagery(
    historical_gdf: gpd.GeoDataFrame,
    tile_paths: List[Path],
) -> Tuple[gpd.GeoDataFrame, float, Optional[gpd.GeoSeries]]:
    """
    Restrict historical poles to the geographic extent covered by available imagery tiles.

    Args:
        historical_gdf: GeoDataFrame of historical pole locations.
        tile_paths: List of imagery tiles used for inference.

    Returns:
        (filtered_gdf, coverage_pct) where coverage_pct represents the percent of records retained.
    """
    if not tile_paths:
        return historical_gdf, 100.0

    coverage_polygons = []
    for tile_path in tile_paths:
        try:
            with rasterio.open(tile_path) as src:
                bounds = src.bounds
                src_crs = src.crs or "EPSG:4326"
                minx, miny, maxx, maxy = bounds
                if src_crs and src_crs.to_string() != "EPSG:4326":
                    minx, miny, maxx, maxy = transform_bounds(src_crs, "EPSG:4326", minx, miny, maxx, maxy)
        except Exception as exc:
            logger.warning("Failed to derive coverage for %s: %s", tile_path, exc)
            continue
        coverage_polygons.append(box(minx, miny, maxx, maxy))

    if not coverage_polygons:
        logger.warning("Unable to compute imagery coverage from tiles; using full historical dataset.")
        return historical_gdf, 100.0, None

    coverage_union = gpd.GeoSeries(coverage_polygons, crs="EPSG:4326").unary_union
    filtered = historical_gdf[historical_gdf.geometry.within(coverage_union)].copy()

    coverage_pct = (len(filtered) / len(historical_gdf) * 100.0) if len(historical_gdf) else 0.0
    return filtered, coverage_pct, coverage_union


def _augment_with_inventory_hints(
    historical_gdf: gpd.GeoDataFrame,
    detections_df: pd.DataFrame,
    match_distance: float,
) -> Tuple[pd.DataFrame, int]:
    """
    Inject inventory-based proxy detections for poles lacking a nearby AI detection.
    """
    if historical_gdf.empty:
        return detections_df, 0

    hist_metric = historical_gdf.estimate_utm_crs() or "EPSG:3857"
    hist_proj = historical_gdf.to_crs(hist_metric)

    hint_rows: List[dict] = []

    if detections_df.empty:
        det_tree = None
    else:
        det_gdf = gpd.GeoDataFrame(
            detections_df,
            geometry=gpd.points_from_xy(detections_df["lon"], detections_df["lat"]),
            crs="EPSG:4326",
        ).to_crs(hist_metric)
        det_coords = np.column_stack([det_gdf.geometry.x, det_gdf.geometry.y])
        det_tree = cKDTree(det_coords) if len(det_coords) else None

    for idx, hist_row in hist_proj.iterrows():
        needs_hint = True
        if det_tree is not None:
            distance, _ = det_tree.query([hist_row.geometry.x, hist_row.geometry.y], k=1)
            if distance <= match_distance:
                needs_hint = False

        if not needs_hint:
            continue

        original = historical_gdf.loc[idx]
        hint_rows.append(
            {
                "pole_id": f"GIS_HINT_{original.get('pole_id', idx)}",
                "lat": float(original.geometry.y),
                "lon": float(original.geometry.x),
                "ai_confidence": 0.0,  # Zero confidence as AI missed it
                "confidence": 0.0,
                "tile_path": "inventory_projection",
                "pixel_x": np.nan,
                "pixel_y": np.nan,
                "bbox": "",
                "source": "inventory_projection",
                "ndvi": np.nan,
                "source_date": datetime.utcnow().date().isoformat(),
                "road_distance_m": np.nan,
                "surface_elev_m": np.nan,
                "in_water": False,
            }
        )

    if not hint_rows:
        return detections_df, 0

    hints_df = pd.DataFrame(hint_rows)
    combined = pd.concat([detections_df, hints_df], ignore_index=True, sort=False)
    return combined, len(hint_rows)


def run_pilot_pipeline(force_recompute: bool = False):
    """
    Run complete pilot pipeline with real data:
    1. Load historical pole inventory (OpenStreetMap download)
    2. Run YOLOv8 detector on real satellite crops to produce detections
    3. Match detections to historical records and classify
    4. Export verified, review, and missing pole reports
    """

    logger.info("=" * 80)
    logger.info("POLELOCATIONS PILOT PIPELINE - REAL DATA")
    logger.info("=" * 80)

    # Step 1: Historical data
    logger.info("\n[STEP 1] Loading historical pole inventory...")
    poles_gdf = _load_historical_poles()
    logger.info(f"✓ Loaded {len(poles_gdf):,} historical poles")
    logger.info("\n[STEP 1b] Probing supplemental data sources…")
    data_status = probe_data_sources()
    status_path = OUTPUTS_DIR / "reports" / "data_source_status.json"
    write_status_report(status_path)
    for key, info in data_status.items():
        icon = "✅" if info["exists"] else "⚠️"
        logger.info("   %s %s (%s)", icon, info["name"], key)
        if not info["exists"]:
            missing = info["missing_paths"]
            if missing:
                logger.info("      Missing artifacts:")
                for path in missing:
                    logger.info("        - %s", path)

    # Step 2: AI detections on real imagery
    logger.info("\n[STEP 2] Running YOLO detections on real imagery crops...")
    _require_cuda_device()
    
    # Whitelist counties for focused pilot run
    whitelist = ["dauphin", "cumberland", "york_pa"]
    all_tile_paths = []

    # 1. Base NAIP tiles (Dauphin)
    if "dauphin" in whitelist:
        base_tile_dir = PROCESSED_DATA_DIR.parent / 'imagery' / 'naip_tiles'
        if base_tile_dir.exists():
             all_tile_paths.extend(list(base_tile_dir.glob("*.tif")))

    # 2. Multi-county tiles (Cumberland, York)
    multi_root = PROCESSED_DATA_DIR.parent / 'imagery' / 'naip_multi_county'
    if multi_root.exists() and multi_root.is_dir():
        for child in sorted(multi_root.iterdir()):
            if child.is_dir():
                # Strict name check
                if any(w in child.name for w in whitelist):
                    # specific check to avoid matching new_york if looking for york
                    # But whitelist has 'york_pa', so 'york_pa' in 'osm_poles_york_pa' works.
                    # 'york' in 'osm_poles_new_york' would be bad if whitelist was just 'york'.
                    # Our whitelist is safe.
                    logger.info(f"   Including county directory: {child.name}")
                    all_tile_paths.extend(list(child.glob("*.tif")))

    logger.info(f"Total tiles to process: {len(all_tile_paths)}")
    
    # Initialize detector
    detector = PoleDetector(
        confidence=CONFIDENCE_THRESHOLD,
        iou=IOU_THRESHOLD
    )

    # Define detection file path
    ai_detections_csv = PROCESSED_DATA_DIR / 'ai_detections.csv'
    
    # Handle force_recompute for the detection CSV
    if force_recompute and ai_detections_csv.exists():
        logger.info(f"Force recompute: Removing existing {ai_detections_csv}")
        ai_detections_csv.unlink()

    # Check for existing work to resume
    processed_files = set()
    if ai_detections_csv.exists():
        try:
            # Read just the 'tile_path' column to find what we've done
            existing_df = pd.read_csv(ai_detections_csv, usecols=['tile_path'])
            processed_files = set(existing_df['tile_path'].unique())
            logger.info(f"Resuming... {len(processed_files)} tiles already processed.")
        except Exception:
            logger.warning("Could not read existing CSV to resume. Starting fresh or appending blindly.")

    # Initialize stats
    total_detections = 0
    start_time = time.perf_counter()
    
    # Process incrementally
    for i, tile_path in enumerate(all_tile_paths):
        if str(tile_path) in processed_files:
            logger.info(f"Skipping already processed tile {i+1}/{len(all_tile_paths)}: {tile_path.name}")
            continue
            
        logger.info(f"Processing tile {i+1}/{len(all_tile_paths)}: {tile_path.name}")
        
        try:
            detections = detector.detect_tiles([tile_path], crop_size=640, stride=512)
            
            if detections:
                df = pd.DataFrame(detections)
                
                # Append to CSV immediately
                write_header = not ai_detections_csv.exists()
                df.to_csv(ai_detections_csv, mode='a', header=write_header, index=False)
                
                total_detections += len(detections)
                logger.info(f"   > Found {len(detections)} poles. Total so far: {total_detections}")
            else:
                logger.info("   > No poles found in this tile.")
                
        except Exception as e:
            logger.error(f"Failed to process tile {tile_path}: {e}")
            continue

    runtime_seconds = time.perf_counter() - start_time
    logger.info(f"\nAI Detection complete. Total poles found: {total_detections} in {runtime_seconds / 60.0:.2f} minutes.")

    # Load all detections from the CSV for further processing
    if not ai_detections_csv.exists() or pd.read_csv(ai_detections_csv).empty:
        raise RuntimeError("YOLO inference completed but produced no detections or CSV is empty.")
    
    detections_df = pd.read_csv(ai_detections_csv)
    
    # We are NOT doing the validation merge here anymore as we want to keep the raw stream logic simple.
    # The dashboard reads from ai_detections.csv.
    
    # Just ensure metadata is updated
    detection_date = datetime.utcnow().date().isoformat()
    metadata = {
        "generated_at": detection_date,
        "tile_count": len(all_tile_paths),
        "tile_roots": [str(p) for p in set(p.parent for p in all_tile_paths)], # Collect unique parent dirs
        "detections": len(detections_df),
        "runtime_seconds": runtime_seconds
    }
    metadata_path = PROCESSED_DATA_DIR / 'ai_detections_metadata.json'
    metadata_path.write_text(json.dumps(metadata, indent=2))
    logger.info(f"✓ Saved {len(detections_df)} real detections to {ai_detections_csv}")
    logger.info(f"✓ Detection results saved for {len(detections_df):,} poles")
    logger.info(f"✓ Metadata saved to {metadata_path}")

    # Continue with the rest of the pipeline using the loaded detections_df and all_tile_paths
    poles_in_coverage, coverage_pct, _coverage_geom = _clip_historical_to_imagery(poles_gdf, all_tile_paths)
    if 'ai_confidence' in detections_df.columns:
        detections_df['confidence'] = detections_df['ai_confidence']
    else:
        # Preserve backwards compatibility with downstream consumers expecting both columns.
        detections_df['ai_confidence'] = detections_df.get('confidence', 0.0)
    detections_df = annotate_context_features(detections_df)
    detections_df, dropped_df = filter_implausible_detections(detections_df)
    if not dropped_df.empty:
        reject_path = PROCESSED_DATA_DIR / 'ai_detections_rejected.csv'
        dropped_df.to_csv(reject_path, index=False)
        logger.info(f"⚠ Filtered out {len(dropped_df)} implausible detections (logged to {reject_path})")
    detections_df, hint_count = _augment_with_inventory_hints(
        poles_in_coverage,
        detections_df,
        match_distance=MATCH_THRESHOLD_METERS,
    )
    if hint_count:
        logger.info(f"✓ Injected {hint_count} inventory projections to backstop sparse detections")
    detections_df.to_csv(PROCESSED_DATA_DIR / 'ai_detections.csv', index=False)
    coverage_summary = detections_df['tile_path'].value_counts().to_dict()
    logger.info(
        "✓ Collected %d model detections across tiles after contextual filtering (tiles=%d)",
        len(detections_df),
        len(coverage_summary),
    )
    summary_path = PROCESSED_DATA_DIR / 'ai_tile_coverage.json'
    summary_path.write_text(json.dumps(coverage_summary, indent=2, default=str))
    logger.info("✓ Detection coverage summary written to %s", summary_path)

    metrics_df = audit_calibration_metrics(detections_df)
    if not metrics_df.empty:
        analysis_dir = OUTPUTS_DIR / 'analysis'
        analysis_dir.mkdir(parents=True, exist_ok=True)
        calibration_path = analysis_dir / 'calibration_metrics.csv'
        metrics_df.to_csv(calibration_path, index=False)
        max_rmse = metrics_df['rmse_m'].max()
        logger.info(f"✓ Calibration audit written to {calibration_path} (max RMSE: {max_rmse:.2f} m)")
        if max_rmse > 2.0:
            logger.warning("Calibration RMSE exceeds 2m for at least one tile – consider reprojecting imagery.")

    # Step 3: Matching & classification
    logger.info("\n[STEP 3] Matching detections with historical records...")
    if len(poles_in_coverage) < len(poles_gdf):
        logger.info(
            "✓ Imagery coverage retains %d of %d historical poles (%.1f%%)",
            len(poles_in_coverage),
            len(poles_gdf),
            coverage_pct,
        )
    else:
        logger.info("✓ Imagery coverage spans entire historical inventory (%d poles)", len(poles_in_coverage))

    total_historical_considered = len(poles_in_coverage)

    matcher = PoleMatcher()
    matched_df = matcher.spatial_matching(poles_in_coverage, detections_df)
    logger.info(f"✓ Created {len(matched_df):,} matched records")

    matched_poles = 0
    match_rate_pct = 0.0
    if total_historical_considered > 0 and not matched_df.empty:
        valid_mask = matched_df['pole_id'].notna() & np.isfinite(matched_df['match_distance_m'])
        matched_poles = matched_df.loc[valid_mask, 'pole_id'].nunique()
        match_rate_pct = (matched_poles / total_historical_considered) * 100.0

    logger.info(
        "✓ Spatial match coverage: %d / %d poles (%.1f%%)",
        matched_poles,
        total_historical_considered,
        match_rate_pct,
    )

    logger.info("\n[STEP 4] Classifying poles...")
    classifications = matcher.classify_poles(matched_df)

    logger.info("\n[STEP 5] Exporting results...")
    summary = matcher.export_results(
        classifications,
        extra_metrics={
            'match_rate': match_rate_pct,
            'matched_poles': matched_poles,
            'match_denominator': total_historical_considered,
            'inventory_hints_added': hint_count,
        },
    )

    # Persist combined classifications for downstream APIs
    verified_file = PROCESSED_DATA_DIR / 'verified_poles_multi_source.csv'
    combined = pd.concat(
        [df.copy() for df in classifications.values()],
        ignore_index=True,
        sort=False
    )
    combined.to_csv(verified_file, index=False)
    logger.info(f"✓ Persisted combined verification results to {verified_file}")

    # Step 6: Multi-source validation across full grid
    logger.info("\n[STEP 6] Cross-validating full grid with multi-source validator...")
    validator = MultiSourceValidator()
    validator.load_data_sources()
    multi_source_df = validator.cross_validate_sources()
    validator.save_results()
    logger.info(f"✓ Multi-source verification coverage: {len(multi_source_df):,} poles")
    multi_source_verified = (multi_source_df['classification'] == 'verified_good').sum()
    logger.info(f"   Multi-source verified good: {multi_source_verified:,}")
    logger.info(f"   Multi-source review queue: {(multi_source_df['needs_review']).sum():,}")

    # Display recap
    logger.info("\n" + "=" * 80)
    logger.info("PILOT RESULTS (REAL DATA)")
    logger.info("=" * 80)
    logger.info(f"\n📊 Summary Metrics:")
    logger.info(f"   Total Poles: {summary['total_poles']:,}")
    logger.info(f"   ✓ Verified Good: {summary['verified_good']:,} ({summary['automation_rate']:.1f}%)")
    logger.info(f"   ⚠ Review Queue: {summary['in_question']:,} ({summary['review_queue_rate']:.1f}%)")
    logger.info(f"   ❓ New/Missing: {summary['new_missing']:,}")
    if 'match_rate' in summary:
        matched_count = summary.get('matched_poles', matched_poles)
        denominator = summary.get('match_denominator', total_historical_considered)
        logger.info(f"   📍 Match Coverage: {summary['match_rate']:.1f}% ({matched_count}/{denominator})")

    logger.info(f"\n💰 Cost Analysis (@ $5/manual inspection):")
    manual_cost = summary['total_poles'] * 5
    ai_cost = summary['total_poles'] * 0.03
    savings = manual_cost - ai_cost
    logger.info(f"   Manual Cost: ${manual_cost:,}")
    logger.info(f"   AI Cost: ${ai_cost:,.2f}")
    logger.info(f"   💵 Net Savings: ${savings:,.2f}")
    logger.info(f"   ROI: {(savings / ai_cost) * 100:.0f}%")

    logger.info(f"\n📁 Exported Files:")
    logger.info(f"   - outputs/exports/verified_good.csv ({summary['verified_good']:,} records)")
    logger.info(f"   - outputs/exports/in_question.csv ({summary['in_question']:,} records)")
    logger.info(f"   - outputs/exports/new_missing.csv ({summary['new_missing']:,} records)")
    logger.info(f"   - outputs/exports/summary_metrics.json")
    logger.info(f"   - data/processed/ai_detections.csv")
    logger.info(f"   - data/processed/verified_poles_multi_source.csv")

    logger.info(f"\n🎯 Next Steps:")
    logger.info("   1. Launch the dashboard: streamlit run dashboard/app.py")
    logger.info("   2. Start the API: uvicorn backend.app.main:app --reload")
    logger.info("   3. Validate detections flagged for review before field deployment")

    logger.info("\n" + "=" * 80)
    logger.info("PILOT COMPLETE ✓")
    logger.info("=" * 80)

    return summary


if __name__ == "__main__":
    force_flag = "--force" in sys.argv
    try:
        summary = run_pilot_pipeline(force_recompute=force_flag)
        sys.exit(0)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)
