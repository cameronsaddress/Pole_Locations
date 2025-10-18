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
- [ ] Expand training data with recent true pole imagery and curated hard negatives (trees, water, signage) and retrain detector.
- [x] Apply contextual GIS filters (water/forest masks, road/parcel proximity) to suppress implausible detections before fusion.
- [x] Audit and correct pixel→lat/lon calibration per tile; cache accuracy metrics to prevent drift.
- [x] Strengthen fusion rules to require corroborating sources (inventory, repeat AI hits, LiDAR) before marking poles verified; downgrade single-source hits to review.
- [ ] Harvest the latest NAIP leaf-on/leaf-off tiles plus state orthophotos for Harrisburg corridors and integrate multi-season imagery.
- [ ] Pull USGS 3DEP LiDAR tiles and derive height rasters to filter out short non-pole detections.
- [ ] Generate additional training labels from Mapillary/KartaView street-level imagery and a quick internal labeling sprint (≥300 pole/non-pole crops).
- [x] Build GIS masks using open TIGER roads, parcels, and land-cover/NDVI to block water/forest false positives and snap detections to ROWs.
- [ ] Construct synthetic hard negatives from open sign/light datasets and retrain detector with them.
- [ ] Produce a Streamlit “before vs after” diff dashboard that visualizes corridor improvements for POC demos.

## Multi-Source Data Integration Roadmap

- [ ] Verizon GIS + inspection ledger ingest: build authenticated pipeline to pull fresh pole inventory (coordinates, inspection status, structure metadata) and register it alongside OSM feeds for fusion.
- [ ] State/county utility & permitting datasets: harvest available open-data exports (e.g., PennDOT utility permits, municipal asset registries) and normalize schemas for corroboration.
- [ ] Commercial aerial refresh: orchestrate ingestion of 30 cm Maxar/Planet or state orthophoto tiles (leaf-off + leaf-on) and prepare metadata so YOLO can be re-run per season.
- [ ] Street-level imagery enrichment: integrate Mapillary/Kinetik APIs to pull latest corridor frames, queue labeling jobs, and merge confirmed poles/hard negatives into the training dataset.
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
