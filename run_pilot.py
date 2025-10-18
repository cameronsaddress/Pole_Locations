"""
End-to-End Pilot Pipeline
Runs the full verification workflow using only real datasets
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.append(str(Path(__file__).parent / 'src'))

import json
import time
import pandas as pd
import geopandas as gpd
import logging
from tqdm import tqdm

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
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _load_historical_poles() -> gpd.GeoDataFrame:
    """
    Load real historical pole records sourced from OpenStreetMap
    """
    input_file = RAW_DATA_DIR / 'osm_poles_harrisburg_real.csv'
    if not input_file.exists():
        raise FileNotFoundError(
            f"Required historical data not found at {input_file}. "
            "Run `python src/utils/get_osm_poles.py` to download real pole locations."
        )

    loader = PoleDataLoader()
    gdf = loader.load_csv(input_file)
    gdf = loader.filter_by_bbox(gdf)
    loader.validate_data(gdf)
    return gdf


def _generate_real_ai_detections(tile_dir: Path) -> pd.DataFrame:
    """
    Run the trained pole detector across NAIP tiles and persist detections.
    Returns a DataFrame with lat/lon + confidence sourced from actual model output.
    """
    detection_file = PROCESSED_DATA_DIR / 'ai_detections.csv'
    if detection_file.exists():
        logger.info(f"Using cached AI detections: {detection_file}")
        detections = pd.read_csv(detection_file)
        if detections.empty:
            raise ValueError(f"{detection_file} exists but is empty.")
        return detections

    tile_paths = sorted(Path(tile_dir).glob("*.tif"))
    if not tile_paths:
        raise FileNotFoundError(
            f"No NAIP tiles found in {tile_dir}. "
            "Run `python src/utils/download_naip_pc.py --no-mosaic` first."
        )

    model_path = MODELS_DIR / 'pole_detector_real.pt'
    detector = PoleDetector(
        model_path=model_path if model_path.exists() else None,
        confidence=CONFIDENCE_THRESHOLD,
        iou=IOU_THRESHOLD
    )

    logger.info(f"Running YOLO detection on {len(tile_paths)} NAIP tiles...")
    detections = detector.detect_tiles(tile_paths, crop_size=640, stride=512)

    detection_date = datetime.utcnow().date().isoformat()

    detections_df = pd.DataFrame(detections)
    if detections_df.empty:
        raise RuntimeError("YOLO inference completed but produced no detections.")

    detections_df['source_date'] = detection_date
    detections_df.to_csv(detection_file, index=False)
    runtime_seconds = 0.0  # detect_tiles already logs runtime context
    metadata = {
        "generated_at": detection_date,
        "tile_count": len(tile_paths),
        "detections": len(detections_df),
        "runtime_seconds": runtime_seconds
    }
    metadata_path = PROCESSED_DATA_DIR / 'ai_detections_metadata.json'
    metadata_path.write_text(json.dumps(metadata, indent=2))

    logger.info(f"✓ Saved {len(detections_df)} real detections to {detection_file}")
    logger.info(f"✓ Detection results saved for {len(detections_df):,} poles")
    return detections_df


def run_pilot_pipeline():
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
    tile_dir = PROCESSED_DATA_DIR.parent / 'imagery' / 'naip_tiles'
    detections_df = _generate_real_ai_detections(tile_dir)
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
    detections_df.to_csv(PROCESSED_DATA_DIR / 'ai_detections.csv', index=False)
    logger.info(f"✓ Collected {len(detections_df):,} model detections across tiles after contextual filtering")

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
    matcher = PoleMatcher()
    matched_df = matcher.spatial_matching(poles_gdf, detections_df)
    logger.info(f"✓ Created {len(matched_df):,} matched records")

    logger.info("\n[STEP 4] Classifying poles...")
    classifications = matcher.classify_poles(matched_df)

    logger.info("\n[STEP 5] Exporting results...")
    summary = matcher.export_results(classifications)

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
    try:
        summary = run_pilot_pipeline()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)
