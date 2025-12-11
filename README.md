# PoleLocations Enterprise (PostGIS V3)

> **Status:** Enterprise Beta (PostGIS Native)
> **Last Updated:** December 2025
> **Architecture:** Modular Containerized Pipeline (NVIDIA GB10 Optimized)

## 🚨 CRITICAL RULE: USE DOCKER

**ALL backend commands, scripts, and python execution MUST be run inside the Docker containers.**

*   **GPU/Pipeline Work**: Execute inside `polelocations-gpu`
    ```bash
    docker exec -it polelocations-gpu /bin/bash
    ```
    ```
*   **Database Ops**: Execute inside `polevision-db`
*   **Web/API**: Execute inside `polevision-web` or `polevision-api`

**NEVER run python scripts directly on the host machine.** The host environment does NOT have the correct dependencies (GDAL, PyTorch-CUDA, PostGIS drivers).

## 🧠 AI Model Upgrade (YOLO11)

The system is currently transitioning from **YOLOv8** to **YOLO11 Large**.
*   **Default Behavior**: The system prioritizes the new YOLO11l checkpoint at `/workspace/models/checkpoints/yolo11l_pole_v1/weights/best.pt`.
*   **Fallback**: If the YOLO11 training is incomplete, it falls back to the legacy `pole_detector_real.pt` (YOLOv8).
*   **Training**: To regenerate the YOLO11 model, run:
    ```bash
    docker exec polelocations-gpu yolo detect train model=yolo11l.pt data=/workspace/data/processed/pole_training_dataset_512/dataset.yaml epochs=50 imgsz=512 batch=16 project=/workspace/models/checkpoints name=yolo11l_pole_v1 device=0
    ```

## 📖 System Overview

**PoleLocations Enterprise** is a high-throughput, AI-driven asset verification system designed to audit utility poles on a massive scale. It moves beyond legacy file-based processing to a robust **PostGIS-Centric Architecture**, where the database serves as the single source of truth for all pipeline state.

### Core Objectives
1.  **Ingest** aerial imagery (NAIP/GeoTIFF) and historical asset records (OSM/Utility Maps).
2.  **Detect** poles using YOLO11 and **Classify** defects (leaning, rust, vegetation) using OpenAI CLIP (Zero-Shot).
3.  **Enrich** detections with usage context (Height from DSM, Distance to Roads).
4.  **Fuse** data to create a "Golden Record" in PostGIS, flagging discrepancies for human review.

---

## 🏗 Architecture & Infrastructure

The system employs a strict "Orchestrator-Worker" pattern across four specialized Docker containers.

### 1. Database Service (`polevision-db`)
*   **Image**: `postgis/postgis:16-3.4`
*   **Role**: Persistent state machine & spatial engine.
*   **Port**: `5433` (Mapped to host to avoid conflicts).
*   **Schema**:
    *   `poles`: Master asset inventory (Point Geometry).
    *   `detections`: Raw AI outputs (transient).
    *   `tiles`: Imagery index and processing status.
    *   `jobs`: Pipeline orchestration tracking.

### 2. GPU Worker (`polelocations-gpu`)
*   **Image**: `nvcr.io/nvidia/pytorch:25.09-py3`
*   **Role**: Heavy Compute / Inference Engine.
*   **Network**: **Host Mode** (Direct access to `localhost:5433`).
*   **Mounts**: 
    *   Source Code: `/home/canderson/PoleLocations` -> `/workspace`
    *   Data: `/workspace/data` symlinked to `/data`
*   **Workload**: Runs `runner.py` to execute Detection (YOLO), Enrichment, and Fusion.

### 3. API Gateway (`polevision-api`)
*   **Image**: Python 3.11 (FastAPI)
*   **Role**: Lightweight REST API for the Frontend Dashboard.
*   **Port**: `8000`.
*   **Responsibility**: Queries `polevision-db` to serve GeoJSON assets and metrics. Does NOT run heavy inference.

### 4. Frontend (`polevision-web`)
*   **Image**: Node 20 (React/Vite)
*   **Role**: Interactive Operations Dashboard ("Ops Center").
*   **Port**: `5173`.

---

## 🚀 Quick Start / Operations

### 1. Start the Infrastructure
```bash
# Start DB, API, and Web
docker-compose -f docker-compose.enterprise.yml up -d
```

### 2. Run the Pipeline (The "Runner")
The `runner.py` script is the master orchestrator. It functions as a CLI to run one or all stages of the pipeline. **It must be executed inside the GPU container** to access PyTorch/CUDA resources.

```bash
# Execute the full end-to-end pipeline (Ingest -> Detect -> Enrich -> Fusion)
docker exec -e PYTHONPATH=/workspace:/workspace/backend-enterprise \
            -e DATABASE_URL=postgresql://pole_user:pole_secure_password@localhost:5433/polevision \
            polelocations-gpu python src/pipeline/runner.py
```

### 3. Continuous Mode (Daemon)
To run the pipeline in a loop (monitoring for new imagery):
```bash
docker exec ... polelocations-gpu python src/pipeline/runner.py --loop
```

### 4. One-Click Enterprise Run (Train + Detect + Fuse)
For a complete system test (Training YOLO11l -> Running Inference on 3 PA Counties -> Fusion), use the **Master Orchestrator**:

```bash
docker exec -e PYTHONPATH=/workspace:/workspace/backend-enterprise \
            -e DATABASE_URL=postgresql://pole_user:pole_secure_password@localhost:5433/polevision \
            polelocations-gpu python /workspace/run_full_enterprise_pipeline.py
```

**What this does:**
1.  **Traings YOLO11l**: Runs 50 epochs on the `pole_training_dataset_512`.
2.  **Inference**: Runs detection on **Dauphin**, **York**, and **Cumberland** counties.
3.  **Enrichment**: Applies PASDA Roads & USGS Lidar filters.
4.  **Fusion**: Validates against FAA Obstacles & OpenInfraMap.

---

## 🧠 Pipeline Stages (Deep Dive)

The logic is split into modular services under `src/pipeline/`:

### Stage A: Ingestion (`ingest_imagery.py`)
- Scans `/data/imagery/naip_tiles` for GeoTIFFs.
- Extracts Bounding Boxes (EPSG:4326).
- **Output**: Inserts rows into the `tiles` table (Status: `Pending`).

### Stage B: Detection (`detect.py`)
- Queries `tiles` where status=`Pending`.
- **Model**: YOLO11l (Object Detection) + CLIP ViT-L/14 (Classification).
- **Logic**: Sliding window inference (512px stride).
- **Output**: Writes millions of rows to `detections` table.
- **Hardware**: Auto-detects CUDA. Falls back to CPU if NVIDIA drivers are unavailable/mismatched.

### Stage C: Enrichment (`enrich.py`)
- **Input**: Raw `detections` lacking context.
- **Logic**:
    - **DSM**: Samples Height Above Ground from Digital Surface Models.
    - **Roads**: Calculates `ST_Distance` to nearest road centerline (using PostGIS Topology).
- **Output**: Updates `height_ag_m` and `road_distance_m` columns.

### Stage D: Fusion (`fusion.py`)
- **Input**: Enriched detections.
- **Logic**:
    - **Match**: `ST_DWithin(detection, pole, 10m)`
    - **Update**: If match found, marks pole `Verified`.
    - **Create**: If **High Confidence** + **Near Road** + **No Match** -> Creates NEW `Flagged` pole.
- **Output**: Writes final assets to `poles` table.

---

## 🛠 Developer Setup & Troubleshooting

### Database Connections
*   **From Host**: `postgresql://pole_user:pole_secure_password@localhost:5433/polevision`
*   **From API Container**: `postresql://pole_user:pole_secure_password@polevision-db:5432/polevision`
*   **From GPU Container (Host Network)**: `postgresql://pole_user:pole_secure_password@localhost:5433/polevision`

### Common Issues

**1. "NVML: Unknown Error" / GPU not used**
*   **Cause**: Host NVIDIA driver version mismatch with container runtime.
*   **Fix**: Restart the GPU container or reboot the host instance. The pipeline will automatically fallback to CPU (slower but functional).

**2. "ModuleNotFoundError: No module named 'database'"**
*   **Cause**: `PYTHONPATH` not set correcty.
*   **Fix**: Ensure `PYTHONPATH=/workspace:/workspace/backend-enterprise` is passed in the `docker exec` command.

**3. Database Schema Missing**
*   **Fix**: Re-run the init script:
    ```bash
    docker exec -e DATABASE_URL=... polelocations-gpu python /workspace/backend-enterprise/init_db.py
    ```

---

## 🌍 Enterprise Data Sources (Augmented)

To ensure maximum accuracy (robustness), the system integrates a multi-layered data verification strategy using **Open Source & Federal Data**:

| Source | Type | Role | Implementation |
| :--- | :--- | :--- | :--- |
| **NAIP** | Imagery (Raster) | **Detection**. High-res (1m) aerial photography. | `ingest_imagery.py` (Local GeoTIFFs) |
| **USGS 3DEP** | DSM (Raster) | **False Positive Filtering**. Check Height Above Ground (HAG). | `src/fusion/context_filters.py` |
| **OpenStreetMap** | Vector | **Context**. Road proximity & filter. | `src/fusion/context_filters.py` |
| **FAA Obstacles** | Data (CSV) | **Ground Truth**. Validates transmission towers >200ft & airport assets. | `src/ingestion/connectors/faa_obstacles.py` |
| **PASDA Roads** | Vector (Shapefile) | **Precision**. Superior road centerlines for Pennsylvania. | `src/ingestion/connectors/pasda_roads.py` |
| **OpenInfraMap** | Vector (WFS) | **Grid Context**. Maps high-voltage transmission lines. | `src/ingestion/connectors/openinframap.py` |
| **Mapillary** | Street Imagery | **Defect Verification**. Visual check for rust/leaning. | `src/ingestion/connectors/mapillary.py` |
| **USGS Lidar** | Point Cloud (LAZ) | **Verticality**. Confirms "Pole vs Tree" signature. | `src/ingestion/connectors/usgs_lidar.py` |

All connectors are modularly located in `src/ingestion/connectors/`. The system gracefully degrades if optional keys (e.g., Mapillary) are missing.

---

## 📂 Directory Structure

```
/home/canderson/PoleLocations/
├── backend-enterprise/       # API & DB Logic
│   ├── models.py             # SQLModel Definitions (The Source of Truth)
│   ├── database.py           # Engine Config
│   └── routers/              # FastAPI Endpoints
├── src/                      # Shared Python Core
│   ├── pipeline/             # NEW: Pipeline Microservices
│   │   ├── runner.py         # Entry Point
│   │   ├── detect.py
│   │   └── ...
│   └── detection/            # YOLO/CLIP Model Wrappers
├── docker-compose.enterprise.yml # Services Definition
└── README.md                 # This file
```
