# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ❌ CRITICAL RULE: ABSOLUTELY NO MOCK OR SYNTHETIC DATA

**NEVER** create, generate, or use:
- Mock data
- Synthetic data
- Fake technician reports
- Simulated GIS records
- Generated test data
- Random/fake coordinates

**ALWAYS** use ONLY REAL data from actual sources:
- Real NAIP satellite imagery
- Real OpenStreetMap data
- Real AI model detections
- Real public datasets (FCC, county GIS, etc.)

**If real data is not available, STOP and ask the user where to get it.**

## Project Overview

PoleLocations is an AI-driven system for automating Verizon utility pole location verification across 1M+ East Coast poles. The system uses computer vision (YOLOv8), geospatial processing, and multi-source data fusion to verify x-y coordinates every 5 years per FCC requirements, reducing manual inspection costs from $3-6/pole to $0.01-0.05/pole.

**Key Goal**: Automate 70-90% of verifications by cross-validating satellite/aerial imagery with historical technician reports, surfacing only 10-30% of ambiguous cases for human review.

## System Architecture

The pipeline follows a four-stage modular design:

### 1. Data Ingestion Layer
- **Inputs**: Historical technician reports (CSV/Excel: pole_id, lat/lon, status, date), Verizon GIS shapefiles, high-res imagery (NAIP/USGS free, Maxar/Planet commercial)
- **Processing**: Standardize to EPSG:4326 CRS, filter to East Coast bounding box, create 10-20m buffer zones around reported coordinates
- **Output**: GeoJSON files for downstream processing (1-10GB for 1M poles)
- **Tools**: GeoPandas for spatial ops, Pandas for tabular data, Rasterio/GDAL for imagery tiling

### 2. AI Detection Layer
- **Model**: YOLOv8 object detector fine-tuned on utility pole datasets (1K+ labeled images combining public sources + Verizon-specific examples)
- **Detection Logic**: Scans 1km² imagery tiles, identifies poles via shapes/shadows/attachments, outputs bounding boxes with confidence scores (0-1)
- **Geolocation**: Converts pixel coordinates to lat/lon using image transforms (Rasterio geotransform)
- **Performance Target**: 85-95% precision on aerial data (≤30cm resolution)
- **Occlusion Handling**: Multi-temporal imagery (leaf-off seasons), multi-source fusion (NAIP + satellite)
- **Tools**: PyTorch/TensorFlow for training, Ultralytics YOLOv8 for inference

### 3. Fusion & Verification Layer
- **Spatial Matching**: SciPy KDTree for nearest-neighbor search within 5-10m thresholds between detected and historical coordinates
- **Confidence Scoring Formula**: `0.4 * imagery_confidence + 0.3 * report_recency + 0.3 * (1 - normalized_distance)`
- **Classification Rules**:
  - **Verified Good** (auto-eliminate): distance <5m AND confidence >0.8 AND recent verified status
  - **In Question** (human review): distance >5m OR confidence <0.6 OR conflicting reports
  - **New/Missing** (field escalation): unmatched detections or absent poles
- **Report Parsing**: Tesseract OCR for unstructured PDFs, weighting for recency (<5 years prioritized)

### 4. Output Layer
- **Review Interface**: FastAPI backend + React (Vite) frontend rendering tile imagery, detections, and metadata (Map + Review Queue pages). Streamlit diff viewer is optional for POC demos.
- **Exports**: GeoJSON (verified poles), CSV (review queue with priorities), audit logs
- **Feedback Loop**: Human approvals/rejections retrain the model quarterly via PyTorch fine-tuning
- **Integration**: Connects to Verizon's third-party payment system to prioritize targeted inspections

### Data Flow
```
Historical Reports + GIS + Imagery
    ↓ [GeoPandas preprocessing]
Buffered GeoJSON zones (1M points)
    ↓ [GDAL tiling → 1km² grids]
Imagery tiles
    ↓ [YOLOv8 inference]
Detections (lat/lon, confidence)
    ↓ [KDTree spatial matching + scoring]
Classifications (Verified/Question/Missing)
    ↓ [Streamlit UI + exports]
Cleared poles + Review queue + Retraining data
```

## Technical Stack

- **Geospatial**: GeoPandas, Rasterio, GDAL (CRS transforms, tiling, buffering)
- **AI/CV**: PyTorch/TensorFlow (training), Ultralytics YOLOv8 (inference)
- **Spatial Indexing**: SciPy KDTree (nearest-neighbor in 5-10m radius)
- **OCR**: Tesseract (parse unstructured technician reports)
- **Visualization**: React + Vite (primary dashboard), FastAPI (REST API), Folium/pydeck where needed; Streamlit diff app for ad-hoc demos
- **Parallelization**: Dask (batch processing 100K poles/day)
- **Cloud**: AWS/Azure (GPU: H100/A100 at $1.85-1.99/hr), AWS S3 (NAIP storage)
- **Imagery APIs**: Google Earth Engine (satellites), Planet API, AWS S3 (NAIP public dataset)

## Critical Implementation Details

### Coordinate Reference Systems (CRS)
- **Standard**: EPSG:4326 (WGS84 lat/lon) for all outputs
- **Handling Mismatches**: Always reproject input shapefiles/imagery to EPSG:4326 using GeoPandas `.to_crs()` before spatial ops
- **Precision**: 5-10m threshold requires careful geotransform handling in Rasterio

### Imagery Acquisition Strategy
- **Primary Source**: NAIP (free, 1m resolution, public domain via AWS S3 `s3://usgs-naip`)
- **Fallback**: Commercial VHR (<30cm): Maxar/Planet at $10-20/km² for archive, $20-50/km² for tasking
- **Multi-Temporal**: Combine leaf-on/leaf-off seasons to mitigate tree occlusions
- **Download Limits**: USGS EarthExplorer bulk limit 8GB/file; use AWS S3 API for NAIP instead
- **Tiling**: Break into 1km² tiles with GDAL to manage file sizes and parallelize inference

### Model Training Considerations
- **Training Data Sources**: Public datasets (e.g., DetectUtilityPoles on GitHub) + 1K Verizon-labeled samples
- **Fine-Tuning**: Start with YOLOv8n pretrained weights, train on pole-specific features (crossarms, shadows, wire attachments)
- **Validation**: 10% holdout set with ground truth from GPS-verified subset (1% sample)
- **Augmentation**: Rotate, flip, brightness/contrast variations for robustness to lighting/angles
- **Retraining Cadence**: Quarterly updates from human review feedback to improve accuracy

### Scaling and Performance
- **Batch Size**: Process 100K poles/day on GPU cluster (Lambda/RunPod/CoreWeave cheaper than AWS/GCP by 20-50%)
- **Parallelization**: Dask for CPU-bound geospatial ops, multi-GPU for inference
- **Spot Instances**: Use spot/preemptible VMs for 50% cost savings on cloud GPUs
- **Storage**: 10-50GB S3/Cloud Storage at $0.02-0.026/GB/month
- **Cost Target**: $0.01-0.05/pole total ($10K-50K for 1M poles)

### Data Access Hurdles & Mitigations
1. **FCC Compliance**: Reports shared upon request per 47 CFR §1.1411, not bulk; leverage public filings (PA PUC audits) + Verizon NDA
2. **Proprietary Silos**: Technician reports unstructured; require API integration or OCR pipeline with 2-4 week MOU
3. **Imagery Quality**: NAIP seasonal occlusions; mitigate with multi-source fusion and leaf-off acquisitions
4. **CRS Mismatches**: Standardize all inputs to EPSG:4326 via GeoPandas before KDTree ops

## Classification Logic Details

### Confidence Scoring Weights
Tune these weights based on pilot validation (default: 0.4/0.3/0.3):
```python
score = (
    0.4 * detection_confidence +  # YOLOv8 output (0-1)
    0.3 * recency_weight +        # 1.0 if <1yr, 0.8 if 1-3yr, 0.5 if 3-5yr, 0.2 if >5yr
    0.3 * (1 - normalized_distance)  # 1.0 at 0m, 0.0 at 10m threshold
)
```

### Threshold Tuning
- **Verified Good**: `distance < 5m AND confidence > 0.8 AND report_status == 'verified'`
- **In Question**: `distance >= 5m OR confidence < 0.6 OR conflicting_reports`
- Adjust thresholds based on precision/recall on validation set (target: <5% false positives)

### Edge Cases
- **Multiple Detections Near One Report**: Take highest confidence within 10m, flag others as potential new poles
- **No Detection for Reported Pole**: Flag as missing (potential removal or obstruction)
- **Detection Far from Any Report**: Flag as new pole (add to inventory or error)

## Development Phases

### Phase 1: Pilot (10K poles, 2-4 weeks)
1. Obtain sample data: East Coast subset with reports + NAIP imagery access
2. Preprocess: GeoPandas standardization, buffer zone creation
3. Train model: Fine-tune YOLOv8 on 1K labeled images (100-500 GPU-hours)
4. Run detection: Inference on pilot tiles, extract lat/lon via geotransform
5. Fusion: KDTree matching, apply scoring, generate classifications
6. Build dashboard: Streamlit UI for review queue validation

### Phase 2: Scale (1M poles, 2-3 months)
1. Cloud deployment: Set up Dask + GPU cluster on Lambda/AWS
2. Batch processing: 100K poles/day with spot instances
3. Multi-source imagery: Integrate NAIP + commercial APIs (Planet/Maxar)
4. OCR pipeline: Parse all unstructured reports via Tesseract
5. Feedback loops: Implement retraining pipeline from Streamlit reviews

### Phase 3: Production (Ongoing)
1. Quarterly retraining on new labels from human reviews
2. Metrics tracking: Precision/recall validation, audit trail generation
3. Cost optimization: Spot instance management, API tier balancing
4. Verizon integration: Connect to third-party payment system

## Key Metrics and Targets

- **Automation Rate**: 70-90% of poles verified without manual inspection
- **Precision**: ≥85% (validated on 10% holdout set)
- **Recall**: ≥80% (catch 80%+ of actual poles)
- **False Positive Rate**: <5% (minimize incorrect "verified good" classifications)
- **Review Queue**: 10-30% of total poles surfaced for human oversight
- **Cost**: $0.01-0.05/pole (vs. $3-6/pole manual)
- **ROI**: 50-70% reduction in third-party inspection costs ($2.1M-5.4M/year savings)

## Security and Compliance

- **Data Sensitivity**: Pole locations are infrastructure-critical; require Verizon NDA
- **FCC Audit Trail**: Log all classifications, human reviews, and model versions for compliance
- **PII Handling**: Technician reports may contain names; anonymize before training data export
- **API Keys**: Never commit imagery API keys (Planet, Maxar, Google Earth Engine); use environment variables or secret managers
- **Model Versioning**: Track YOLOv8 checkpoints with metrics for reproducibility

## Common Gotchas

1. **CRS Confusion**: Always verify input data CRS with `gdf.crs` before spatial ops; reproject to EPSG:4326
2. **Buffer Units**: GeoPandas buffer in degrees for lat/lon (0.0001° ≈ 10m); use meters by reprojecting to UTM first if precision critical
3. **KDTree Distance Units**: Returns distances in CRS units (degrees for EPSG:4326); convert to meters for thresholds
4. **YOLO Confidence**: Model outputs logits; apply sigmoid for 0-1 probabilities
5. **Imagery Georeferencing**: Verify NAIP tiles have embedded geotransform (`rasterio.open(path).transform`) before pixel-to-latlon conversion
6. **Occlusions**: Trees/buildings can hide poles; multi-temporal imagery critical for >90% detection rate
7. **Report Parsing**: OCR errors common; validate extracted coords against known ranges (East Coast: lat 38-42, lon -75 to -72)

## Next Steps for Implementation

This is a proposal-stage project. Before writing code:
1. **Data Access**: Secure Verizon data-sharing MOU (1-2 months legal review)
2. **Sample Data**: Obtain 10K pole subset with reports + imagery access for pilot
3. **Environment Setup**: Configure cloud GPU access (Lambda/AWS), install geospatial stack (GDAL system deps)
4. **POC Hardening**: Harvest Mapillary imagery + labels, retrain detector with the expanded dataset, wire the Streamlit diff view into the FastAPI/React experience, and deploy free 3DEP DSM/OSM contextual filters.

## Mapillary Labeling Quick Reference

1. `PYTHONPATH=src ./venv/bin/python src/utils/harvest_mapillary.py --limit 300` (requires `MAPILLARY_TOKEN`).
2. Populate `data/raw/mapillary/mapillary_labels.csv` with `image_id,pole|negative` after manual review.
3. `PYTHONPATH=src ./venv/bin/python src/utils/process_mapillary_labels.py` to ingest thumbnails into the YOLO dataset.
4. Regenerate splits (`prepare_yolo_dataset.py`), retrain `PoleDetector`, copy best weights to `models/pole_detector_real.pt`, and rerun `run_pilot.py`.
4. **Training Data**: Label 1K pole images or source from public datasets (DetectUtilityPoles GitHub)
5. **Validation Ground Truth**: GPS-verify 1% sample (100-1000 poles) for accuracy benchmarking

Once data is available, start with Phase 1 pilot development.
