from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlmodel import SQLModel, Field, Column
from geoalchemy2 import Geometry
from pydantic import ConfigDict
import uuid

# JSON Type for Tags
from sqlalchemy.dialects.postgresql import JSONB

class PoleBase(SQLModel):
    pole_id: str = Field(index=True, unique=True)
    status: str = Field(default="Review") # Verified, Critical, Review, Flagged, Missing
    financial_impact: float = Field(default=0.0)
    height_ag_m: Optional[float] = Field(default=None)
    tags: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    last_verified_at: datetime = Field(default_factory=datetime.utcnow)

class Pole(PoleBase, table=True):
    __tablename__ = "poles"
    
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, primary_key=True)
    
    # PostGIS Geometry Column (Point, SRID 4326)
    location: Any = Field(sa_column=Column(Geometry("POINT", srid=4326)))
    
    class Config:
        arbitrary_types_allowed = True

class DetectionBase(SQLModel):
    confidence: float
    class_name: str
    image_path: Optional[str] = None
    run_id: Optional[str] = None
    height_ag_m: Optional[float] = None
    road_distance_m: Optional[float] = None
    tags: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB))

class Detection(DetectionBase, table=True):
    __tablename__ = "detections"
    
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # PostGIS Geometry
    location: Any = Field(sa_column=Column(Geometry("POINT", srid=4326)))
    
    class Config:
        arbitrary_types_allowed = True

class Job(SQLModel, table=True):
    __tablename__ = "jobs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    status: str = Field(default="Pending")
    meta_data: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Tile(SQLModel, table=True):
    __tablename__ = "tiles"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    path: str = Field(unique=True)
    bbox: Any = Field(sa_column=Column(Geometry("POLYGON", srid=4326)))
    status: str = Field(default="Pending")
    retry_count: int = Field(default=0)
    last_processed_at: Optional[datetime] = None
    
    class Config:
        arbitrary_types_allowed = True

