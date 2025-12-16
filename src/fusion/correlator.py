
import math
import logging

class SensorFusion:
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("FusionEngine")

    def calculate_satellite_correction(self, map_lat, map_lon, bbox_norm, tile_size_meters=35, tile_pixels=512):
        """
        Calculates the TRUE geolocation of a pole based on its bounding box detection in a satellite tile.
        
        Args:
            map_lat (float): The center latitude of the tile (the query coordinate).
            map_lon (float): The center longitude of the tile.
            bbox_norm (tuple): (x_center, y_center, width, height) normalized 0-1.
            tile_size_meters (float): The total width of the tile in meters (e.g. 35m).
            tile_pixels (int): The pixel dimension of the tile (e.g. 512).
            
        Returns:
            (float, float): lat_corrected, lon_corrected
        """
        cx, cy, _, _ = bbox_norm
        
        # 0.5, 0.5 is the center (the map_lat, map_lon)
        # Deviation in pixels (normalized)
        dx_norm = cx - 0.5
        dy_norm = 0.5 - cy  # Y is inverted in images (0 is top)
        
        # Convert to meters
        dx_meters = dx_norm * tile_size_meters
        dy_meters = dy_norm * tile_size_meters
        
        # Earth Constants
        R_EARTH = 6378137.0  # meters
        
        # Coordinate Shift
        # dLat = dy / R
        # dLon = dx / (R * cos(lat))
        
        dLat = (dy_meters / R_EARTH) * (180 / math.pi)
        dLon = (dx_meters / R_EARTH) * (180 / math.pi) / math.cos(map_lat * math.pi / 180)
        
        lat_corrected = map_lat + dLat
        lon_corrected = map_lon + dLon
        
        self.logger.debug(f"Sat Correction: {dx_meters:.2f}m E, {dy_meters:.2f}m N -> ({lat_corrected:.6f}, {lon_corrected:.6f})")
        return lat_corrected, lon_corrected

    def calculate_bearing(self, lat1, lon1, lat2, lon2):
        """Standard Haversine initial bearing calculation."""
        dLon = (lon2 - lon1) * math.pi / 180.0
        lat1 = lat1 * math.pi / 180.0
        lat2 = lat2 * math.pi / 180.0
        
        y = math.sin(dLon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dLon)
        
        bearing_rad = math.atan2(y, x)
        bearing_deg = (bearing_rad * 180.0 / math.pi + 360) % 360
        return bearing_deg

    def verify_with_street_view(self, pole_lat, pole_lon, car_lat, car_lon, camera_heading, tolerance_deg=10.0):
        """
        Projects a ray from the car to the candidate pole and checks if it aligns with the camera heading.
        
        Args:
            pole_lat/lon: The candidate pole location (e.g., from Satellite).
            car_lat/lon: The GPS position of the street view car.
            camera_heading: The compass heading of the camera (0-360).
            tolerance_deg: Acceptable angular deviation.
            
        Returns:
            (bool, float): (Match Success, Deviation in Degrees)
        """
        expected_bearing = self.calculate_bearing(car_lat, car_lon, pole_lat, pole_lon)
        
        deviation = abs(expected_bearing - camera_heading)
        # Handle wrap-around (e.g. 359 vs 1)
        if deviation > 180:
            deviation = 360 - deviation
            
        is_match = deviation <= tolerance_deg
        
        self.logger.info(f"Fusion Check: Car Bearing {expected_bearing:.1f}° vs Cam {camera_heading:.1f}° | Dev: {deviation:.1f}° | Match: {is_match}")
        
        return is_match, deviation

# --- TEST HARNESS ---
if __name__ == "__main__":
    fusion = SensorFusion()
    
    print("\n--- TEST 1: Satellite Correction ---")
    # Scenario: Pole is 10m North-East of center
    # 0.5 is center. If we want NE (+x, -y pixels), say 0.7, 0.3
    # Tile 35m wide. 0.2 * 35 = 7m. Close enough.
    
    orig_lat, orig_lon = 40.000000, -75.000000
    bbox = (0.7, 0.3, 0.1, 0.1) # x, y, w, h
    
    new_lat, new_lon = fusion.calculate_satellite_correction(orig_lat, orig_lon, bbox)
    print(f"Original: {orig_lat}, {orig_lon}")
    print(f"Corrected: {new_lat}, {new_lon}")
    
    print("\n--- TEST 2: Street View Correlation ---")
    # Scenario: Car is directly South of the New Pole, facing North (0 deg)
    car_lat = new_lat - 0.0001 # ~11m South
    car_lon = new_lon
    
    # Check with Camera Heading = 0 (North) -> Should Match
    fusion.verify_with_street_view(new_lat, new_lon, car_lat, car_lon, camera_heading=0)
    
    # Check with Camera Heading = 90 (East) -> Should Fail
    fusion.verify_with_street_view(new_lat, new_lon, car_lat, car_lon, camera_heading=90)
