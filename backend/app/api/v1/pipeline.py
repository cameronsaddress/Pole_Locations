from fastapi import APIRouter, HTTPException

from app.services import pipeline_runner

router = APIRouter()


@router.get("/pipeline/status")
async def get_pipeline_status():
  """Return the latest status of the data pipeline."""
  return pipeline_runner.get_status()


@router.post("/pipeline/run")
async def start_pipeline():
  """Trigger the data pipeline in the background."""
  try:
    status = pipeline_runner.trigger_pipeline()
  except RuntimeError as exc:
    raise HTTPException(status_code=409, detail=str(exc)) from exc
  return status
