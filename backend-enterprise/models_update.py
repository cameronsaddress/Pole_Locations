
from typing import Optional, Any
from datetime import datetime
from sqlmodel import SQLModel, Field, Column
from geoalchemy2 import Geometry
import uuid

class StreetViewImage(SQLModel, table=True):
    __tablename__ = "street_view_images"
    
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, primary_key=True)
    provider: str = Field(default="Mapillary") # or Google
    image_key: str = Field(unique=True) # Unique ID from provider
    
    # Camera Position
    location: Any = Field(sa_column=Column(Geometry("POINT", srid=4326)))
    heading: float = Field(default=0.0)
    pitch: float = Field(default=0.0)
    fov: float = Field(default=90.0)
    
    captured_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        arbitrary_types_allowed = True
