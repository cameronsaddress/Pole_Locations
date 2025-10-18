#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"
DEFAULT_BACKEND_PORT=8021
DEFAULT_FRONTEND_PORT=5173
REQUESTED_BACKEND_PORT="${BACKEND_PORT:-$DEFAULT_BACKEND_PORT}"
REQUESTED_FRONTEND_PORT="${FRONTEND_PORT:-$DEFAULT_FRONTEND_PORT}"
RUN_PIPELINE="${RUN_PIPELINE:-0}"
VENV_PYTHON="${PROJECT_ROOT}/venv/bin/python"
UVICORN_BIN="${PROJECT_ROOT}/venv/bin/uvicorn"
POLES_CSV="${PROJECT_ROOT}/data/raw/osm_poles_harrisburg_real.csv"
TILES_DIR="${PROJECT_ROOT}/data/imagery/naip_tiles"
MAX_TILES="${MAX_TILES:-16}"

echo "[start.sh] Working directory: ${PROJECT_ROOT}"

if ! command -v lsof >/dev/null 2>&1; then
  echo "[start.sh] ERROR: 'lsof' command not found. Install lsof to enable port detection." >&2
  exit 1
fi

find_open_port() {
  local start_port=$1
  local max_attempts=${2:-50}
  local port=$start_port
  local attempts=0

  while [[ ${attempts} -lt ${max_attempts} ]]; do
    if ! lsof -iTCP:${port} -sTCP:LISTEN >/dev/null 2>&1; then
      echo "${port}"
      return 0
    fi
    port=$((port + 1))
    attempts=$((attempts + 1))
  done

  echo "[start.sh] ERROR: Unable to find open port (start=${start_port}, attempts=${max_attempts})." >&2
  exit 1
}

BACKEND_PORT="$(find_open_port "${REQUESTED_BACKEND_PORT}")"
FRONTEND_PORT="$(find_open_port "${REQUESTED_FRONTEND_PORT}")"
echo "[start.sh] Selected backend port: ${BACKEND_PORT} (requested ${REQUESTED_BACKEND_PORT})"
echo "[start.sh] Selected frontend port: ${FRONTEND_PORT} (requested ${REQUESTED_FRONTEND_PORT})"

export BACKEND_PORT FRONTEND_PORT
export VITE_BACKEND_PORT="${BACKEND_PORT}"
export VITE_FRONTEND_PORT="${FRONTEND_PORT}"

if [[ "${FRONTEND_PORT}" == "${BACKEND_PORT}" ]]; then
  FRONTEND_PORT="$(find_open_port "$((FRONTEND_PORT + 1))")"
  echo "[start.sh] Adjusted frontend port to avoid backend conflict: ${FRONTEND_PORT}"
  export FRONTEND_PORT
  export VITE_FRONTEND_PORT="${FRONTEND_PORT}"
fi

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "[start.sh] ERROR: virtual environment Python not found at ${VENV_PYTHON}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}"

echo "[start.sh] Stopping existing backend/frontend processes…"
pkill -f "uvicorn backend.app.main:app" 2>/dev/null || true
pkill -f "npm run dev" 2>/dev/null || true
pkill -f "[v]ite" 2>/dev/null || true
sleep 1

if [[ "${RUN_PIPELINE}" == "1" ]]; then
  echo "[start.sh] RUN_PIPELINE=1 => executing full data pipeline"

  echo "[start.sh] Downloading NAIP imagery tiles (max ${MAX_TILES})…"
  PYTHONPATH="${PROJECT_ROOT}/backend" "${VENV_PYTHON}" "${PROJECT_ROOT}/src/utils/download_naip_pc.py" \
    --output-dir "${TILES_DIR}" \
    --no-mosaic \
    --max-tiles "${MAX_TILES}"

  echo "[start.sh] Extracting pole crops from downloaded tiles…"
  PYTHONPATH="${PROJECT_ROOT}/backend" "${VENV_PYTHON}" "${PROJECT_ROOT}/src/utils/extract_pole_crops.py" \
    --imagery "${TILES_DIR}" \
    --poles "${POLES_CSV}" \
    --output "${PROJECT_ROOT}/data/processed/pole_training_dataset" \
    --crop-size 256 \
    --clean

  echo "[start.sh] Preparing YOLO dataset splits…"
  PYTHONPATH="${PROJECT_ROOT}/backend" "${VENV_PYTHON}" "${PROJECT_ROOT}/src/utils/prepare_yolo_dataset.py"

  echo "[start.sh] Clearing cached detections…"
  rm -f "${PROJECT_ROOT}/data/processed/ai_detections.csv" "${PROJECT_ROOT}/data/processed/ai_detections_metadata.json" || true

  echo "[start.sh] Running verification pipeline (run_pilot.py)…"
  PYTHONPATH="${PROJECT_ROOT}/backend" "${VENV_PYTHON}" "${PROJECT_ROOT}/run_pilot.py"
else
  echo "[start.sh] RUN_PIPELINE=${RUN_PIPELINE}. Skipping heavy data pipeline tasks."
  echo "[start.sh] Use the dashboard \"Refresh Pipeline\" button or rerun with RUN_PIPELINE=1 when data needs to be regenerated."
fi

echo "[start.sh] Starting backend on port ${BACKEND_PORT}…"
PYTHONPATH="${PROJECT_ROOT}/backend" "${UVICORN_BIN}" backend.app.main:app \
  --reload --port "${BACKEND_PORT}" > "${LOG_DIR}/backend.log" 2>&1 &
echo $! > "${LOG_DIR}/backend.pid"

echo "[start.sh] Starting frontend on port ${FRONTEND_PORT}…"
(
  cd "${PROJECT_ROOT}/frontend"
  npm run dev -- --host --port "${FRONTEND_PORT}" > "${LOG_DIR}/frontend.log" 2>&1 &
  echo $! > "${LOG_DIR}/frontend.pid"
)

BACKEND_PID=$(cat "${LOG_DIR}/backend.pid")
FRONTEND_PID=$(cat "${LOG_DIR}/frontend.pid")

echo "[start.sh] Backend PID: ${BACKEND_PID} (log: ${LOG_DIR}/backend.log)"
echo "[start.sh] Frontend PID: ${FRONTEND_PID} (log: ${LOG_DIR}/frontend.log)"
echo "[start.sh] Frontend available at http://localhost:${FRONTEND_PORT}"
