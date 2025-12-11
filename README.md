# PoleLocations Enterprise (PostGIS V3)

> **Status:** Enterprise Beta (PostGIS Native)
> **Last Updated:** December 2025
> **Architecture:** Modular Containerized Pipeline (NVIDIA GB10 Optimized)

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
