"""
Background runner for the PoleVision data pipeline.
Executes run_pilot.run_pilot_pipeline() in a worker thread so the API remains responsive.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional, Dict, Any, Callable
import traceback
import sys

# Ensure project root on path so run_pilot can be imported
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.append(str(PROJECT_ROOT))

_executor = ThreadPoolExecutor(max_workers=1)
_lock = Lock()
_current_future: Optional[Future] = None
_status: Dict[str, Any] = {
  "state": "idle",
  "started_at": None,
  "finished_at": None,
  "error": None,
  "message": "Pipeline has not been executed in this session.",
}
_run_pilot_callable: Optional[Callable[..., None]] = None
_import_error: Optional[BaseException] = None


def _load_run_pilot() -> Callable[..., None]:
  """Import run_pilot lazily so the API can start even if heavy deps are absent."""
  global _run_pilot_callable, _import_error  # pylint: disable=global-statement
  if _run_pilot_callable is not None:
    return _run_pilot_callable

  try:
    from run_pilot import run_pilot_pipeline as _runner  # type: ignore  # pylint: disable=import-error
  except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
    _import_error = exc
    raise RuntimeError(
      "Pipeline dependencies are unavailable. Install the geospatial stack to enable pipeline runs."
    ) from exc
  except Exception as exc:  # pragma: no cover - defensive
    _import_error = exc
    raise RuntimeError(
      "Pipeline dependencies failed to initialize. Inspect server logs for root cause."
    ) from exc

  _import_error = None
  _run_pilot_callable = _runner
  return _runner


def _update_status(**kwargs: Any) -> None:
  global _status  # pylint: disable=global-statement
  with _lock:
    _status = {**_status, **kwargs}


def get_status() -> Dict[str, Any]:
  """Return the latest pipeline status snapshot."""
  with _lock:
    # Return a shallow copy to avoid accidental mutation downstream
    return dict(_status)


def is_running() -> bool:
  """Return True if a pipeline execution is currently in progress."""
  with _lock:
    if _current_future is None:
      return False
    return not _current_future.done()


def _run_pipeline_task() -> Dict[str, Any]:
  """Worker executed within the executor."""
  started_at = datetime.utcnow().isoformat()
  _update_status(
    state="running",
    started_at=started_at,
    finished_at=None,
    error=None,
    message="Pipeline execution in progress (regenerating detections).",
  )
  try:
    runner = _load_run_pilot()
    try:
      runner(force_recompute=True)
    except TypeError:
      # Backwards compatibility with older implementations that ignore the flag.
      runner()
  except Exception as exc:  # pragma: no cover - protective logging
    tb = traceback.format_exc()
    finished_at = datetime.utcnow().isoformat()
    _update_status(
      state="error",
      finished_at=finished_at,
      error=str(exc),
      message="Pipeline execution failed. Inspect server logs for details.",
      traceback=tb,
    )
    return get_status()

  finished_at = datetime.utcnow().isoformat()
  _update_status(
    state="completed",
    finished_at=finished_at,
    error=None,
    message="Pipeline completed successfully.",
  )
  return get_status()


def trigger_pipeline() -> Dict[str, Any]:
  """Start the pipeline if not already running."""
  global _current_future  # pylint: disable=global-statement
  with _lock:
    if _current_future is not None and not _current_future.done():
      raise RuntimeError("Pipeline execution already in progress.")
    _current_future = _executor.submit(_run_pipeline_task)
  return get_status()
