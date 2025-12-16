
import numpy as np
from sklearn.neighbors import NearestNeighbors
import math
import logging

class PearlStringer:
    def __init__(self, spacing_min=30, spacing_max=60):
        self.spacing_min = spacing_min
        self.spacing_max = spacing_max
        self.logger = logging.getLogger("PearlStringer")

    def find_missing_pearls(self, pole_coordinates: list[tuple[float, float]], session=None, write_to_db=False):
        """
        Identifies potential missing poles ('gaps') in a chain of detected poles.
        
        Args:
            pole_coordinates: List of (lat, lon) tuples of CONFIRMED detections.
            session: SQLModel Session (optional)
            write_to_db: Boolean, if True inserts 'Missing' poles to DB.
            
        Returns:
            List of (lat, lon) suggested search locations.
        """
        if len(pole_coordinates) < 2:
            return []
            
        missing_candidates = []
        
        # Build neighbor graph
        X = np.array(pole_coordinates)
        nbrs = NearestNeighbors(n_neighbors=min(3, len(X)), algorithm='ball_tree').fit(X)
        distances, indices = nbrs.kneighbors(X)
        
        # Iterate through every pole
        for i, neighbors in enumerate(indices):
            if len(neighbors) < 2: continue
            
            self_idx = neighbors[0] # itself
            closest_idx = neighbors[1] # 1st neighbor
            dist_m = self.estimate_distance_m(pole_coordinates[self_idx], pole_coordinates[closest_idx])
            
            # Logic: If distance is ~double the standard spacing (e.g. 70-100m)
            # there is likely a missing pole in the middle.
            if self.spacing_max < dist_m < (self.spacing_max * 2.2):
                p1 = np.array(pole_coordinates[self_idx])
                p2 = np.array(pole_coordinates[closest_idx])
                
                # Calculate Midpoint
                midpoint = (p1 + p2) / 2
                midpoint_tuple = tuple(midpoint)
                
                self.logger.info(f"Gap Detected ({dist_m:.1f}m). Predicting Pearl at {midpoint_tuple}")
                missing_candidates.append(midpoint_tuple)
                
        # Unique candidates
        unique_candidates = sorted(list(set(missing_candidates)))
        
        # Write to DB if requested
        if write_to_db and session and unique_candidates:
            from models import Pole
            from geoalchemy2.shape import from_shape
            from shapely.geometry import Point
            import uuid
            from datetime import datetime
            
            count = 0
            for lat, lon in unique_candidates:
                # Check duplication first (simple check)
                # Ideally check against existing DB poles? 
                # For now just trust the gap analysis relative to *these* poles.
                
                new_pole = Pole(
                     id=uuid.uuid4(),
                     pole_id=f"AI_PEARL_{uuid.uuid4().hex[:6]}",
                     status="Missing", # Trigger for Re-Scan
                     location=from_shape(Point(lon, lat), srid=4326),
                     last_verified_at=datetime.utcnow(),
                     tags={"source": "PearlGapAnalysis", "confidence": 0.0, "reason": "Consistent Spacing Gap"},
                     financial_impact=0.0
                )
                session.add(new_pole)
                count += 1
            
            try:
                session.commit()
                self.logger.info(f"✅ Inserted {count} 'Missing' poles into DB for AI Re-Scan.")
            except Exception as e:
                self.logger.error(f"Failed to write pearls to DB: {e}")
                session.rollback()

        return unique_candidates

    def estimate_distance_m(self, p1, p2):
        # Haversine approx
        R = 6371000
        lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
        lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

# --- TEST ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    stringer = PearlStringer(spacing_min=30, spacing_max=50)
    
    # Simulate a chain with a gap
    # Pole 1 --35m-- Pole 2 --(Missing 70m)-- Pole 3
    # Lat~40.0, 1 deg lat ~ 111km -> 1m ~ 0.000009 deg
    chain = [
        (40.00000, -75.00000),      # Pole 0
        (40.00035, -75.00000),      # Pole 1 (+39m)
        (40.00100, -75.00000),      # Pole 2 (+72m Gap from Pole 1) -> Predicted: 40.000675
        (40.00135, -75.00000)       # Pole 3 (+39m)
    ]
    
    suggestions = stringer.find_missing_pearls(chain)
    print("Suggested Search Locations:", suggestions)
