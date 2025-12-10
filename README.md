# PoleLocations - AI-Driven Utility Pole Verification System

> **Source Repository:** https://github.com/cameronsaddress/PoleLocations

## Project Overview

Verizon maintains over one million utility poles on the East Coast that require location verification (x-y coordinates) every 5 years per FCC guidelines. This system automates the verification process using AI, Python, aerial/satellite imagery, and historical technician reports to eliminate known good pole locations and surface questionable poles for human review.

## Business Problem

- **Scale**: 1M+ poles across East Coast requiring 5-year verification cycles
- **Current Cost**: $3-6 per pole via third-party inspections ($3M-6M annually)
- **Goal**: Automate 70-90% of verifications, reducing costs to $0.01-0.05 per pole
- **Compliance**: Align with FCC audit requirements and Verizon's third-party payment program

## Technical Approach

### High-Level Architecture

The solution employs a modular Python pipeline with four core stages:

1. **Data Ingestion Layer**: Collect and preprocess pole records from multiple sources
2. **AI Detection Layer**: Use computer vision (YOLOv8 + CLIP) to detect poles and classify specific defects (Lean, Vegetation, Damage)
3. **Fusion & Verification Layer**: Cross-validate detections against historical data with confidence scoring
4. **Command Center Output**: Live "Ops Center" dashboard for real-time network health monitoring

### Data Sources

- **Historical Technician Reports**: CSV/Excel with pole_id, lat/lon, inspection_date, status
- **Satellite/Aerial Imagery**: High-res (≤30cm/pixel) from:
  - USGS NAIP (free, public domain, 1m resolution)
  - Maxar WorldView or Planet Labs (commercial, <30cm VHR)
  - Proprietary UAV/drone data
- **GIS Database**: Verizon's pole inventory shapefiles

### Workflow

```
[Data Inputs] → Preprocess → AI Detection (YOLOv8) → Zero-Shot Classification (CLIP) →
Fusion Matching (Spatial + Scoring) → Operational Status Assignment →
[Outputs: Command Center / Critical Alerts]
     ↑
Human Feedback Loop (Retraining)
```

### Defect Classification Logic (Real Intelligence)

The system now uses **Zero-Shot CLIP Classification** to identify specific high-value defects:

- **Severe Lean**: Pole listing > 10 degrees (Structural Risk)
- **Vegetation Encroachment**: Heavy canopy coverage (Fire/Outage Risk)
- **Equipment Damage**: Broken crossarms or insulators (Maintenance Priority)
- **Rusted Transformer**: Visible corrosion (Asset Lifecycle)
- **Bird Nest**: Nesting material on structure (Environmental/Fire Risk)
- **Verified Good**: Clean, vertical pole with clear clearance

### Confidence Scoring

Weighted algorithm combines multiple factors:
- 40% imagery detection confidence
- 30% report recency (prioritize <5 year reports)
- 30% spatial match distance

### Technology Stack

- **Geospatial Processing**: Pandas, GeoPandas, Rasterio, GDAL
- **AI/Computer Vision**: 
  - **YOLOv8** (Object Detection)
  - **OpenAI CLIP** (Zero-Shot Defect Classification)
  - **PyTorch** (Inference Engine)
- **Spatial Indexing**: SciPy KDTree
- **OCR**: Tesseract (for unstructured report parsing)
- **Web App**: FastAPI backend + React (Vite) frontend for live dashboards
- **Cloud Infrastructure**: AWS/Azure for batch processing with Dask parallelization
- **Imagery APIs**: Google Earth Engine, Planet API, AWS S3 (NAIP)

## Cost Analysis

### Per-Pole Cost Breakdown ($0.01-0.05/pole target)

| Category | Cost | Details |
|----------|------|---------|
| Imagery Acquisition | $0-0.02/pole | NAIP free; commercial satellite $10-20/km² for subsets |
| Cloud GPU Computing | $0.005-0.02/pole | YOLOv8 inference on H100/A100 GPUs |
| Data Processing | $0.002-0.005/pole | Storage, OCR, model fine-tuning |
| Human Review (10-30%) | $0.003-0.01/pole | Dashboard-assisted review |
| **Total Savings** | **-$3-6/pole offset** | 70-90% automation = $2.1M-5.4M/year saved |

### Pilot Budget
- 10K poles: $100-500
- 1M poles: $10K-50K total

## Data Access Challenges

### Key Hurdles

1. **Regulatory Compliance**: FCC rules require sharing upon request, not proactive bulk access
   - *Mitigation*: Leverage FCC transparency, Verizon NDA for internal reports, start with public filings

2. **Proprietary Data Silos**: Technician reports often unstructured; GIS access requires internal approval
   - *Mitigation*: API integration, OCR for PDFs, pilot data-sharing MOU (2-4 weeks)

3. **Imagery Quality**: NAIP free but seasonal occlusions; satellite coverage gaps
   - *Mitigation*: Multi-source fusion (NAIP + commercial), multi-temporal (leaf-off) images

4. **Technical Integration**: CRS mismatches, large datasets (1-10GB), AI training data scarcity
   - *Mitigation*: Standardized GeoJSON, Dask parallelization, fine-tune on public datasets + 1K Verizon samples

## Implementation Plan

### Phase 1: Pilot (10K poles, 2-4 weeks)
1. Data collection: Obtain sample reports + imagery for East Coast subset
2. Preprocessing: Clean, standardize CRS, create buffer zones
3. Model training: Fine-tune YOLOv8 on 1K labeled pole images
4. Detection: Run inference on pilot imagery tiles
5. Fusion: Match detections to reports, generate classifications
6. Review: Build Streamlit dashboard, validate accuracy

### Phase 2: Scale (1M poles, 2-3 months)
1. Batch processing: Deploy on cloud GPU cluster (100K poles/day)
2. Multi-source integration: Expand imagery providers, parse all reports
3. Feedback loops: Implement retraining pipeline from human reviews
4. Integration: Connect to Verizon third-party payment system

### Phase 3: Production (Ongoing)
1. Quarterly retraining: Improve model on new labels
2. Metrics tracking: Precision/recall validation, <5% false positive target
3. Cost optimization: Spot instances, API tier management

## Expected Outcomes

- **Automation Rate**: 70-90% of poles verified without manual inspection
- **Accuracy**: ≥85% precision (validated on 10% holdout set)
- **Review Queue**: 10-30% of poles surfaced for human oversight
- **ROI**: 50-70% reduction in third-party inspection costs
- **Compliance**: Meets FCC 5-year audit cycles with audit trail

## Next Steps

1. Share sample data (10K pole subset with reports + imagery access)
2. Legal review: Data-sharing MOU with Verizon (1-2 months)
3. Prototype development: Build end-to-end pipeline on pilot data
4. Demonstration: Present results to stakeholders
5. Production deployment: Q1 2026 target

### Current Pilot Hardening Tasks (No-Cost)

- **Street-Level Enrichment**: Harvest Mapillary imagery, label pole/non-pole crops, and fold them into the training dataset as additional positives and hard negatives.
- **Retrain Detector**: Re-run YOLO fine-tuning with the expanded dataset and re-evaluate recall across Harrisburg corridors.
- **Contextual Filters**: Integrate free 3DEP DSM height rasters and OSM road proximity to suppress false positives in wetlands/woodland or far from rights-of-way.
- **POC Diff View**: Surface the “before vs after” results in the existing FastAPI/React dashboard (linking to the Streamlit diff page) to quantify automated coverage gains for stakeholders.

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

The system processes 1M poles in weeks versus years manually, with proven AI techniques (YOLOv8 on aerial imagery achieving 85-95% precision) adapted for utility-specific challenges like occlusions and coordinate precision.

---

**Contact**: AI Automation Team
**Date**: October 14, 2025
**Status**: Proposal - Awaiting Data Access & Pilot Approval
