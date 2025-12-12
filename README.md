# PoleLocations Enterprise (PostGIS V3)

> **Status:** Enterprise Beta (Unified Pipeline)
> **Last Updated:** December 2025
> **Architecture:** Modular Containerized Pipeline (NVIDIA GB10 Optimized)

## 🚨 CRITICAL RULES: ENTERPRISE PROTOCOLS

1.  **ALWAYS USE DOCKER CONTAINERS**: 
    *   **GPU/Pipeline Work**: Execute inside `polevision-gpu`.
      ```bash
      docker exec -it polevision-gpu /bin/bash
      ```
    *   **Database Ops**: Execute inside `polevision-db`.
    *   **Web/API**: Execute inside `polevision-web` or `polevision-api`.

2.  **NEVER RUN ON HOST**: 
    *   Do NOT run python scripts (`main.py`, `detect.py`) directly on the host machine. The host lacks critical dependencies (GDAL, PostGIS drivers, PyTorch-CUDA) which are isolated within the containers.

3.  **NO MOCK DATA**: 
    *   This system is connected to live production databases (`polevision`, `poles` table) and processes real satellite imagery (`NAIP`). Do not introduce mock data unless explicitly running a unit test suite.

4.  **STRICT PATHs**:
    *   Always use absolute paths found within the container mapping (e.g., `/workspace/data/...`). Do not use relative paths like `../data`.

---

## 📖 System Overview

**PoleLocations Enterprise** is a high-throughput, AI-driven asset verification system designed to audit utility poles on a massive scale. It moves beyond legacy file-based processing to a robust **PostGIS-Centric Architecture**, where the database serves as the single source of truth for all pipeline state.

### Core Objectives
1.  **Ingest** aerial imagery (NAIP/GeoTIFF) and historical asset records (OSM/Utility Maps).
2.  **Unified Detection Service**: A single atomic operation that:
    *   **Detects** poles using YOLO11l.
    *   **Classifies** defects (leaning, rust, vegetation) using OpenAI CLIP.
    *   **Enriches** detections with context (Height from DSM, Distance to Roads).
    *   **Fuses** data to create a "Golden Record" in PostGIS immediately.

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

### 2. GPU Worker (`polevision-gpu`)
*   **Image**: `nvcr.io/nvidia/pytorch:25.09-py3`
*   **Role**: Unified Compute Engine.
*   **Network**: **Host Mode** (Direct access to `localhost:5433`).
*   **Mounts**: `/workspace` (Code), `/data` (Imagery).
*   **Workload**: Runs the **Unified Detection Service** (`detect.py`) which handles Inference -> Enrichment -> Fusion.

### 3. API Gateway (`polevision-api`)
*   **Image**: Python 3.11 (FastAPI)
*   **Role**: Lightweight REST API for the Frontend Dashboard.
*   **Port**: `8000`.
*   **Responsibility**: Queries `polevision-db` to serve GeoJSON assets and metrics. 

### 4. Frontend (`polevision-web`)
*   **Image**: Node 20 (React/Vite)
*   **Role**: Interactive Operations Dashboard ("Ops Center").
*   **Port**: `5173`.

---

## 🚀 Quick Start / Operations

### 1. Start the Infrastructure
```bash
# Start DB, API, Web, and GPU Worker
docker compose -f docker-compose.enterprise.yml up -d
```

### 2. Run the Unified Pipeline (The "Master Orchestrator")
The `run_full_enterprise_pipeline.py` script is the certified entry point. It handles Training (optional), Ingestion, and the full Unified Detection Service.

```bash
docker exec -e PYTHONPATH=/workspace:/workspace/backend-enterprise \
            -e DATABASE_URL=postgresql://pole_user:pole_secure_password@localhost:5433/polevision \
            polevision-gpu python /workspace/run_full_enterprise_pipeline.py
```

**What this does:**
1.  **Train (Optional)**: Trains YOLO11l on the latest dataset.
2.  **Ingest**: Scans `/data/imagery` for new tiles.
3.  **Detect & Enrich & Fuse**: 
    *   Runs YOLO inference.
    *   Enriches results with Road/DSM data *in-memory*.
    *   Commits valid poles to the DB immediately.

### 3. Continuous Mode (Daemon)
To run the detection service in a loop (monitoring for new imagery):
```bash
docker exec ... polevision-gpu python src/pipeline/runner.py --loop
```

### 4. GPU Model Upgrade (YOLO11)
The system uses **YOLO11 Large**.
*   **Default Behavior**: Loads best weights from `/workspace/models/checkpoints/yolo11l_pole_v1/weights/best.pt`.
*   **Retraining**: Handled automatically by the Master Orchestrator (step 2) unless `--skip-train` is passed.

---

## 🧠 Unified Pipeline Logic (Deep Dive)

The legacy disjointed scripts have been unified into a single service: `src/pipeline/detect.py`.

### Step A: Inference
*   **Model**: YOLO11l + CLIP ViT-L/14.
*   **Input**: 1km² NAIP Tile.
*   **Output**: Stream of raw detections.

### Step B: Contextual Enrichment (In-Memory)
*   **Roads**: Uses `PASDA` or OSM spatial index to calculate `road_distance_m`.
*   **Height**: Samples 3DEP LiDAR DSM for `height_ag_m` (Height Above Ground).
*   **Filtration**: Drops detection points located in water bodies or deep forests (low confidence).

### Step C: Real-Time Fusion (`FusionEngine`)
*   **The Engine**: `src/pipeline/fusion_engine.py`
*   **Logic**:
    *   **Match**: `ST_DWithin(detection, pole, 10m)`
    *   **Update**: If match found, marks pole `Verified`.
    *   **Create**: If it's a **High Confidence** + **Valid Context** prediction -> Creates NEW `Flagged` pole.
*   **Outcome**: The `poles` table is updated **instantly** after each tile is processed.

---

## 🌟 Data Sources

To ensure maximum accuracy, the system integrates a multi-layered data verification strategy:

| Source | Role | Implementation |
| :--- | :--- | :--- |
| **NAIP** | **Detection**. High-res (1m) aerial photography. | `ingest_imagery.py` |
| **USGS 3DEP** | **Enrichment**. Height Above Ground (HAG) verification. | `src/fusion/context_filters.py` |
| **PASDA Roads** | **Context**. Precision road centerlines. | `src/fusion/context_filters.py` |
| **FAA Obstacles** | **Validation**. Ground truth for towers >200ft. | `src/ingestion/connectors/faa_obstacles.py` |
| **OpenInfraMap** | **Grid Context**. High-voltage transmission lines. | `src/ingestion/connectors/openinframap.py` |

---

## 📂 Directory Structure

```
/home/canderson/PoleLocations/
├── backend-enterprise/       # API & DB Logic
│   ├── models.py             # SQLModel Definitions (The Source of Truth)
│   ├── database.py           # Engine Config
│   └── routers/              # FastAPI Endpoints
├── src/                      # Shared Python Core
│   ├── pipeline/             # Pipeline Microservices
│   │   ├── runner.py         # Loop Runner
│   │   ├── detect.py         # UNIFIED Service (Detect/Enrich/Fuse)
│   │   └── fusion_engine.py  # Fusion Logic Class
│   └── detection/            # YOLO/CLIP Model Wrappers
├── docker-compose.enterprise.yml # Services Definition
└── README.md                 # This file
```
