# PoleVision AI

**AI-driven utility pole verification at scale** — automates FCC-mandated infrastructure inspections using satellite imagery, street-level photos, and geospatial sensor fusion.

Built with YOLO11l, CLIP, PostGIS, FastAPI, React, and Docker (NVIDIA GPU-accelerated).

---

## Overview

PoleVision AI automates the verification of 1M+ utility poles across the East Coast by fusing multiple data sources through a multi-modal AI pipeline. It reduces manual pole inspection costs from **$3-6/pole to $0.01-0.05/pole**, automating 70-90% of FCC 5-year compliance verifications.

**Pipeline:**

1. **Ingest** — Aerial imagery (NAIP GeoTIFF), street-level photos (Mapillary), and asset records (OSM, FAA, PASDA)
2. **Detect** — YOLO11l identifies poles in satellite imagery with sub-meter accuracy
3. **Classify** — OpenAI CLIP classifies defects (leaning, rust, vegetation encroachment)
4. **Enrich** — LiDAR height verification (USGS 3DEP), road proximity filtering (PASDA)
5. **Fuse** — Sensor fusion creates "Golden Records" in PostGIS with multi-source confirmation
6. **Verify** — "String of Pearls" algorithm infers missing poles from network spacing topology

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                    POLEVISION AI PIPELINE                       │
│                                                                │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────┐     │
│  │  React   │◄───│ FastAPI  │◄───│    PostGIS 16        │     │
│  │  Ops     │    │   API    │    │  (Single Source of    │     │
│  │ Center   │    │ Gateway  │    │   Truth for State)    │     │
│  └──────────┘    └──────────┘    └──────────┬───────────┘     │
│                                              │                 │
│                                              ▼                 │
│                                  ┌──────────────────────┐     │
│                                  │    GPU Worker         │     │
│                                  │  YOLO11l Detection    │     │
│                                  │  CLIP Classification  │     │
│                                  │  Sensor Fusion Engine │     │
│                                  └──────────────────────┘     │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                    DATA SOURCES                           │ │
│  │  NAIP Satellite (1m) | Mapillary Street | USGS LiDAR    │ │
│  │  FAA Obstacles | PASDA Roads | OpenInfraMap Grid         │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Detection** | YOLO11l (satellite), YOLO11l (street-level) — Dual-Expert Architecture |
| **Classification** | OpenAI CLIP ViT-L/14 (defect classification) |
| **Auto-Labeling** | Grounding DINO (zero-shot training data generation) |
| **Geospatial** | PostGIS 16 + GeoAlchemy2, GDAL/Rasterio, GeoPandas, Shapely |
| **Backend** | FastAPI (Python 3.11), SQLModel ORM |
| **Frontend** | React 19, TypeScript, Vite, TailwindCSS, Leaflet/Mapbox |
| **Infrastructure** | Docker Compose (4 containers), NVIDIA GPU, host-mode networking |
| **Data Sources** | NAIP, Mapillary, USGS 3DEP LiDAR, FAA, PASDA, OpenInfraMap |

---

## Key Innovations

### Dual-Expert Model Architecture
Two specialized YOLO11l models optimized for different perspectives:
- **Satellite Expert** — Top-down detection of poles as small dots and shadows in 1m/pixel NAIP imagery
- **Street Expert** — Ego-centric detection of vertical wooden structures and transformers in Mapillary photos

The `PoleDetector` auto-selects the correct expert based on input source.

### Sensor Fusion via Ray-Casting
When the satellite expert detects a pole from above, the fusion engine:
1. Queries nearby Mapillary images (within 500m)
2. Projects a bearing ray from each camera position
3. If the ray intersects the satellite detection point, the pole is marked **Confirmed**
4. Downloads the actual street-level image and runs the Street Expert for visual confirmation

### "String of Pearls" Gap Inference
Utility poles follow network topology — they are rarely isolated:
- Analyzes confirmed detections for spatial regularity (typically 30-50m spacing)
- Detects "pearl gaps" (e.g., a 90m gap implies a missing pole at the midpoint)
- Triggers targeted high-sensitivity re-scans at inferred locations

### Zero-Shot Auto-Labeling Pipeline
Solves the training data bottleneck without manual annotation:
- **Satellite Mining** — Grounding DINO scans PASDA tiles at ~1.1 poles/second
- **Street Mining** — Deep-fetches Mapillary imagery with positive/negative prompt filtering
- Automatic generation of thousands of YOLO training samples per hour

---

## Unified Pipeline

The entire detection workflow runs as a single atomic operation:

| Stage | Service | Description |
|-------|---------|------------|
| **Inference** | YOLO11l + CLIP | Detect poles in NAIP tiles, classify defects |
| **Enrichment** | GDAL + 3DEP | Add height-above-ground from LiDAR, road distance from PASDA |
| **Filtration** | Context Filters | Drop detections in water bodies or deep forests |
| **Fusion** | FusionEngine | Match to existing records (`ST_DWithin 10m`), create or verify |
| **Repair** | Pearl Stringer | Infer missing poles, trigger targeted re-scans |

Each tile processes through all stages and commits results to PostGIS immediately.

---

## Data Sources

| Source | Resolution | Role |
|--------|-----------|------|
| **NAIP** | 1m/pixel aerial | Primary detection grid |
| **Mapillary** | Street-level photos | Sensor fusion verification |
| **USGS 3DEP** | LiDAR DSM | Height-above-ground validation |
| **PASDA** | Road centerlines | Context filtering (road proximity) |
| **FAA Obstacles** | Tower registry | Ground truth for structures >200ft |
| **OpenInfraMap** | Transmission lines | Grid backbone context |

---

## Project Structure

```
├── backend-enterprise/
│   ├── main.py                  # FastAPI application
│   ├── models.py                # SQLModel schema (Pole, Detection, Job)
│   ├── database.py              # PostGIS connection config
│   └── routers/                 # API endpoints (poles, metrics, pipeline, ops)
├── frontend-enterprise/
│   └── src/
│       ├── pages/
│       │   ├── LiveMap.tsx      # Leaflet map with Mapillary integration
│       │   └── LiveMap3D.tsx    # 3D visualization
│       └── components/          # Dashboard widgets, intelligence cards
├── src/
│   ├── pipeline/
│   │   ├── detect.py            # Unified detection service (Detect/Enrich/Fuse)
│   │   ├── fusion_engine.py     # PostGIS spatial matching + confidence scoring
│   │   ├── runner.py            # Batch job orchestrator
│   │   └── manager.py           # Job lifecycle management
│   ├── detection/
│   │   ├── pole_detector.py     # YOLO11l + CLIP dual-expert wrapper
│   │   └── threshold_sweeper.py # Confidence calibration
│   ├── fusion/
│   │   ├── pearl_stringer.py    # "String of Pearls" gap inference
│   │   ├── correlator.py        # Ray-casting sensor fusion
│   │   └── context_filters.py   # Water/forest/road proximity masking
│   ├── ingestion/
│   │   └── connectors/          # Data source adapters (FAA, PASDA, Mapillary)
│   └── training/
│       ├── smart_miner_autodistill.py  # Grounding DINO auto-labeling (satellite)
│       └── smart_street_miner.py       # Mapillary mining + hard negatives
├── docker-compose.enterprise.yml       # 4-container orchestration
└── .env.example                        # Required environment variables
```

---

## Getting Started

### Prerequisites

- Docker and Docker Compose
- NVIDIA GPU with CUDA support
- NVIDIA Container Toolkit installed

### Setup

```bash
# Clone the repository
git clone https://github.com/cameronsaddress/PoleLocations.git
cd PoleLocations

# Configure environment
cp .env.example .env
# Edit .env with your API keys (Mapillary, OpenRouter)

# Start all services
docker compose -f docker-compose.enterprise.yml up -d

# Run the unified pipeline
docker exec polevision-gpu python /workspace/run_full_enterprise_pipeline.py
```

### Access Points

| Service | URL |
|---------|-----|
| Operations Dashboard | `http://localhost:5173` |
| API Documentation | `http://localhost:8000/docs` |
| Database | `localhost:5433` (PostGIS) |

---

## Infrastructure

**Docker Services (4 containers):**

| Container | Role | Configuration |
|-----------|------|--------------|
| `polevision-db` | PostGIS 16 + spatial engine | Persistent state, healthcheck |
| `polevision-gpu` | GPU compute (YOLO, CLIP, fusion) | Host networking, full GPU access |
| `polevision-api` | FastAPI REST gateway | Serves GeoJSON, metrics, job control |
| `polevision-web` | React operations dashboard | Leaflet maps, intelligence cards |

**GPU Configuration:**
- NVIDIA GPU with full device access for YOLO11l and CLIP inference
- Host-mode networking for direct PostGIS access from GPU container
- Optimized for NVIDIA Grace Blackwell (GB10) infrastructure

---

## License

MIT
