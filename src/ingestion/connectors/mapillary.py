
"""
Mapillary API Connector.
Checks for street-level imagery availability to verify defects.
"""
import requests
import os
import logging

logger = logging.getLogger(__name__)

MAPILLARY_API_URL = "https://graph.mapillary.com"

class MapillaryClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("MAPILLARY_CLIENT_TOKEN")
        self.enabled = bool(self.api_key)
        
        if not self.enabled:
            logger.warning("Mapillary Token not found. Visual verification disabled.")

    def is_image_available(self, lat: float, lon: float, radius_m: int = 20) -> bool:
        """
        Check if an image exists near the target.
        """
        if not self.enabled:
            return False
            
        # Bbox logic
        # endpoint: /images?bbox=...
        
        headers = {"Authorization": f"OAuth {self.api_key}"}
        # ... logic ...
        return False
        
    def get_image_url(self, lat: float, lon: float):
        """
        Returns a thumbnail URL for the nearest image.
        """
        pass
