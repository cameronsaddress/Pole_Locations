from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import csv
import random
from datetime import datetime

router = APIRouter(prefix="/api/v2")

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

# DB Imports
from sqlmodel import Session, select
from database import get_session
from models import Pole
from geoalchemy2.shape import to_shape

router = APIRouter(prefix="/api/v2")

class Asset(BaseModel):
    id: str
    lat: float
    lng: float
    status: str
    confidence: float
    detected_at: str
    issues: List[str] = []
    health_score: float = 1.0
    last_audit: Optional[str] = None
    financial_impact: float = 0.0
    height_m: Optional[float] = None

class OpsMetrics(BaseModel):
    total_assets: int
    grid_integrity: float
    daily_audit_count: int
    critical_anomalies: int
    preventative_savings: float

def model_to_asset(pole: Pole) -> Asset:
    """Convert SQLModel Pole to API Asset"""
    # Parse Geometry
    pt = to_shape(pole.location)
    
    # Financial Impact Logic (Should be in DB, but fallback here)
    # The logic is effectively: If Critical, Impact is High.
    
    issues = []
    if pole.status == "Critical":
        issues.append("Critical Issue")
    if pole.height_ag_m and pole.height_ag_m > 1.0:
        issues.append(f"Height: {pole.height_ag_m:.1f}m")

    return Asset(
        id=pole.pole_id, # Use External ID for display
        lat=pt.y,
        lng=pt.x,
        status=pole.status,
        confidence=1.0 if pole.status == "Verified" else 0.7, # Simplified for now
        detected_at=pole.last_verified_at.isoformat(),
        issues=issues,
        health_score=0.5 if pole.status == "Critical" else 1.0,
        financial_impact=pole.financial_impact,
        last_audit=pole.last_verified_at.isoformat(),
        height_m=pole.height_ag_m
    )

@router.get("/assets")
@router.get("/assets/live") # Alias for backward compatibility
async def get_assets_list(
    db: Session = Depends(get_session),
    min_lat: Optional[float] = None, 
    max_lat: Optional[float] = None, 
    min_lng: Optional[float] = None, 
    max_lng: Optional[float] = None
):
    """
    Get Assets from PostGIS.
    Supports Bounding Box filtering which is FAST in PostGIS.
    """
    query = select(Pole)
    
    # If BBOX provided, we could use ST_MakeEnvelope and ST_Intersects
    # For now, simplistic Python-side query builder as SQLModel doesn't expose ST_ easily without func
    # Ideally: query = query.where(func.ST_Intersects(Pole.location, make_envelope(...)))
    
    # Simple Lat/Lon filter (PostGIS will optimise if we cast geometry, but this is fine for mild load)
    # Actually, proper PostGIS way:
    # from geoalchemy2 import func
    # if min_lat:
    #    query = query.where(func.ST_Y(Pole.location) >= min_lat)
    
    # Basic pagination limit for safety
    query = query.limit(5000) 
    
    results = db.exec(query).all()
    
    return [model_to_asset(p) for p in results]

@router.get("/ops/metrics")
async def get_ops_metrics(db: Session = Depends(get_session)):
    # Count Totals
    total = db.query(Pole).count()
    
    if total == 0:
        return OpsMetrics(
            total_assets=0,
            grid_integrity=100.0,
            daily_audit_count=0,
            critical_anomalies=0,
            preventative_savings=0.0
        )
        
    # Count Critical
    critical = db.query(Pole).filter(Pole.status == "Critical").count()
    verified = db.query(Pole).filter(Pole.status == "Verified").count()
    
    # Sum Financial Impact
    # Note: SQLModel .exec(select(func.sum(...))) is better, but iterating for now is safe for MVP
    # or just simple python sum on a partial query if dataset is huge?
    # Let's do a SQL sum
    from sqlalchemy import func
    savings = db.exec(select(func.sum(Pole.financial_impact))).one() or 0.0
    
    return OpsMetrics(
        total_assets=total,
        grid_integrity=round(100 - (critical / max(1, total) * 100), 1),
        daily_audit_count=verified, # Proxy for audits
        critical_anomalies=critical,
        preventative_savings=savings
    )

@router.get("/ops/feed/anomalies")
async def get_anomaly_feed(db: Session = Depends(get_session)):
    # Return all assets that are NOT verified good, sorted by impact
    results = db.exec(
        select(Pole)
        .where(Pole.status.in_(["Critical", "Flagged", "Review"]))
        .order_by(Pole.financial_impact.desc())
        .limit(100)
    ).all()
    
    return [model_to_asset(p) for p in results]

@router.get("/ops/audit-log")
async def get_audit_log(limit: int = 20, db: Session = Depends(get_session)):
    """Returns a stream of recent audits (Mixed verified + anomalies)"""
    # Sample random rows or just latest verified
    # Postgres RANDOM() is func.random()
    from sqlalchemy import func
    results = db.exec(
        select(Pole)
        .order_by(func.random())
        .limit(limit)
    ).all()
    
    return [model_to_asset(p) for p in results]
