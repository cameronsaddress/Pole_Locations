from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uuid
import random

router = APIRouter(prefix="/api/v2/work-orders", tags=["Work Orders"])

class WorkOrderCreate(BaseModel):
    asset_id: str
    issue_type: str
    priority: str
    description: Optional[str] = None
    assigned_crew: Optional[str] = None

class WorkOrder(WorkOrderCreate):
    id: str
    status: str # Open, Assigned, In Progress, Closed
    created_at: str
    estimated_cost: float

# Mock Database
WORK_ORDERS = []

@router.post("/", response_model=WorkOrder)
async def create_work_order(wo: WorkOrderCreate):
    """
    Create a new utility work order (ticket).
    Integrates with standard utility ERP formats (SAP/Maximo simulated).
    """
    # Simulate cost estimation based on issue
    cost_map = {
        "Leaning Pole (Critical)": 15000.0,
        "Structural Damage": 25000.0,
        "Veg. Encroachment": 4500.0,
        "Transformer Rust": 2500.0,
        "Bio-Hazard (Nest)": 1200.0,
        "Unauthorized Attach.": 500.0
    }
    
    new_wo = WorkOrder(
        id=f"WO-{datetime.now().year}-{random.randint(10000,99999)}",
        **wo.dict(),
        status="Open",
        created_at=datetime.utcnow().isoformat(),
        estimated_cost=cost_map.get(wo.issue_type, 1000.0)
    )
    
    WORK_ORDERS.append(new_wo)
    return new_wo

@router.get("/", response_model=List[WorkOrder])
async def list_work_orders(status: Optional[str] = None):
    if status:
        return [w for w in WORK_ORDERS if w.status == status]
    return WORK_ORDERS

@router.get("/{wo_id}", response_model=WorkOrder)
async def get_work_order(wo_id: str):
    for w in WORK_ORDERS:
        if w.id == wo_id:
            return w
    raise HTTPException(status_code=404, detail="Work Order not found")

@router.patch("/{wo_id}/dispatch")
async def dispatch_crew(wo_id: str, crew_id: str):
    for w in WORK_ORDERS:
        if w.id == wo_id:
            w.status = "Assigned"
            w.assigned_crew = crew_id
            return w
    raise HTTPException(status_code=404, detail="Work Order not found")
