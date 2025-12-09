## New York State Expansion

- [ ] **NAIP statewide coverage**: split New York into manageable AOIs or obtain Planetary Computer credentials; rerun `sync_multi_source_data.py --naip-max-tiles 0` for each region to pull all tiles.
- [ ] **3DEP DSM download**: execute `download_3dep_dsm.py` for New York bounding boxes once NAIP tiles are staged (`--areas new_york_state --dsm-limit <value>`).
- [ ] **Authoritative pole inventory**: source statewide pole shapefiles/CSV from NY utilities or open-data portals to replace OSM-only inventory; integrate into the downloader pipeline.
- [ ] **Statewide validation pass**: after imagery and inventory are updated, rerun `run_pilot.py` using the statewide directories and confirm the dashboard map renders the full coverage.

## Production-Grade Detection Roadmap

- [ ] **Data harvesting**: stand up reproducible pipelines for each imagery/inventory feed  
  - [x] NAIP (USDA) → update `download_naip_pc.py` to pull latest tiles + manifest (2022 currently latest for AOI)  
  - [x] PAMAP leaf-off orthophotos (Pennsylvania PASDA) → downloader + georeferencing script (`georeference_pema_tiles.py`); next: build mosaic/register in crop pipeline  
  - [x] Mapillary/KartaView street-level API → initial metadata/thumbnail fetch (`harvest_mapillary.py`); next: integrate labeling + dataset merge  
  - [ ] FCC ASR, HIFLD energy assets, PennDOT permits, municipal asset registries → normalize CSV/GeoJSON feeds into `data/raw` and document refresh cadence  
  - [ ] USGS 3DEP point clouds + DSM rasters → integrate height features into pipeline  
  - [ ] NLCD/NHD/TIGER contextual layers → automate ingestion and preprocessing
- [ ] **Post-training execution (every run)**
  - [x] Capture `results.csv` / `training_metrics.json`, archive run config + dataset version.
  - [x] Automate real-time detection vs. historical pole audit (distance/precision report) for new checkpoints.
  - [x] Copy best weights to pipeline (`models/pole_detector_real.pt`) and rerun `/api/v1/pipeline/run`.
  - [x] Compare new detections vs. prior run (counts, spatial diff, sample QA).
  - [x] Flag high-uncertainty poles for review (see `outputs/reports/audit_v6_low_confidence.csv`).
  - [ ] Update dashboard stats/manifests so operations sees current accuracy.
- [ ] **Curated training datasets**: expand real pole crops with jittered augmentations, seasonal imagery, and labeled hard negatives; version under `data/processed/pole_training_dataset_vX/`.
  - [x] Aggregate multi-county NAIP tiles (target ≥3 adjacent counties) and regenerate pole crops for broader coverage.
  - [x] Stage street-level hard-negative pipeline (Mapillary/KartaView) with reviewer queues and ingestion scripts.
- [ ] **Active learning loop**: after each pipeline run, surface “needs review” detections, capture human verdicts, and append to the next dataset version.
- [ ] **GPU training experiments**: schedule yolov8m/yolov8l runs (512–640 px) with aggressive augmentation; track metrics via MLFlow/W&B and compare to baselines.
- [ ] **Calibration & thresholds**: run `threshold_sweeper.py` per tile/imagery season to set confidence/IoU values dynamically.
- [ ] **Validation harness**: maintain hold-out “golden tiles,” regression tests, and visual diff dashboards to catch performance regressions pre-deploy.
- [ ] **Human feedback loop**: coordinate field/analyst spot-checks of auto-verified poles; fold corrections back into training and update documentation.
- [ ] **Advanced accuracy levers**
  - [ ] Hyperparameter sweeps (optimizer, warmup, label smoothing) tracked via experiment logger.
  - [ ] Model ensembling/distillation (recall-heavy + precision-heavy checkpoints, optional TensorRT ensemble).
  - [ ] Self-training/pseudo-labeling on high-confidence detections from new imagery, with manual QA audits.
  - [ ] Hard-negative mining using external infrastructure datasets and synthetic renders.
  - [ ] Per-tile confidence calibration (Platt/isotonic) and fusion weight tuning via logistic regression/GBMs.
  - [ ] Integrate additional sensor features (LiDAR heights, DEM slopes, GIS context) into fusion and optional auxiliary model channels.
- [ ] **256×256 retraining cycle**  
  1. Refresh NAIP/PEMA imagery manifests (if needed); ensure georeferenced tiles and mosaic exist.  
  2. Run `extract_pole_crops.py --crop-size 256` with jitter + hard negatives → `data/processed/pole_training_dataset_256/`.  
  3. Split train/val with `prepare_yolo_dataset.py` (85/15, seed 321).  
  4. Fine-tune from `pole_detector_v4` weights at `imgsz=256` (AdamW, lr 4e-4, mosaic/mixup) → `models/pole_detector_256`.  
  5. Validate (`yolo val`) and copy best weights to `models/pole_detector_real.pt`.  
  6. Update pipeline inference window to 256×256 (`detect_tiles` stride/crop updates); rerun `run_pilot.py`, inspect detections.  
  7. Feed Mapillary-labeled samples into next dataset iteration and repeat.  

## Dashboard Accuracy & Data Integrity

- [ ] **Automated threshold sweeps**: run `PoleDetector.sweep_thresholds` after every training cycle, persist the best confidence/IoU pair to `outputs/analysis/threshold_eval/latest.json`, and sync `THRESHOLD_EXPORT_PATH` so inference loads calibrated knobs automatically.
- [ ] **Geospatial offset calibration**: compare detections vs. verified poles to recompute `DETECTION_LAT/LON_OFFSET_DEG` and store overrides whenever drift exceeds 1 m.
- [ ] **Data quality enforcement**: add schema + row-count validation for `summary_metrics.json`, `ai_detections.csv`, and `osm_poles_*` before FastAPI endpoints return values; fail fast with actionable errors instead of silently returning stale numbers.
- [ ] **Dashboard snapshot artifact**: emit `outputs/reports/dashboard_snapshot.json` during each pipeline run with key KPIs and SHA256 fingerprints of every upstream file so the UI can display “data as of” plus provenance.
- [ ] **Metrics API regression tests**: create pytest client fixtures for `/api/v1/metrics/*` endpoints that load tiny CSV/JSON samples to ensure required fields (avg confidence, coverage area, cost) stay accurate across refactors.

## Remove Simulated Data

- [x] Ingestion: delete usage of `src/utils/sample_data_generator.py` and rely solely on real inventories (`get_osm_poles.py`, `ingest_dc_poles.py`, future Verizon feeds).
- [x] Detection: run the YOLOv8 pipeline end-to-end so `run_pilot.py` consumes real inference outputs instead of Gaussian-noise simulations.
- [x] Fusion: update `src/fusion/multi_source_validator.py` to load actual detection exports (no random sampling of OSM poles) and document the expected file locations.
- [x] API: replace placeholder confidence/metric fallbacks in `backend/app/api/v1/poles.py` and `backend/app/api/v1/metrics.py` with values calculated from real datasets, failing fast if data is missing.
- [x] Dashboards: audit Streamlit and React views to ensure every KPI, chart, and map is sourced from real exports (remove hard-coded percentages, counts, and costs).
- [x] Data hygiene: add validation checks that block pipeline runs when only synthetic/sample files are present, and surface instructions for acquiring required imagery + pole inventories.

## Frontend Operational Redesign

- [x] Dashboard: remove cost/ROI tiles and emphasize operational KPIs (status breakdown, compliance monitors, alerts).
- [x] Map view: add filtering (status, confidence, freshness) and enhanced detail overlays for managers.
- [x] Review queue: surface SLA timers, inspection age, and single-source indicators alongside priority sorting.
- [x] Executive summary page: replace financial analytics with operational trend insights (confidence mix, inspection freshness, backlog).
- [x] Update copy/styling to align with operational focus (renamed sections, adjusted legends, removed financial references).

## Model Accuracy Hardening

- [x] Tighten YOLO detection thresholds (confidence/IoU) and evaluate across the labeled validation split; add class-specific NMS if needed.
- [x] Expand training data with recent true pole imagery and curated hard negatives (trees, water, signage) and retrain detector (Upgraded to YOLOv8l + TTA).
- [x] Apply contextual GIS filters (water/forest masks, road/parcel proximity) to suppress implausible detections before fusion.
- [x] Audit and correct pixel→lat/lon calibration per tile; cache accuracy metrics to prevent drift.
- [x] Strengthen fusion rules to require corroborating sources (inventory, repeat AI hits, LiDAR) before marking poles verified; downgrade single-source hits to review.
- [ ] Harvest the latest NAIP leaf-on/leaf-off tiles plus state orthophotos for Harrisburg corridors and integrate multi-season imagery.
- [ ] Pull USGS 3DEP LiDAR tiles and derive height rasters to filter out short non-pole detections.
- [ ] Generate additional training labels from Mapillary/KartaView street-level imagery and a quick internal labeling sprint (≥300 pole/non-pole crops).
  - [ ] Stage Mapillary thumbnail labeling queue (CSV + preview script) so reviewers can tag poles vs. negatives.
  - [ ] Convert labeled Mapillary crops into YOLO format and merge into next dataset revision.
- [x] Build GIS masks using open TIGER roads, parcels, and land-cover/NDVI to block water/forest false positives and snap detections to ROWs.
- [ ] Construct synthetic hard negatives from open sign/light datasets and retrain detector with them.
- [ ] Produce a Streamlit “before vs after” diff dashboard that visualizes corridor improvements for POC demos.

## Multi-Source Data Integration Roadmap

- [ ] Verizon GIS + inspection ledger ingest: build authenticated pipeline to pull fresh pole inventory (coordinates, inspection status, structure metadata) and register it alongside OSM feeds for fusion.
- [ ] State/county utility & permitting datasets: harvest available open-data exports (e.g., PennDOT utility permits, municipal asset registries) and normalize schemas for corroboration.
- [ ] Commercial aerial refresh: orchestrate ingestion of 30 cm Maxar/Planet or state orthophoto tiles (leaf-off + leaf-on) and prepare metadata so YOLO can be re-run per season.
  - [ ] Street-level imagery enrichment: integrate Mapillary/Kinetik APIs to pull latest corridor frames (requires MAPILLARY_TOKEN), queue labeling jobs, and merge confirmed poles/hard negatives into the training dataset.
- [ ] LiDAR & mobile mapping fusion: download USGS 3DEP point clouds or enterprise mobile collections, derive pole-height rasters, and feed the validator with elevation-based confidence boosts.
- [ ] Vegetation/ROW context layers: add utility corridor shapefiles, land-cover, and weather/outage overlays to refine contextual filters and prioritization scoring.
- [ ] External compliance filings: integrate FCC pole attachment reports or public outage filings to cross-validate inventory freshness and inspection cadence.
- [ ] Pennsylvania PAMAP orthophotos: fetch latest 6″–1′ leaf-off aerial tiles, store under `data/imagery/pamap`, and register for detector reruns.
- [ ] NAIP historical stack: stage prior-year NAIP vintages in `data/imagery/naip_historical` to support seasonal training augmentation.
- [ ] USGS 3DEP expansion: pull missing Harrisburg point-cloud tiles into `data/processed/lidar/pointclouds` and regenerate DSM rasters for height scoring.
- [ ] National Land Cover Dataset (NLCD): ingest 30 m land-cover rasters into `data/processed/context/land_cover` and wire into contextual filters.
- [ ] National Hydrography Dataset (NHD): download high-resolution hydro line/polygon data to `data/processed/context/nhd_water.geojson` for improved water masking.
- [ ] TIGER/PennDOT road centerlines: merge latest TIGER and PennDOT road shapefiles into `data/processed/context/transport_roads.geojson` for ROW snapping.
- [ ] FCC ASR + HIFLD energy assets: stage tower/utility infrastructure CSV/GeoJSON feeds inside `data/raw/fcc` and `data/raw/hifld` to enrich context scoring.
- [ ] Municipal Harrisburg/Dauphin open data: pull asset registries or permit logs into `data/raw/municipal` for supplementary inventory corroboration.
- [ ] Mapillary/KartaView refresh cadence: automate quarterly ingestion of corridor imagery metadata into `data/raw/street_level/mapillary` for labeling and QA.
