"""
Match AI detections with historical pole records and classify verification status
"""
import pandas as pd
import geopandas as gpd
import numpy as np
from scipy.spatial import KDTree
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging
from pathlib import Path
import sys
from pyproj import Transformer, CRS

sys.path.append(str(Path(__file__).parent.parent))
from config import (
    VERIFIED_DISTANCE_THRESHOLD, VERIFIED_CONFIDENCE_THRESHOLD,
    IN_QUESTION_CONFIDENCE_THRESHOLD, MATCH_THRESHOLD_METERS,
    WEIGHT_IMAGERY, WEIGHT_RECENCY, WEIGHT_DISTANCE,
    RECENCY_WEIGHTS, PROCESSED_DATA_DIR, EXPORTS_OUTPUT_DIR
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PoleMatcher:
    """
    Match AI-detected poles with historical records and classify verification status
    """

    def __init__(self):
        self.verified_threshold_dist = VERIFIED_DISTANCE_THRESHOLD
        self.verified_threshold_conf = VERIFIED_CONFIDENCE_THRESHOLD
        self.question_threshold_conf = IN_QUESTION_CONFIDENCE_THRESHOLD
        self.match_threshold = MATCH_THRESHOLD_METERS

    def calculate_recency_weight(self, inspection_date: str) -> float:
        """
        Calculate weight based on how recent the inspection was

        Args:
            inspection_date: Date string (YYYY-MM-DD)

        Returns:
            Weight between 0-1
        """
        try:
            date = datetime.strptime(inspection_date, '%Y-%m-%d')
            days_ago = (datetime.now() - date).days
            years_ago = days_ago / 365.25

            if years_ago < 1:
                return RECENCY_WEIGHTS['under_1yr']
            elif years_ago < 3:
                return RECENCY_WEIGHTS['1_to_3yr']
            elif years_ago < 5:
                return RECENCY_WEIGHTS['3_to_5yr']
            else:
                return RECENCY_WEIGHTS['over_5yr']

        except Exception as e:
            logger.warning(f"Error parsing date {inspection_date}: {e}")
            return RECENCY_WEIGHTS['over_5yr']  # Default to oldest

    def normalize_distance(self, distance_meters: float) -> float:
        """
        Normalize distance to 0-1 scale (0 = far, 1 = close)

        Args:
            distance_meters: Distance in meters

        Returns:
            Normalized score (1 = perfect match, 0 = far away)
        """
        if distance_meters >= self.match_threshold:
            return 0.0

        # Linear normalization: 0m = 1.0, match_threshold = 0.0
        return 1.0 - (distance_meters / self.match_threshold)

    def calculate_confidence_score(self, imagery_conf: float, recency_weight: float,
                                   distance_meters: float) -> float:
        """
        Calculate overall confidence score combining multiple factors

        Args:
            imagery_conf: AI detection confidence (0-1)
            recency_weight: Report recency weight (0-1)
            distance_meters: Spatial distance between detection and record

        Returns:
            Combined confidence score (0-1)
        """
        distance_score = self.normalize_distance(distance_meters)

        combined_score = (
            WEIGHT_IMAGERY * imagery_conf +
            WEIGHT_RECENCY * recency_weight +
            WEIGHT_DISTANCE * distance_score
        )

        return combined_score

    def spatial_matching(self, historical_gdf: gpd.GeoDataFrame,
                        detections_df: pd.DataFrame) -> pd.DataFrame:
        """
        Match detections to historical records using spatial proximity

        Args:
            historical_gdf: GeoDataFrame with historical pole records
            detections_df: DataFrame with AI detections (must have 'lat', 'lon' columns)

        Returns:
            DataFrame with matched detections and historical records
        """
        logger.info(f"Matching {len(detections_df)} detections to {len(historical_gdf)} historical records")

        if historical_gdf.empty or detections_df.empty:
            logger.info("No matches computed because one of the inputs is empty.")
            return pd.DataFrame()

        hist_gdf = historical_gdf.reset_index(drop=True).copy()
        if hist_gdf.crs is None:
            hist_gdf.set_crs("EPSG:4326", inplace=True)
        elif hist_gdf.crs.to_string() != "EPSG:4326":
            hist_gdf = hist_gdf.to_crs("EPSG:4326")

        detections_clean = detections_df.copy()
        detections_clean = detections_clean.dropna(subset=['lat', 'lon']).reset_index(drop=True)

        if detections_clean.empty:
            logger.warning("All detections missing coordinates after cleaning; returning empty match set.")
            return pd.DataFrame()

        try:
            metric_crs = hist_gdf.estimate_utm_crs()
        except Exception:
            metric_crs = None

        if metric_crs is None:
            metric_crs = CRS.from_epsg(3857)

        transformer = Transformer.from_crs("EPSG:4326", metric_crs, always_xy=True)

        hist_x, hist_y = transformer.transform(
            hist_gdf.geometry.x.to_numpy(),
            hist_gdf.geometry.y.to_numpy()
        )
        det_x, det_y = transformer.transform(
            detections_clean['lon'].to_numpy(),
            detections_clean['lat'].to_numpy()
        )

        historical_coords = np.column_stack([hist_x, hist_y])
        detection_coords = np.column_stack([det_x, det_y])

        tree = KDTree(historical_coords)

        # Query nearest neighbor for each detection
        distances, indices = tree.query(
            detection_coords,
            k=1,
            distance_upper_bound=self.match_threshold
        )

        # Build matched records
        matches = []

        for i, (dist, idx) in enumerate(zip(distances, indices)):
            detection = detections_clean.iloc[i]

            if dist != np.inf and idx < len(hist_gdf):  # Valid match found
                historical_record = hist_gdf.iloc[int(idx)]
                match_distance_m = float(dist)

                # Calculate recency weight
                recency_weight = self.calculate_recency_weight(
                    historical_record.get('inspection_date', '2000-01-01')
                )

                # Calculate combined confidence
                combined_conf = self.calculate_confidence_score(
                    imagery_conf=detection.get('confidence', 0.5),
                    recency_weight=recency_weight,
                    distance_meters=match_distance_m
                )

                match = {
                    # Detection info
                    'detection_lat': detection['lat'],
                    'detection_lon': detection['lon'],
                    'detection_confidence': detection.get('confidence', 0.5),
                    'detection_ndvi': detection.get('ndvi'),
                    'road_distance_m': detection.get('road_distance_m'),

                    # Historical info
                    'pole_id': historical_record.get('pole_id', 'UNKNOWN'),
                    'historical_lat': historical_record.geometry.y,
                    'historical_lon': historical_record.geometry.x,
                    'historical_status': historical_record.get('status', 'unknown'),
                    'inspection_date': historical_record.get('inspection_date', ''),

                    # Match quality
                    'match_distance_m': match_distance_m,
                    'recency_weight': recency_weight,
                    'combined_confidence': combined_conf,

                    # Additional fields
                    'state': historical_record.get('state', ''),
                    'pole_type': historical_record.get('pole_type', ''),
                    'notes': historical_record.get('notes', '')
                }

                matches.append(match)

            else:  # No match found - potential new pole
                match = {
                    'detection_lat': detection['lat'],
                    'detection_lon': detection['lon'],
                    'detection_confidence': detection.get('confidence', 0.5),
                    'detection_ndvi': detection.get('ndvi'),
                    'road_distance_m': detection.get('road_distance_m'),
                    'pole_id': None,
                    'historical_lat': None,
                    'historical_lon': None,
                    'historical_status': None,
                    'inspection_date': None,
                    'match_distance_m': np.inf,
                    'recency_weight': 0.0,
                    'combined_confidence': detection.get('confidence', 0.5) * WEIGHT_IMAGERY,
                    'state': None,
                    'pole_type': None,
                    'notes': 'Potential new pole - no historical record found'
                }

                matches.append(match)

        matched_df = pd.DataFrame(matches)
        logger.info(f"Created {len(matched_df)} matches")

        return matched_df

    def classify_poles(self, matched_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """
        Classify poles into: Verified Good, In Question, New/Missing

        Args:
            matched_df: DataFrame with matched detections and historical records

        Returns:
            Dictionary with three DataFrames: 'verified_good', 'in_question', 'new_missing'
        """
        logger.info(f"Classifying {len(matched_df)} matched poles")

        # Verified Good: Close match, high confidence, recent verified status
        verified_good = matched_df[
            (matched_df['match_distance_m'] < self.verified_threshold_dist) &
            (matched_df['combined_confidence'] > self.verified_threshold_conf) &
            (matched_df['historical_status'] == 'verified')
        ].copy()
        verified_good['classification'] = 'verified_good'

        # New/Missing: No historical match OR historical pole with no detection
        new_missing = matched_df[
            (matched_df['pole_id'].isna()) |
            (matched_df['match_distance_m'] == np.inf)
        ].copy()
        new_missing['classification'] = 'new_missing'

        # In Question: Everything else
        in_question = matched_df[
            ~matched_df.index.isin(verified_good.index) &
            ~matched_df.index.isin(new_missing.index)
        ].copy()
        in_question['classification'] = 'in_question'

        # Add priority scores for review queue (higher = more urgent)
        in_question['review_priority'] = (
            (1 - in_question['combined_confidence']) * 0.5 +  # Lower confidence = higher priority
            (in_question['match_distance_m'] / self.match_threshold) * 0.3 +  # Larger distance = higher priority
            (1 - in_question['recency_weight']) * 0.2  # Older inspection = higher priority
        )
        in_question = in_question.sort_values('review_priority', ascending=False)

        logger.info(f"Classification results:")
        logger.info(f"  Verified Good: {len(verified_good)} ({len(verified_good)/len(matched_df)*100:.1f}%)")
        logger.info(f"  In Question: {len(in_question)} ({len(in_question)/len(matched_df)*100:.1f}%)")
        logger.info(f"  New/Missing: {len(new_missing)} ({len(new_missing)/len(matched_df)*100:.1f}%)")

        return {
            'verified_good': verified_good,
            'in_question': in_question,
            'new_missing': new_missing
        }

    def export_results(
        self,
        classifications: Dict[str, pd.DataFrame],
        extra_metrics: Optional[Dict[str, float]] = None
    ):
        """
        Export classification results to CSV files

        Args:
            classifications: Dictionary with classified DataFrames
        """
        EXPORTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        for name, df in classifications.items():
            filepath = EXPORTS_OUTPUT_DIR / f'{name}.csv'
            df.to_csv(filepath, index=False)
            logger.info(f"Exported {len(df)} records to {filepath}")

        # Also create a summary report
        summary = {
            'total_poles': sum(len(df) for df in classifications.values()),
            'verified_good': len(classifications['verified_good']),
            'in_question': len(classifications['in_question']),
            'new_missing': len(classifications['new_missing']),
            'automation_rate': len(classifications['verified_good']) / sum(len(df) for df in classifications.values()) * 100,
            'review_queue_rate': len(classifications['in_question']) / sum(len(df) for df in classifications.values()) * 100
        }

        if extra_metrics:
            summary.update(extra_metrics)

        summary_path = EXPORTS_OUTPUT_DIR / 'summary_metrics.json'
        import json
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)

        logger.info(f"Summary metrics saved to {summary_path}")

        return summary


def main():
    """
    Demo: Match and classify poles
    """
    logger.info("=" * 60)
    logger.info("POLE MATCHING AND CLASSIFICATION DEMO")
    logger.info("=" * 60)

    # This is a demo - in production, detections would come from the AI pipeline
    logger.info("\nThis module requires:")
    logger.info("  1. Historical pole records (GeoDataFrame)")
    logger.info("  2. AI detections with lat/lon and confidence")
    logger.info("\nUsage:")
    logger.info("  matcher = PoleMatcher()")
    logger.info("  matched = matcher.spatial_matching(historical_gdf, detections_df)")
    logger.info("  classifications = matcher.classify_poles(matched)")
    logger.info("  summary = matcher.export_results(classifications)")

    logger.info("\n" + "=" * 60)
    logger.info("MATCHER READY")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
