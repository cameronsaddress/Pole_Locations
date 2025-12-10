# PoleLocations - AI-Driven Utility Pole Verification System (Enterprise Edition)

> **Source Repository:** https://github.com/cameronsaddress/PoleLocations
> **Status:** Enterprise Beta - NVIDIA GB10 Optimized

## Project Overview

Verizon maintains over one million utility poles on the East Coast that require location verification (x-y coordinates) every 5 years per FCC guidelines. This system automates the verification process using AI, Python, aerial/satellite imagery, and historical technician reports to eliminate known good pole locations and surface questionable poles for human review.

**Enterprise Update (Dec 2025):** The system has been upgraded to a **Dual-Pipeline Architecture** specifically optimized for **NVIDIA GB10 Tensor Core GPUs (128GB VRAM)**, enabling the use of massive state-of-the-art vision models (ViT-Huge, YOLO11x) that were previously computationally prohibitive.

## Enterprise Features

### 1. Dual-Pipeline AI Architecture
The system now operates two distinct, specialized AI pipelines to maximize accuracy:

*   **Detector Pipeline (YOLO11x)**:
    *   **Model**: YOLO11 X-Large (SOTA 2025).
    *   **Optimization**: Fine-tuned on GB10 hardware for maximum mAP (mean Average Precision).
    *   **Role**: Locates poles in high-resolution aerial imagery with extreme precision, handling occlusions (trees, shadows).

*   **Classifier Pipeline (CLIP ViT-Huge)**:
    *   **Model**: `laion/CLIP-ViT-H-14` (2.5B Parameters).
    *   **Hardware Acceleration**: severe lean, vegetation encroachment, and equipment damage.
    *   **Performance**: Near-human zero-shot accuracy, leveraging the 128GB unified memory of the GB10 to run full uncompressed models.

### 2. Closed-Loop Hyperparameter Tuning (Grok-4.1)
We have moved beyond static configuration to an autonomous **"Human-in-the-Loop" Tuning Engine**:

*   **Workflow**: The system executes a "Trial" (Validation Run) -> Broadcasts Results to Grok-4.1 -> Grok analyzes convergence/F1-scores -> Grok recommends structured config changes -> System effectively re-configures itself and re-runs.
*   **Dynamic Evolution**: The "Parameter Evolution" timeline in the Training Dashboard visualizes this process in real-time, showing how the AI adapts learning rates, NMS thresholds, and confidence levels to optimize for the specific dataset.

### 3. Incident Command Center
A new React-based "Ops Center" provides real-time situational awareness:
*   **Live Map**: Real-time visualization of verified poles, defects, and technician dispatch.
*   **Telemetry**: Real-time GPU (GB10) utilization, VRAM usage, and power draw monitoring.
*   **Revenue Engine**: Identification of "Ghost Attachments" (unbilled unauthorized attachments) for revenue recovery.

## Technical Approach

### High-Level Architecture

The solution employs a modular Python pipeline with four core stages:

1.  **Data Ingestion Layer**: Collect and preprocess pole records from multiple sources
2.  **Dual AI Layer**:
    *   **Detection**: YOLO11x for bounding box regression.
    *   **Classification**: CLIP ViT-H-14 for semantic understanding.
3.  **Fusion & Verification Layer**: Cross-validate detections against historical data with confidence scoring
4.  **Command Center Output**: Live "Ops Center" dashboard for real-time network health monitoring

### Workflow

```
[Data Inputs] → Preprocess → AI Detection (YOLO11x) → Zero-Shot Classification (ViT-H-14) →
Fusion Matching (Spatial + Scoring) → Operational Status Assignment →
[Outputs: Command Center / Critical Alerts]
     ↑
Autonomous Hyperparameter Tuning (Grok-4.1 Loop)
```

### Technology Stack

*   **Hardware**: **NVIDIA GB10 Tensor Core GPUs (128GB VRAM)**
*   **Geospatial Processing**: Pandas, GeoPandas, Rasterio, GDAL
*   **AI/Computer Vision**:
    *   **YOLO11x** (Object Detection)
    *   **CLIP ViT-H-14** (Zero-Shot Defect Classification)
    *   **PyTorch** (Inference Engine)
*   **LLM Integration**: **Grok-4.1** (via OpenRouter) for autonomous tuning
*   **Web App**: FastAPI backend + React (Vite) frontend (Enterprise Dashboard)
*   **Cloud Infrastructure**: AWS/Azure for batch processing with Dask parallelization

## Cost Analysis

### Per-Pole Cost Breakdown ($0.01-0.05/pole target)

| Category | Cost | Details |
|----------|------|---------|
| Imagery Acquisition | $0-0.02/pole | NAIP free; commercial satellite $10-20/km² for subsets |
| Cloud GPU Computing | $0.005-0.02/pole | YOLOv8 inference on H100/A100 GPUs |
| Data Processing | $0.002-0.005/pole | Storage, OCR, model fine-tuning |
| Human Review (10-30%) | $0.003-0.01/pole | Dashboard-assisted review |
| **Total Savings** | **-$3-6/pole offset** | 70-90% automation = $2.1M-5.4M/year saved |

## Implementation Plan

### Phase 1: Pilot (10K poles, 2-4 weeks)
1.  Data collection: Obtain sample reports + imagery for East Coast subset
2.  Preprocessing: Clean, standardize CRS, create buffer zones
3.  Model training: Fine-tune YOLOv8 on 1K labeled pole images
4.  Detection: Run inference on pilot imagery tiles
5.  Fusion: Match detections to reports, generate classifications
6.  Review: Build Streamlit dashboard, validate accuracy

### Phase 2: Scale (1M poles, 2-3 months)
1.  Batch processing: Deploy on cloud GPU cluster (100K poles/day)
2.  Multi-source integration: Expand imagery providers, parse all reports
3.  Feedback loops: Implement retraining pipeline from human reviews
4.  Integration: Connect to Verizon third-party payment system

### Phase 3: Production (Ongoing)
1.  Quarterly retraining: Improve model on new labels
2.  Metrics tracking: Precision/recall validation, <5% false positive target
3.  Cost optimization: Spot instances, API tier management

## Next Steps

1.  **Configure API Keys**: Ensure `OPENROUTER_API_KEY` is set in the Enterprise Settings for Grok-4.1 integration.
2.  **Model Download**: The system will automatically attempt to download `ViT-H-14` if not present (approx 5GB).
3.  **Run Pilot**: Execute `run_pilot.py` to process the sample tile set (Dauphin/Cumberland/York).
4.  **Launch Dashboard**: `npm run dev` in `frontend-enterprise/` and `uvicorn main:app` in `backend-enterprise/`.

### Mapillary Labeling Workflow

```bash
# 1. Harvest thumbnails (requires MAPILLARY_TOKEN env)
PYTHONPATH=src ./venv/bin/python src/utils/harvest_mapillary.py --limit 300

# 2. Launch the labeling app (one-click review per frame)
## Option A: from the PoleVision AI dashboard (top-right “Mapillary Labeler” button)
## Option B: standalone
streamlit run dashboard/mapillary_labeler.py

# 3. (Optional) Add notes in the app; labels persist back to the queue CSV automatically.

# 4. Ingest labeled thumbnails into the YOLO dataset
PYTHONPATH=src ./venv/bin/python src/utils/process_mapillary_labels.py

# 5. Rebuild train/val splits and retrain
PYTHONPATH=src ./venv/bin/python src/utils/prepare_yolo_dataset.py
PYTHONPATH=src ./venv/bin/python - <<'PY'
from pathlib import Path
from detection.pole_detector import PoleDetector
from config import PROCESSED_DATA_DIR, MODELS_DIR
detector = PoleDetector(model_path=None)
best = detector.train(
    data_yaml=PROCESSED_DATA_DIR / 'pole_training_dataset' / 'dataset.yaml',
    epochs=50,
    batch_size=16,
    img_size=256,
    patience=10,
)
print('Best weights saved to', best)
PY

# 6. Re-run the pilot pipeline
# IMPORTANT: run heavy inference inside the Docker GPU container so PyTorch keeps CUDA enabled.
# Running the command from the host venv will fall back to CPU-only builds.
docker exec -it polelocations-gpu bash -lc 'cd /workspace && PYTHONPATH=src python run_pilot.py'
```

### Diff Viewer
- Launch the optional Streamlit diff viewer: `streamlit run dashboard/diff_app.py`
- Configure the React frontend with `VITE_DIFF_VIEWER_URL` (defaults to `http://localhost:8501`).

### Monitoring Active Training
Keep a dedicated terminal pinned while YOLO training is running so you can watch every epoch update. Launch the command below from the host; it polls the container every five seconds and prints the full header plus the most recent metrics row from `results.csv`.

```bash
watch -n 5 "docker exec polelocations-gpu bash -lc \"python - <<'PY'
import csv
import datetime as dt
from pathlib import Path

TOTAL_EPOCHS = 220
csv_path = Path('/workspace/models/pole_detector_v6/results.csv')
if not csv_path.exists():
    print('results.csv not found yet')
    raise SystemExit

rows = list(csv.reader(csv_path.open()))
if len(rows) <= 1:
    print('waiting for training epochs to log...')
    raise SystemExit

header, *records = rows
last = records[-1]

try:
    epoch = int(float(last[0]))
    elapsed = float(last[1])
except ValueError:
    print('latest row incomplete...')
    raise SystemExit

remaining = max(TOTAL_EPOCHS - epoch, 0)
avg_epoch = elapsed / epoch if epoch else 0.0
eta_seconds = remaining * avg_epoch

fmt = lambda seconds: str(dt.timedelta(seconds=int(seconds)))

print(f'Epoch {epoch} / {TOTAL_EPOCHS}')
print(f'Elapsed: {fmt(elapsed)} | Avg/Epoch: {avg_epoch:.1f}s | Remaining epochs: {remaining}')
print(f'ETA to finish: {fmt(eta_seconds)}')
print('Last metrics row:')
print(','.join(header))
print(','.join(last))
PY\""
```

### Multi-County Data Sync
Automate fresh data pulls (OSM poles, NAIP tiles via Microsoft Planetary Computer, PEMA orthophotos, USGS 3DEP DSM, and Mapillary placeholders) for adjacent counties with:

```bash
venv/bin/python src/utils/sync_multi_source_data.py --areas dauphin_pa,cumberland_pa,york_pa --naip-max-tiles 2 --pema-tile-span 0.05 --dsm-limit 5 --skip-mapillary
```

This seeds:
- OSM pole CSVs under `data/raw/osm_poles_multi/`
- County-specific NAIP tiles in `data/imagery/naip_multi_county/<slug>/`
- PEMA orthophotos in `data/imagery/pema_tiles_multi/<slug>/`
- 3DEP DSM tiles in `data/processed/3dep_dsm_multi/<slug>/`
- Mapillary staging folders at `data/raw/mapillary_multi/<slug>/` (add a `MAPILLARY_TOKEN` and rerun without `--skip-mapillary` to fetch thumbnails/metadata).

## Technical Proposal Summary

This AI-driven automation positions Verizon at the forefront of utility infrastructure management by:
- **Reducing manual errors** through multi-source validation exceeding single-method audits
- **Accelerating compliance** with FCC requirements via continuous monitoring
- **Optimizing costs** through intelligent triage of inspection resources
- **Scaling efficiently** via cloud-native, GIS-compliant architecture
- **Improving over time** through human-in-the-loop feedback

The system processes 1M poles in weeks versus years manually, with proven AI techniques (YOLO11x on aerial imagery achieving 85-95% precision) adapted for utility-specific challenges like occlusions and coordinate precision.

---

**Contact**: AI Automation Team
**Date**: December 10, 2025
**Status**: Enterprise Beta - Awaiting Production Rollout
