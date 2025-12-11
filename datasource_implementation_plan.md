# Implementation Plan: Enterprise Data Source Integration

## 🎯 Objective
Integrate five new "free/open" data sources to drastically improve system accuracy and robustness. The integration will be **modular**, with each source handled by a dedicated connector in `src/ingestion/connectors/`.

## 📦 Data Source Modules

### 1. FAA Obstruction Database (Ground Truth)
*   **Source**: FAA Digital Obstacle File (DOF) - CSV.
*   **Role**: Provides "Golden Truth" for tall transmission towers (>200ft) and poles near airports.
*   **Integration**:
    *   Script: `src/ingestion/connectors/faa_obstacles.py`
    *   Logic: Download CSV, filter for `AGL > 40` & `Type=['POLE', 'TOWER']`, Insert into `poles` table with `status='Federal_Record'`.

### 2. OpenInfraMap (Grid Context)
*   **Source**: OpenStreetMap Power Infrastructure (via Overpass API).
*   **Role**: Defines the "Grid Backbone".
*   **Integration**:
    *   Script: `src/ingestion/connectors/openinframap.py`
    *   Logic: Fetch `way["power"="line"]` and `node["power"="tower"]`. Store in DB `infrastructure` table (new) or `poles`.
    *   Enrichment: Detections within 20m of these lines get a confidence boost.

### 3. PASDA Road Centerlines (Spatial Filter)
*   **Source**: PennDOT Road Centerlines (GeoJSON/Shapefile).
*   **Role**: Superior road proximity filtering for Pennsylvania compared to OSM.
*   **Integration**:
    *   Script: `src/ingestion/connectors/pasda_roads.py`
    *   Logic: Fetch, Clean, Project to EPSG:4326, Save to `data/processed/roads_pasda.geojson`.
    *   Update `context_filters.py` to prioritize PASDA roads if available.

### 4. Mapillary (Visual Verification)
*   **Source**: Mapillary API v4 (Street Level Imagery).
*   **Role**: "Eyes on the ground" to verify defects (rust, leaning).
*   **Integration**:
    *   Script: `src/ingestion/connectors/mapillary.py`
    *   Logic: `MapillaryClient` class. check `is_image_available(lat, lon)`.
    *   **Note**: Requires API Key (User must provide). Will fail gracefully if missing.

### 5. USGS Lidar (Verticality Check)
*   **Source**: USGS 3DEP Lidar Point Clouds (LPC) via `pdal` or `laspy` (Amazon Public Dataset).
*   **Role**: Confirms if a detection is a narrow vertical object vs a tree.
*   **Integration**:
    *   Script: `src/ingestion/connectors/usgs_lidar.py`
    *   Logic: Fetch local LAZ tile. Analyze point distribution in a 1m cylinder around detection.
    *   Metric: `verticality_score` (Ratio of Z-variance to XY-variance).

## 🛠 Execution Steps

1.  **Dependencies**: Install `laspy`, `requests`, `pandas`, `geopandas`.
2.  **Develop Connectors**: Write the 5 scripts defined above.
3.  **Pipeline Integration**:
    *   Update `src/pipeline/enrich.py` to call these connectors.
    *   Update `src/pipeline/fusion.py` to use new confidence signals (e.g., FAA match = 100% confidence).
4.  **Test**: Run a "Data Source Verification" script.
5.  **Documentation**: Update README with detailed "Data Sources" dictionary.

## ⚠️ Risks
*   **API Limits**: Mapillary/Overpass have rate limits.
*   **Data Size**: USGS Lidar and PASDA Vector files are huge. We will implement "Lazy Loading" or "Region of Interest" filtering.
