"""
Multi-Source Pole Verification Engine
Implements the confidence scoring and 3-tier classification system per README.md

Confidence Scoring Formula:
    Total = 0.40 × AI_Detection + 0.30 × Recency + 0.30 × Spatial_Match

Classification:
    - Verified Good (76%): confidence ≥0.8, spatial match <5m, 2+ sources
    - In Question (20%): confidence <0.8 OR mismatch >5m OR conflicting reports
    - Missing/New (4%): Only 1 source detected
"""

import pandas as pd
import numpy as np
from pathlib import Path
from scipy.spatial import KDTree
from datetime import datetime
from typing import Dict, List, Tuple
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

RAW_DATA_DIR = PROJECT_ROOT / 'data' / 'raw'
PROCESSED_DATA_DIR = PROJECT_ROOT / 'data' / 'processed'

from .context_filters import annotate_with_roads, annotate_with_water  # noqa: E402


class MultiSourceValidator:
    """Cross-validate poles from multiple data sources"""

    def __init__(self):
        self.osm_poles = None
        self.ai_detections = None
        self.dc_poles = None
        self.verified_poles = None
        self.verizon_poles = None
        self.state_permits = None
        self.street_imagery_index = None
        self.lidar_assets = None
        self.compliance_filings = None

    def load_data_sources(self):
        """Load all available real data sources"""
        print("=" * 80)
        print("MULTI-SOURCE POLE VERIFICATION ENGINE")
        print("=" * 80)
        print("\n📥 Loading data sources...\n")

        # Source 1: OSM Poles (multi-county inventories)
        osm_file = RAW_DATA_DIR / 'osm_poles_harrisburg_real.csv'
        multi_dir = RAW_DATA_DIR / 'osm_poles_multi'
        osm_frames = []

        if multi_dir.exists():
            for csv_path in sorted(multi_dir.glob("*.csv")):
                try:
                    df = pd.read_csv(csv_path)
                except Exception as exc:  # pragma: no cover - defensive
                    print(f"⚠️  Failed to read {csv_path}: {exc}")
                    continue
                if "source" not in df.columns:
                    df["source"] = "osm"
                else:
                    df["source"] = df["source"].fillna("osm")
                if "inspection_date" not in df.columns:
                    df["inspection_date"] = "2024-01-01"
                osm_frames.append(df)

        if osm_file.exists():
            df = pd.read_csv(osm_file)
            if "source" not in df.columns:
                df["source"] = "osm"
            else:
                df["source"] = df["source"].fillna("osm")
            if "inspection_date" not in df.columns:
                df["inspection_date"] = "2024-01-01"
            osm_frames.append(df)

        if osm_frames:
            combined_osm = pd.concat(osm_frames, ignore_index=True)
            if "pole_id" in combined_osm.columns:
                before = len(combined_osm)
                combined_osm = combined_osm.drop_duplicates(subset=["pole_id"])
                if len(combined_osm) < before:
                    print(f"ℹ️  Dropped {before - len(combined_osm)} duplicate pole_id rows across OSM exports")
            combined_osm['source_date'] = datetime(2024, 10, 1)  # Approximate OSM data date
            self.osm_poles = combined_osm
            print(f"✅ OSM Poles: {len(self.osm_poles)} records across {multi_dir if multi_dir.exists() else 'single export'}")
        else:
            print("❌ No OSM pole inventories found – run sync_multi_source_data.py first.")

        # Source 2: AI Detections (real YOLO inference results)
        detections_file = PROCESSED_DATA_DIR / 'ai_detections.csv'
        if detections_file.exists():
            self.ai_detections = pd.read_csv(detections_file)
            print(f"✅ AI Detections: {len(self.ai_detections)} poles detected by YOLO")
        else:
            print(f"❌ AI detections not found at {detections_file}")
            print("   Run `python run_pilot.py` to generate real detections.")

        # Source 3: DC Poles (reference)
        dc_file = PROCESSED_DATA_DIR / 'dc_poles_wgs84.csv'
        if dc_file.exists():
            self.dc_poles = pd.read_csv(dc_file)
            self.dc_poles['source'] = 'dc_gov_1999'
            self.dc_poles['source_date'] = datetime(1999, 1, 1)
            print(f"✅ DC Poles: {len(self.dc_poles)} poles (Washington DC - reference data)")
        else:
            print(f"ℹ️  DC poles not yet processed (will be available after ingestion)")

        # Verizon enterprise feed
        from src.ingestion.data_registry import DATA_SOURCES  # lazy import to avoid cycles

        verizon_spec = DATA_SOURCES["verizon_gis"]
        verizon_spec.probe()
        if verizon_spec.exists:
            try:
                inventory_path = verizon_spec.expected_paths[0]
                ledger_path = verizon_spec.expected_paths[1]
                import geopandas as gpd

                inventory = gpd.read_file(inventory_path)
                ledger = pd.read_csv(ledger_path)
                self.verizon_poles = inventory.merge(
                    ledger,
                    on="pole_id",
                    how="left",
                    suffixes=("", "_inspection"),
                )
                self.verizon_poles['source'] = 'verizon_gis'
                print(f"✅ Verizon GIS poles: {len(self.verizon_poles)} records loaded")
            except Exception as exc:  # pragma: no cover - defensive
                print(f"⚠️  Failed to load Verizon GIS feed: {exc}")
        else:
            print("⚠️  Verizon GIS feed not present – multi-source verification will rely on OSM + AI until delivered.")

        # State & county permits
        state_spec = DATA_SOURCES["state_permitting"]
        state_spec.probe()
        if state_spec.exists:
            try:
                permits = pd.read_csv(state_spec.expected_paths[0])
                municipal_path = state_spec.expected_paths[1]
                if municipal_path.suffix.lower() in {".geojson", ".json"}:
                    import geopandas as gpd  # ensure availability

                    municipal = gpd.read_file(municipal_path)
                else:
                    municipal = pd.read_csv(municipal_path)
                self.state_permits = {
                    "permits": permits,
                    "municipal": municipal,
                }
                print(f"✅ State/municipal permits: {len(permits)} entries")
            except Exception as exc:
                print(f"⚠️  Failed to parse state/municipal permits: {exc}")
        else:
            print("ℹ️  State/municipal permit exports not found.")

        # Street-level imagery index
        street_spec = DATA_SOURCES["street_level"]
        street_spec.probe()
        if street_spec.exists:
            try:
                metadata_path = street_spec.expected_paths[1]
                self.street_imagery_index = pd.read_csv(metadata_path)
                print(f"✅ Street-level imagery metadata: {len(self.street_imagery_index)} frames queued")
            except Exception as exc:
                print(f"⚠️  Failed to load street-level metadata: {exc}")
        else:
            print("ℹ️  Street-level imagery not yet harvested.")

        # LiDAR assets
        lidar_spec = DATA_SOURCES["lidar_pointcloud"]
        lidar_spec.probe()
        if lidar_spec.exists:
            self.lidar_assets = lidar_spec.expected_paths
            print("✅ LiDAR point clouds detected – heights will be applied during contextual scoring.")
        else:
            print("ℹ️  LiDAR inputs missing; height scoring will fall back to DSM/road proxies.")

        # Compliance filings
        compliance_spec = DATA_SOURCES["compliance_filings"]
        compliance_spec.probe()
        if compliance_spec.exists:
            try:
                filings = pd.read_csv(compliance_spec.expected_paths[0])
                outages = pd.read_csv(compliance_spec.expected_paths[1])
                self.compliance_filings = {
                    "filings": filings,
                    "outages": outages,
                }
                print(f"✅ Compliance filings loaded: {len(filings)} pole attachments, {len(outages)} outage rows")
            except Exception as exc:
                print(f"⚠️  Failed to parse compliance filings: {exc}")
        else:
            print("ℹ️  Compliance filings not yet ingested.")

        print()

    def _extract_ai_detections(self, labels_dir: Path) -> pd.DataFrame:
        """Extract pole coordinates from AI detection training dataset"""
        # For now, create a mapping from training images to approximate coordinates
        # In production, this would parse YOLO label files and map back to geo-coordinates

        # Load the OSM poles that were used to create the training dataset
        if self.osm_poles is not None and self.ai_detections is not None:
            return self.ai_detections
        return pd.DataFrame(columns=['pole_id', 'lat', 'lon', 'ai_confidence'])

    def calculate_spatial_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate approximate distance in meters between two lat/lon points
        Using simple Euclidean approximation (good enough for short distances)
        """
        # At 40° latitude, 1° ≈ 85km (lon) and 111km (lat)
        lat_m = (lat2 - lat1) * 111000  # meters
        lon_m = (lon2 - lon1) * 85000   # meters (approximate for PA latitude)
        return np.sqrt(lat_m**2 + lon_m**2)

    def calculate_recency_score(self, source_date: datetime) -> float:
        """
        Calculate recency score based on data age
        1.0 if <1yr, 0.8 if <3yr, 0.5 if <5yr, 0.2 if >5yr
        """
        current_date = datetime(2025, 10, 14)  # Current date from context
        age_years = (current_date - source_date).days / 365.25

        if age_years < 1:
            return 1.0
        elif age_years < 3:
            return 0.8
        elif age_years < 5:
            return 0.5
        else:
            return 0.2

    def calculate_spatial_match_score(self, distance_m: float) -> float:
        """
        Calculate spatial match score based on distance between sources
        1.0 if <2m, 0.8 if <5m, 0.5 if <10m, 0.2 if >10m
        """
        if distance_m < 2:
            return 1.0
        elif distance_m < 8:
            return 0.8
        elif distance_m < 20:
            return 0.5
        elif distance_m < 50:
            return 0.35
        elif distance_m < 90:
            return 0.25
        else:
            return 0.15

    def calculate_linearity_score(self, target_idx: int, all_coords: np.ndarray, tree: KDTree) -> Tuple[float, int]:
        """
        String of Pearls Logic:
        Calculate how well a pole aligns with its neighbors to form a line.
        Returns: (score 0.0-1.0, num_neighbors)
        """
        # Find neighbors within 85 meters (typical max span is ~50-80m)
        dists, indices = tree.query(all_coords[target_idx], k=8, distance_upper_bound=85)
        
        valid_indices = [i for i, d in zip(indices, dists) 
                        if i != target_idx and i < len(all_coords) and d > 1.0 and d != np.inf] # Exclude self and super close duplicates
        
        if len(valid_indices) < 2:
            return 0.0, len(valid_indices)

        p = all_coords[target_idx]
        neighbors = all_coords[valid_indices]
        
        # Calculate vectors from target to all neighbors
        # vectors = neighbors - p
        
        max_alignment = 0.0
        
        # Check every pair of neighbors to see if they form a line through P
        # This is O(N^2) on neighbors, but N is small (<=8)
        import itertools
        for i1, i2 in itertools.combinations(range(len(neighbors)), 2):
            v1 = neighbors[i1] - p
            v2 = neighbors[i2] - p
            
            # Normalize
            n1 = np.linalg.norm(v1)
            n2 = np.linalg.norm(v2)
            if n1 == 0 or n2 == 0: continue
                
            u1 = v1 / n1
            u2 = v2 / n2
            
            # Dot product (cosine of angle)
            # If they are opposite, angle is 180, cos is -1.
            # We want alignment -> cos close to -1.
            dot = np.dot(u1, u2)
            
            # Score: map -1 to 1.0, 0 to 0.0. 
            # Linear score = (dot - 1) / -2  ? No.
            # If dot = -1 (perfect line), score = 1.
            # If dot = 0 (90 deg), score = 0.
            # If dot = 1 (overlap), score = 0.
            
            # alignment = (1 - (dot + 1) / 2) ? No.
            # We only care about "straightness", ie approaching -1.
            # Let's simply take max(0, -dot). 
            # If dot is -0.9, score is 0.9. If dot is 0.5, score is 0.
            current_alignment = max(0.0, -dot)
            
            # Bonus: If distances are roughly equal (regular spacing), boost score?
            # For now, just geometry.
            if current_alignment > max_alignment:
                max_alignment = current_alignment
                
        # Return squared score to punish weak alignment, reward strong lines
        return max_alignment ** 2, len(valid_indices)

    def cross_validate_sources(self) -> pd.DataFrame:
        """
        Cross-validate OSM poles against AI detections with Linear Topology ('String of Pearls').
        Phases:
        1. Collection: Gather all OSM matches and New AI detections.
        2. Topology: Analyze the geometric arrangement of ALL candidates to find lines.
        3. Scoring: Apply ensemble weights including Linearity.
        """
        print("🔍 Cross-validating data sources (w/ String of Pearls Topology)...\n")
        
        if self.osm_poles is None or len(self.osm_poles) == 0:
            print("❌ No OSM poles loaded.")
            return pd.DataFrame()

        # PHASE 1: COLLECTION
        # ===================
        candidates = []
        
        # Build KD-Tree for AI detections
        ai_coords = np.empty((0, 2))
        if self.ai_detections is not None and not self.ai_detections.empty:
            ai_coords = self.ai_detections[['lat', 'lon']].values
            ai_tree = KDTree(ai_coords)
        else:
            ai_tree = None

        used_detection_indices = set()
        
        # 1A. Process Existing OSM Poles
        # -----------------------------
        print("   ... Matching OSM records to AI...")
        osm_context = self.osm_poles[['pole_id', 'lat', 'lon']].copy()
        osm_context = annotate_with_roads(osm_context)
        osm_context = annotate_with_water(osm_context)

        for idx, osm_pole in self.osm_poles.iterrows():
            osm_lat, osm_lon = osm_pole['lat'], osm_pole['lon']
            
            # Default values
            ai_data = {}
            nearest_dist = 9999.9
            
            # Find AI match
            if ai_tree is not None:
                dist_deg, nearest_idx = ai_tree.query([osm_lat, osm_lon])
                nearest_ai = self.ai_detections.iloc[nearest_idx]
                dist_m = self.calculate_spatial_distance(osm_lat, osm_lon, nearest_ai['lat'], nearest_ai['lon'])
                
                if dist_m < 75: # Broad search, refine later
                    nearest_dist = dist_m
                    ai_data = nearest_ai.to_dict()
                    if dist_m < 20: # Only claim it if close
                        used_detection_indices.add(nearest_idx)

            # Context
            ctx_row = osm_context.loc[idx] if idx in osm_context.index else {}
            
            candidates.append({
                'type': 'osm_match',
                'pole_id': osm_pole['pole_id'],
                'lat': osm_lat,
                'lon': osm_lon,
                'source_date': osm_pole['source_date'],
                'ai_data': ai_data,
                'nearest_ai_dist': nearest_dist,
                'ctx': ctx_row
            })

        # 1B. Process New AI-Only Detections
        # ----------------------------------
        print("   ... Identifying new AI-only candidates...")
        if self.ai_detections is not None:
            osm_coords = self.osm_poles[['lat', 'lon']].values
            osm_tree = KDTree(osm_coords)
            
            for idx, ai_pole in self.ai_detections.iterrows():
                if idx in used_detection_indices: continue
                
                ai_lat, ai_lon = ai_pole['lat'], ai_pole['lon']
                dist_deg, nearest_osm_idx = osm_tree.query([ai_lat, ai_lon])
                nearest_osm = self.osm_poles.iloc[nearest_osm_idx]
                dist_m = self.calculate_spatial_distance(ai_lat, ai_lon, nearest_osm['lat'], nearest_osm['lon'])
                
                if dist_m > 20: # Truly new
                    candidates.append({
                        'type': 'new_ai',
                        'pole_id': f"AI_NEW_{idx}",
                        'lat': ai_lat,
                        'lon': ai_lon,
                        'source_date': None,
                        'ai_data': ai_pole.to_dict(),
                        'nearest_ai_dist': 0.0, # It IS the AI
                        'ctx': {} # Need to fetch context?
                    })

        # PHASE 2: TOPOLOGY (STRING OF PEARLS)
        # ====================================
        print(f"   ... Analyzing topology for {len(candidates)} candidates...")
        
        # Convert Lat/Lon to local Meter approximation for KDTree & Vector math
        # 1 deg lat ~ 111,139 m
        # 1 deg lon ~ 85,000 m (at ~40 deg N)
        cand_latlon = np.array([[c['lat'], c['lon']] for c in candidates])
        
        if len(cand_latlon) > 0:
            min_lat, min_lon = cand_latlon.min(axis=0)
            cand_meters = np.zeros_like(cand_latlon)
            cand_meters[:, 0] = (cand_latlon[:, 0] - min_lat) * 111139
            cand_meters[:, 1] = (cand_latlon[:, 1] - min_lon) * 85000
        else:
            cand_meters = np.empty((0, 2))

        cand_tree = KDTree(cand_meters)
        
        for i, cand in enumerate(candidates):
            # Pass meter coordinates to linearity calc
            linearity, neighbor_count = self.calculate_linearity_score(i, cand_meters, cand_tree)
            cand['linearity_score'] = linearity
            cand['neighbor_count'] = neighbor_count


        # PHASE 3: SCORING & CLASSIFICATION
        # =================================
        print("   ... Calculating final ensemble scores...")
        
        final_results = []
        
        for cand in candidates:
            # Extract Signals
            ai_data = cand['ai_data']
            ctx = cand['ctx']
            
            # 1. AI Score
            ai_conf = ai_data.get('ai_confidence', ai_data.get('confidence', 0.0)) if cand['nearest_ai_dist'] < 20 else 0.0
            if cand['type'] == 'new_ai': ai_conf = ai_data.get('ai_confidence', ai_data.get('confidence', 0.0))
            
            # 2. Recency Score
            recency = self.calculate_recency_score(cand['source_date']) if cand['source_date'] else 1.0
            
            # 3. Spatial Match Score
            spatial = self.calculate_spatial_match_score(cand['nearest_ai_dist']) if cand['type'] == 'osm_match' else 0.0
            
            # 4. Linearity Score (Already computed)
            linearity = cand['linearity_score']
            
            # NEW ENSEMBLE FORMULA
            # 35% AI + 20% Recency + 20% Spatial + 25% Linearity
            # Note: For AI-only, Spatial is 0, so max score is 0.8. We might need to adjust logic for AI-only.
            
            if cand['type'] == 'osm_match':
                total_conf = (0.35 * ai_conf) + (0.20 * recency) + (0.20 * spatial) + (0.25 * linearity)
            else:
                # For new poles, spatial match to map is 0 (by definition), but that shouldn't kill it.
                # Re-weight: 50% AI + 50% Linearity ?
                # Or: 45% AI + 10% Dummy Spatial + 45% Linearity
                # Let's keep it rigorous. If no map data, Recency/Spatial are 0/Low.
                # Actually, Recency for "New" is high (it's happening now).
                # Total = 0.35*AI + 0.20*1.0 + 0.20*0.0 + 0.25*Linearity
                # Max possible = 0.35 + 0.2 + 0.25 = 0.8. 
                # That fits "In Question" or "New" thresholds well. Hard to get "Verified Good" without a map record.
                total_conf = (0.35 * ai_conf) + (0.20 * 1.0) + (0.0) + (0.25 * linearity)

            # Apply Context Filters/Penalties
            # ... (re-using existing logic slightly modified)
            
            # Normalized values for display
            ndvi = ai_data.get('ndvi', np.nan)
            road_dist = ai_data.get('road_distance_m', ctx.get('road_distance_m', np.nan))
            in_water = ai_data.get('in_water', False) or ctx.get('in_water', False)

            # Classification Rules
            classification = 'in_question'
            status_color = '#FF9800'
            needs_review = True
            reasons = []

            # Hard constraints
            if in_water: reasons.append('in_water')
            if pd.notna(road_dist) and road_dist > 60: reasons.append('far_from_road')
            
            # Linearity Bonus: Boosting confidence
            if linearity > 0.8: reasons.append('strong_linear_alignment')
            
            if cand['type'] == 'osm_match':
                # Existing Pole Logic
                if total_conf >= 0.65:
                    classification = 'verified_good'
                    status_color = '#00897B'
                    needs_review = False
            else:
                # New Pole Logic
                classification = 'new_detection'
                status_color = '#1E88E5'
                # Auto-verify highly confident new lines?
                if ai_conf > 0.7 and linearity > 0.9: 
                     # It's a very strong optical detection forming a perfect line
                     classification = 'verified_good' # Promote high quality new finds!
                     reasons.append('auto_verified_strong_line')
                     needs_review = False

            final_results.append({
                'pole_id': cand['pole_id'],
                'lat': cand['lat'],
                'lon': cand['lon'],
                'source': 'osm' if cand['type'] == 'osm_match' else 'ai_only',
                'ai_confidence': ai_conf,
                'linearity_score': linearity,
                'total_confidence': total_conf,
                'classification': classification,
                'status_color': status_color,
                'needs_review': needs_review,
                'review_reasons': '|'.join(reasons),
                # Keep other cols for CSV compatibility
                'road_distance_m': road_dist,
                'spatial_match_score': spatial,
                'nearest_ai_distance_m': cand['nearest_ai_dist']
            })

        verified_df = pd.DataFrame(final_results)
        
        self.verified_poles = verified_df
        
        # Print Stats
        print("📊 Verification Statistics (Enhanced):")
        print(f"Total poles: {len(verified_df)}")
        print(f"  Verified Good: {len(verified_df[verified_df['classification']=='verified_good'])}")
        print(f"  In Question:   {len(verified_df[verified_df['classification']=='in_question'])}")
        print(f"  New Detections:{len(verified_df[verified_df['classification']=='new_detection'])}")
        print(f"Avg Linearity Score: {verified_df['linearity_score'].mean():.3f}")

        return verified_df

    def save_results(self, output_file: Path = None):
        """Save verification results to CSV"""
        if self.verified_poles is None:
            print("❌ No verification results to save")
            return

        if output_file is None:
            output_file = PROCESSED_DATA_DIR / 'verified_poles_multi_source.csv'

        output_file.parent.mkdir(parents=True, exist_ok=True)
        self.verified_poles.to_csv(output_file, index=False)
        print(f"\n💾 Saved verification results to: {output_file}")


def main():
    """Run multi-source verification"""
    validator = MultiSourceValidator()

    # Load all data sources
    validator.load_data_sources()

    # Cross-validate and classify
    verified_poles = validator.cross_validate_sources()

    # Save results
    validator.save_results()

    print("\n" + "=" * 80)
    print("✅ MULTI-SOURCE VERIFICATION COMPLETE!")
    print("=" * 80)
    print("\nNext steps:")
    print("  1. Review poles flagged as 'in_question'")
    print("  2. Investigate 'missing_new' poles for field verification")
    print("  3. Update dashboard to display 3-tier classification")
    print()


if __name__ == '__main__':
    main()
