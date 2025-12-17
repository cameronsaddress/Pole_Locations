from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from pathlib import Path
from src.pipeline.manager import PipelineManager

router = APIRouter(prefix="/api/v2/pipeline", tags=["pipeline"])

class JobRequest(BaseModel):
    params: Dict[str, Any] = {}

@router.get("/datasets")
def get_datasets():
    """List available datasets grouped by region."""
    return Response(content=log_content, media_type="text/plain")

@router.get("/serve_image/{filename}")
def serve_image(filename: str, dataset: str = "street"):
    """Serves a training image from the disk."""
    from fastapi.responses import FileResponse
    
    base = Path("/data/training")
    if dataset == "satellite":
        image_path = base / "satellite_drops/images" / filename
    else:
        # Street default
        image_path = base / "layer1_drops/images" / filename
        
    if not image_path.exists():
        return Response(status_code=404)
    return FileResponse(image_path)

@router.post("/run/{job_type}")
def run_pipeline_job(job_type: str, request: JobRequest):
    """
    Trigger a pipeline job.
    job_type options: 'integrity', 'train_satellite', 'train_street', 'inference', 'full_pipeline'
    """
    try:
        pid = PipelineManager.run_job(job_type, request.params)
        return {"status": "started", "job_type": job_type, "pid": pid}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/logs")
def get_pipeline_logs(lines: int = 50):
    """Fetch recent logs from the pipeline execution."""
    logs = PipelineManager.get_logs(lines)
    return {"logs": logs}

@router.get("/status")
def get_pipeline_status():
    """Get status of current or last job."""
    return PipelineManager.get_job_status()
