#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "${INSIDE_DGX_CONTAINER:-}" ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "[start.sh] ERROR: Docker is required to run the GPU container." >&2
    exit 1
  fi

  CONTAINER_NAME="${POLE_DGX_CONTAINER_NAME:-polelocations-gpu}"
  DOCKER_IMAGE="${POLE_DGX_IMAGE:-nvcr.io/nvidia/pytorch:25.09-py3}"

  EXISTING_ID="$(docker ps -a --filter "name=^/${CONTAINER_NAME}$" -q)"
  LAUNCH_CONTAINER() {
    echo "[start.sh] Launching GPU container '${CONTAINER_NAME}' from ${DOCKER_IMAGE}…"
    docker run -d --gpus all --network host --ipc=host --ulimit memlock=-1 --ulimit stack=67108864 \
      -v "${PROJECT_ROOT}:/workspace" \
      --name "${CONTAINER_NAME}" \
      "${DOCKER_IMAGE}" sleep infinity >/dev/null
  }

  if [[ -z "${EXISTING_ID}" ]]; then
    LAUNCH_CONTAINER
  else
    RUNNING_ID="$(docker ps --filter "name=^/${CONTAINER_NAME}$" -q)"
    if [[ -z "${RUNNING_ID}" ]]; then
      echo "[start.sh] Starting existing container '${CONTAINER_NAME}'…"
      docker start "${CONTAINER_NAME}" >/dev/null
    fi
    NETWORK_MODE="$(docker inspect -f '{{.HostConfig.NetworkMode}}' "${CONTAINER_NAME}")"
    CURRENT_IMAGE="$(docker inspect -f '{{.Config.Image}}' "${CONTAINER_NAME}")"
    if [[ "${NETWORK_MODE}" != "host" ]]; then
      echo "[start.sh] Recreating container '${CONTAINER_NAME}' to enable host networking…"
      docker stop "${CONTAINER_NAME}" >/dev/null
      docker rm "${CONTAINER_NAME}" >/dev/null
      LAUNCH_CONTAINER
    elif [[ "${CURRENT_IMAGE}" != "${DOCKER_IMAGE}" ]]; then
      echo "[start.sh] Recreating container '${CONTAINER_NAME}' to use image ${DOCKER_IMAGE} (found ${CURRENT_IMAGE})…"
      docker stop "${CONTAINER_NAME}" >/dev/null
      docker rm "${CONTAINER_NAME}" >/dev/null
      LAUNCH_CONTAINER
    fi
  fi

  echo "[start.sh] Provisioning container environment (first run may take several minutes)…"
  docker exec "${CONTAINER_NAME}" bash -lc 'cd /workspace && ./.docker_setup_pipeline.sh'

  ENV_FLAGS=(--env INSIDE_DGX_CONTAINER=1)
  ENV_FLAGS+=(--env RUN_PIPELINE="${RUN_PIPELINE:-0}")
  [[ -n "${BACKEND_PORT:-}" ]] && ENV_FLAGS+=(--env BACKEND_PORT="${BACKEND_PORT}")
  [[ -n "${FRONTEND_PORT:-}" ]] && ENV_FLAGS+=(--env FRONTEND_PORT="${FRONTEND_PORT}")
  [[ -n "${MAX_TILES:-}" ]] && ENV_FLAGS+=(--env MAX_TILES="${MAX_TILES}")
  HOST_IP_VALUE="${HOST_LAN_IP:-$(hostname -I | awk '{print $1}')}"
  ENV_FLAGS+=(--env HOST_LAN_IP="${HOST_IP_VALUE}")

  docker exec -i "${ENV_FLAGS[@]}" "${CONTAINER_NAME}" bash -lc 'cd /workspace && ./start.sh'

  if [[ -f "${PROJECT_ROOT}/logs/last_start_ports" ]]; then
    source "${PROJECT_ROOT}/logs/last_start_ports"
    echo "[start.sh] Backend API: http://${HOST_IP_VALUE:-localhost}:${BACKEND_PORT}/api/docs"
    echo "[start.sh] Frontend UI:  http://${HOST_IP_VALUE:-localhost}:${FRONTEND_PORT}"
  fi
  exit 0
fi

LOG_DIR="${PROJECT_ROOT}/logs"
DEFAULT_BACKEND_PORT=8021
DEFAULT_FRONTEND_PORT=5173
REQUESTED_BACKEND_PORT="${BACKEND_PORT:-$DEFAULT_BACKEND_PORT}"
REQUESTED_FRONTEND_PORT="${FRONTEND_PORT:-$DEFAULT_FRONTEND_PORT}"
RUN_PIPELINE="${RUN_PIPELINE:-0}"
POLES_CSV="${PROJECT_ROOT}/data/raw/osm_poles_harrisburg_real.csv"
TILES_DIR="${PROJECT_ROOT}/data/imagery/naip_tiles"
MAX_TILES="${MAX_TILES:-16}"
VERIFIED_FILE="${PROJECT_ROOT}/data/processed/verified_poles_multi_source.csv"
DETECTIONS_FILE="${PROJECT_ROOT}/data/processed/ai_detections.csv"

if [[ -n "${INSIDE_DGX_CONTAINER:-}" ]]; then
  PYTHON_BIN="$(command -v python)"
  UVICORN_BIN="$(command -v uvicorn)"
else
  PYTHON_BIN="${PROJECT_ROOT}/venv/bin/python"
  UVICORN_BIN="${PROJECT_ROOT}/venv/bin/uvicorn"
  if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "[start.sh] ERROR: virtual environment Python not found at ${PYTHON_BIN}" >&2
    exit 1
  fi
fi

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

if [[ -z "${INSIDE_DGX_CONTAINER:-}" && ! -x "${PYTHON_BIN}" ]]; then
  echo "[start.sh] ERROR: virtual environment Python not found at ${PYTHON_BIN}" >&2
  exit 1
fi

# Ensure baseline data is present (download if missing)
PIPELINE_REQUIRED=0

if [[ ! -f "${POLES_CSV}" ]]; then
  echo "[start.sh] Historical pole inventory missing – downloading real OSM poles…"
  if PYTHONPATH="${PROJECT_ROOT}/src" "${PYTHON_BIN}" "${PROJECT_ROOT}/src/utils/get_osm_poles.py"; then
    PIPELINE_REQUIRED=1
  else
    echo "[start.sh] ERROR: Failed to download OSM pole data." >&2
    exit 1
  fi
else
  ROW_COUNT="$("${PYTHON_BIN}" - <<'PY' "${POLES_CSV}"
import sys
from pathlib import Path
import pandas as pd

path = Path(sys.argv[1])
try:
    df = pd.read_csv(path)
    print(len(df))
except Exception:
    print(0)
PY
)"
  if [[ -z "${ROW_COUNT}" ]]; then
    ROW_COUNT=0
  fi
  if (( ROW_COUNT < 1000 )); then
    echo "[start.sh] Historical pole inventory has only ${ROW_COUNT} records; refreshing from OSM for complete dataset…"
    if PYTHONPATH="${PROJECT_ROOT}/src" "${PYTHON_BIN}" "${PROJECT_ROOT}/src/utils/get_osm_poles.py"; then
      PIPELINE_REQUIRED=1
    else
      echo "[start.sh] ERROR: Failed to refresh OSM pole data." >&2
      exit 1
    fi
  fi
fi

# Determine if processed outputs exist; trigger pipeline otherwise
if [[ ! -f "${VERIFIED_FILE}" || ! -f "${DETECTIONS_FILE}" ]]; then
  PIPELINE_REQUIRED=1
fi

RUN_PIPELINE_FLAG="${RUN_PIPELINE:-0}"
if [[ "${PIPELINE_REQUIRED}" == "1" ]]; then
  RUN_PIPELINE_FLAG="1"
  echo "[start.sh] Missing processed outputs detected – pipeline will run to regenerate data."
fi

mkdir -p "${LOG_DIR}"

echo "[start.sh] Stopping existing backend/frontend processes…"
pkill -f "uvicorn backend.app.main:app" 2>/dev/null || true
pkill -f "npm run dev" 2>/dev/null || true
pkill -f "[v]ite" 2>/dev/null || true
sleep 1

if [[ "${RUN_PIPELINE_FLAG}" == "1" ]]; then
  echo "[start.sh] RUN_PIPELINE_FLAG=1 => executing full data pipeline"

  imagery_available=0
  if compgen -G "${TILES_DIR}/*.tif" > /dev/null; then
    echo "[start.sh] NAIP tiles already present at ${TILES_DIR}; skipping download."
    imagery_available=1
  else
    echo "[start.sh] Downloading NAIP imagery tiles (max ${MAX_TILES})…"
    if ! PYTHONPATH="${PROJECT_ROOT}/backend" "${PYTHON_BIN}" "${PROJECT_ROOT}/src/utils/download_naip_pc.py" \
      --output-dir "${TILES_DIR}" \
      --no-mosaic \
      --max-tiles "${MAX_TILES}"
    then
      echo "[start.sh] WARNING: NAIP tile download failed; continuing with existing cached detections if available." >&2
    else
      imagery_available=1
    fi
  fi

  if [[ "${imagery_available}" == "1" ]]; then
    echo "[start.sh] Extracting pole crops from downloaded tiles…"
    PYTHONPATH="${PROJECT_ROOT}/backend" "${PYTHON_BIN}" "${PROJECT_ROOT}/src/utils/extract_pole_crops.py" \
      --imagery "${TILES_DIR}" \
      --poles "${POLES_CSV}" \
      --output "${PROJECT_ROOT}/data/processed/pole_training_dataset" \
      --crop-size 256 \
      --clean

    echo "[start.sh] Preparing YOLO dataset splits…"
    PYTHONPATH="${PROJECT_ROOT}/backend" "${PYTHON_BIN}" "${PROJECT_ROOT}/src/utils/prepare_yolo_dataset.py"

    echo "[start.sh] Clearing cached detections…"
    rm -f "${PROJECT_ROOT}/data/processed/ai_detections.csv" "${PROJECT_ROOT}/data/processed/ai_detections_metadata.json" || true
  else
    echo "[start.sh] Skipping crop extraction and cache reset; relying on existing detection outputs."
  fi

  echo "[start.sh] Running verification pipeline (run_pilot.py)…"
  PYTHONPATH="${PROJECT_ROOT}/backend" "${PYTHON_BIN}" "${PROJECT_ROOT}/run_pilot.py"
else
  echo "[start.sh] RUN_PIPELINE=${RUN_PIPELINE}. Skipping heavy data pipeline tasks."
  echo "[start.sh] Use the dashboard \"Refresh Pipeline\" button or rerun with RUN_PIPELINE=1 when data needs to be regenerated."
fi

echo "[start.sh] Starting backend on port ${BACKEND_PORT}…"
PYTHONPATH="${PROJECT_ROOT}/backend" "${UVICORN_BIN}" backend.app.main:app \
  --reload --host "0.0.0.0" --port "${BACKEND_PORT}" > "${LOG_DIR}/backend.log" 2>&1 &
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
HOST_ADDR="${HOST_LAN_IP:-localhost}"
echo "BACKEND_PORT=${BACKEND_PORT}" > "${LOG_DIR}/last_start_ports"
echo "FRONTEND_PORT=${FRONTEND_PORT}" >> "${LOG_DIR}/last_start_ports"
echo "[start.sh] Frontend available at http://${HOST_ADDR}:${FRONTEND_PORT}"
echo "[start.sh] Backend API docs at http://${HOST_ADDR}:${BACKEND_PORT}/api/docs"
