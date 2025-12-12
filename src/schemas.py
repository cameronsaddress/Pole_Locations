from pydantic import BaseModel, Field
from typing import List, Optional, Any

class PoleDetectionResult(BaseModel):
    """
    Standardized payload from the AI detection model.
    """
    pole_id: str
    lat: float
    lon: float
    ai_confidence: float
    tile_path: str
    pixel_x: float
    pixel_y: float
    bbox: List[float] # [x1, y1, x2, y2]
    class_name: str = "utility_pole"
    ndvi: Optional[float] = None
    tags: Optional[dict] = None
    
class BatchDetectionResult(BaseModel):
    """
    Wrapper for bulk results from a single tile/image.
    """
    tile_id: int
    image_path: str
    detections: List[PoleDetectionResult]
