# Real Public Data Sources for Multi-Source Pole Verification

**Status**: Research completed October 14, 2025
**Compliance**: NO MOCK/SYNTHETIC DATA - All sources are real public datasets

---

## Currently Available Real Data Sources

### 1. OpenStreetMap Poles (IMPLEMENTED ✅)
- **Source**: OpenStreetMap via OSMnx Python library
- **Coverage**: Harrisburg, PA area
- **Count**: 1,977 poles
- **Format**: CSV with lat/lon coordinates
- **Location**: `/data/raw/osm_poles_harrisburg_real.csv`
- **Acquisition Method**:
  ```python
  import osmnx as ox
  poles = ox.features_from_place("Harrisburg, Pennsylvania", tags={'power': 'pole'})
  ```
- **Data Fields**: pole_id, lat, lon, power tag
- **Quality**: Community-verified, high accuracy in urban areas

### 2. NAIP Satellite Imagery (IMPLEMENTED ✅)
- **Source**: USDA National Agriculture Imagery Program via Microsoft Planetary Computer
- **Resolution**: 0.6m/pixel (60cm)
- **Format**: GeoTIFF (4-band RGBA)
- **Size**: 392.7 MB for Harrisburg area
- **Location**: `/data/raw/naip_imagery/`
- **CRS**: EPSG:26918 (UTM Zone 18N)
- **Acquisition Method**: Microsoft Planetary Computer API (no auth required)
- **API**: https://planetarycomputer.microsoft.com/api/stac/v1
- **Quality**: High-resolution aerial imagery, updated periodically

### 3. AI Detection Results (IMPLEMENTED ✅)
- **Source**: YOLOv8n trained model on NAIP imagery
- **Count**: 315 poles detected
- **Accuracy**: 95.4% precision, 95.2% recall, 98.6% mAP50
- **Format**: CSV with detection confidence scores
- **Location**: `/data/processed/pole_training_dataset/`
- **Data Fields**: detection_id, lat, lon, confidence, image_path
- **Quality**: Validated through training/validation split

---

## Newly Identified Real Data Sources (Available for Integration)

### 4. DC Utility Poles Dataset (1999) - READY TO DOWNLOAD ✅

**Overview:**
- **Source**: Washington DC Open Data Portal (Data.gov)
- **Coverage**: Washington DC, parts of MD and VA
- **Year**: 1999 (historical but real data)
- **License**: Creative Commons Attribution (public domain)
- **Count**: Unknown (thousands of poles)

**Direct Download URLs:**
```bash
# CSV Format
curl -o dc_utility_poles_1999.csv "https://opendata.dc.gov/api/download/v1/items/0a19b79fa45a48019c408ff1c79e875f/csv?layers=8"

# GeoJSON Format
curl -o dc_utility_poles_1999.geojson "https://opendata.dc.gov/api/download/v1/items/0a19b79fa45a48019c408ff1c79e875f/geojson?layers=8"

# Shapefile Format
curl -o dc_utility_poles_1999.zip "https://opendata.dc.gov/api/download/v1/items/0a19b79fa45a48019c408ff1c79e875f/shapefile?layers=8"
```

**REST API:**
- Endpoint: `https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Planimetrics_1999/MapServer/8`
- Format: ArcGIS GeoService REST API
- Query Example: `/query?where=1%3D1&outFields=*&f=geojson`

**Coordinate System**:
- Bounding Box: -77.1161, 38.7931 to -76.9094, 38.9957
- CRS: Likely EPSG:4326 (WGS84)

**Integration Value:**
- Can serve as historical baseline for DC area
- Provides cross-validation for OSM data in DC
- Test multi-source fusion with known dataset

**Limitations:**
- Data from 1999 (25 years old - poles may have been removed/relocated)
- Different geographic area than our Harrisburg focus
- May need recency penalty in confidence scoring

---

### 5. HIFLD Electric Power Transmission Lines - AVAILABLE ✅

**Overview:**
- **Source**: Homeland Infrastructure Foundation-Level Data (DHS/CISA)
- **Authority**: Oak Ridge National Laboratory (ORNL)
- **Coverage**: Nationwide (entire USA)
- **Voltage**: 69 kV to 765 kV transmission lines
- **License**: Public domain (US Government)

**Download Portal:**
- Website: https://hifld-geoplatform.opendata.arcgis.com/datasets/electric-power-transmission-lines
- Formats: CSV, KML, Shapefile, GeoJSON, File Geodatabase

**Data Fields** (expected):
- Line geometry (polyline)
- Voltage rating
- Owner/Operator name
- Status (operational/decommissioned)
- Coordinates of towers/poles along lines

**Integration Value:**
- High-voltage transmission poles marked along lines
- Official government dataset
- Can identify Verizon attachment points on transmission infrastructure
- Nationwide coverage for scaling beyond Harrisburg

**Integration Method:**
1. Download transmission lines for Pennsylvania
2. Buffer lines by 50m to find nearby OSM/AI poles
3. Tag poles as "transmission-adjacent" vs "distribution"
4. Higher confidence for poles near transmission corridors

**Limitations:**
- Focuses on transmission lines (69kV+), not distribution poles (7kV-35kV)
- May not include individual pole locations, only line paths
- Need to infer pole locations from line geometry

---

### 6. FCC Cellular Tower Database - AVAILABLE ✅

**Overview:**
- **Source**: Federal Communications Commission Universal Licensing System (ULS)
- **Authority**: FCC (federal regulatory data)
- **Coverage**: Nationwide (entire USA)
- **License**: Public domain (US Government)
- **Update Frequency**: Daily/Weekly transactions

**Download Methods:**

**Option A: HIFLD Cellular Towers Dataset**
- Portal: https://hifld-geoplatform.opendata.arcgis.com/datasets/cellular-towers
- Formats: CSV, GeoJSON, Shapefile
- Pre-processed point locations

**Option B: Direct FCC ULS Downloads**
- Website: https://www.fcc.gov/wireless/data/public-access-files-database-downloads
- Format: Pipe-delimited ZIP files (weekly/daily)
- Files: Weekly Transactions (contains antenna structure coordinates)
- URL Pattern: https://www.fcc.gov/uls/transactions/daily-weekly

**Data Fields** (expected):
- Tower ID (FCC registration number)
- Lat/Lon coordinates
- Tower height
- Owner/licensee information
- Structure type
- Registration date

**Integration Value:**
- Many cellular towers are on utility poles (co-location)
- Verizon Wireless owns thousands of these towers
- Can cross-reference tower locations with pole locations
- Identifies communication infrastructure attachment points

**Integration Method:**
1. Download FCC cellular towers for Pennsylvania
2. Spatial join with OSM poles (within 10m radius)
3. Tag poles as "cellular-attached" if tower nearby
4. Higher importance flag for Verizon-owned towers
5. Use as additional confidence source (if tower exists, pole likely verified)

**Limitations:**
- Only includes registered cellular towers (not all poles have towers)
- May be slightly offset from actual pole location
- Registration database may have reporting delays

---

### 7. FCC Antenna Structure Registration (ASR) Database - AVAILABLE ✅

**Overview:**
- **Source**: FCC Antenna Structure Registration
- **Authority**: FCC (structures >200 feet or near airports)
- **Coverage**: Nationwide
- **License**: Public domain

**Access Methods:**
- Search Tool: https://wireless2.fcc.gov/UlsApp/AsrSearch/asrAdvancedSearch.jsp
- Bulk Download: Available through state GIS portals
- Example: https://gisdata.mn.gov/dataset/util-fcc

**Data Fields:**
- Registration number (ASR)
- Lat/Lon coordinates
- Structure height
- Owner information
- FAA study number

**Integration Value:**
- Identifies tall communication structures
- Many are on utility poles or share pole infrastructure
- Can validate pole locations for tall structures

**Limitations:**
- Only tall structures (>200 feet) or near airports
- Limited to communication infrastructure
- May not include distribution poles

---

### 8. State/County GIS Open Data Portals - VARIES BY LOCATION

**Pennsylvania Resources:**

**A. PASDA (Pennsylvania Spatial Data Access)**
- Website: https://www.pasda.psu.edu/
- Contact: pasda@psu.edu
- Search: Use keyword search for "utility", "pole", "electric", "power"
- Formats: Shapefile, GeoJSON, various
- Status: Need to manually search portal

**B. Dauphin County Open Data**
- Website: https://data-dauphinco.opendata.arcgis.com/
- Coverage: Dauphin County (includes Harrisburg)
- Format: ArcGIS Hub portal
- Status: No utility poles dataset found in initial search
- Action: Contact GIS department directly

**C. PA DEP GIS Portal**
- Website: https://www.dep.pa.gov/DataandTools/Pages/GIS.aspx
- Layers: 300+ environmental/infrastructure datasets
- Status: Need to search for utility infrastructure

**Integration Value:**
- Local government authoritative data
- Most up-to-date for specific regions
- May include inspection records

**Next Steps:**
1. Search PASDA for Pennsylvania utility datasets
2. Contact Dauphin County GIS: Request utility pole inventory
3. Check neighboring counties (Cumberland, Lebanon, Perry)

---

## Data Sources NOT Available (Per Research)

### ❌ Verizon Proprietary Pole Inventory
- **Status**: Not publicly accessible
- **Access**: Requires NDA, internal approval, data-sharing MOU
- **Alternative**: Use public sources + AI detection as proxy

### ❌ Technician Inspection Reports (Real)
- **Status**: Not publicly accessible without Verizon partnership
- **Access**: Internal Verizon data, may be unstructured PDFs
- **Alternative**: Use report recency scoring based on OSM update dates

### ❌ Utility Company Pole Attachment Records
- **Status**: Available via FCC filings but not bulk download
- **Access**: Individual case-by-case FCC ECFS searches
- **Alternative**: Use pole attachment disputes as spot checks

---

## Recommended Integration Priority

### Phase 1: Immediate Integration (Next 1-2 days)

1. **Download DC Utility Poles (1999)** ✅
   - Quick win to test multi-source fusion
   - Direct download URLs available
   - Can validate spatial matching algorithm

2. **Cross-validate OSM + AI Detections** ✅
   - Already have both datasets (1,977 OSM + 315 AI)
   - Calculate spatial distance between sources
   - Identify mismatches >5m for review

3. **HIFLD Electric Transmission Lines** ✅
   - Download Pennsylvania subset
   - Buffer analysis to find transmission-adjacent poles
   - Tag high-value infrastructure

### Phase 2: Extended Integration (Next 1 week)

4. **FCC Cellular Towers (HIFLD)**
   - Download pre-processed HIFLD cellular towers
   - Spatial join with poles (10m buffer)
   - Identify Verizon-owned towers

5. **Search PASDA for Pennsylvania Datasets**
   - Manual keyword search
   - Contact data providers
   - Download any available utility datasets

6. **County GIS Outreach**
   - Email Dauphin County GIS department
   - Request utility pole inventory or inspection records
   - Inquire about data-sharing for research

### Phase 3: Advanced Integration (Future)

7. **FCC ULS Bulk Downloads**
   - Parse pipe-delimited FCC files
   - Extract antenna/tower coordinates
   - Build parser for weekly updates

8. **Multi-temporal NAIP Imagery**
   - Download NAIP imagery from multiple years (2017, 2019, 2021, 2024)
   - Detect pole changes over time
   - Identify new/removed poles

9. **Neighboring Counties**
   - Expand to Cumberland, Lebanon, York counties
   - Scale to entire Pennsylvania
   - Test on other East Coast states

---

## Multi-Source Fusion Strategy (Per README)

### Confidence Scoring Formula:
```
Total Confidence = (0.40 × AI_Detection) + (0.30 × Recency) + (0.30 × Spatial_Match)

Where:
- AI_Detection: YOLOv8 confidence (0.0-1.0)
- Recency: 1.0 if <1yr, 0.8 if <3yr, 0.5 if <5yr, 0.2 if >5yr
- Spatial_Match: 1.0 if <2m, 0.8 if <5m, 0.5 if <10m, 0.2 if >10m
```

### Classification Rules:
1. **Verified Good (76% target)**:
   - Confidence ≥ 0.8 AND spatial match <5m
   - At least 2 sources agree
   - Action: Auto-eliminate from review

2. **In Question (20% target)**:
   - Confidence <0.8 OR spatial mismatch >5m
   - Conflicting reports between sources
   - Action: Flag for human review

3. **Missing/New (4% target)**:
   - Only 1 source (AI detection without report, or vice versa)
   - Action: Escalate for field verification

### Implementation with Current Data:

**2-Source Cross-Validation (Minimum Viable):**
```
Source A: OSM poles (1,977 poles)
Source B: AI detections (315 poles)

Matches (<5m): Verified Good
OSM only: In Question (AI didn't detect - occlusion? error?)
AI only: New/Missing (potential new poles or false positives)
```

**3-Source Cross-Validation (With DC Data):**
```
Source A: OSM poles (1,977)
Source B: AI detections (315)
Source C: DC utility poles for DC area poles (if we expand to DC)

3-way match: Verified Good (highest confidence)
2-way match: Verified Good (medium confidence)
1-way only: In Question or Missing
```

**4+ Source Cross-Validation (With HIFLD + FCC):**
```
Source A: OSM poles
Source B: AI detections
Source C: HIFLD transmission lines (proximity-based)
Source D: FCC cellular towers (proximity-based)

More sources = higher confidence
Conflicting sources = In Question
```

---

## Next Steps

### Immediate Actions:
1. ✅ Download DC utility poles dataset (CSV + GeoJSON)
2. Create data ingestion script: `src/data/ingest_dc_poles.py`
3. Build multi-source fusion engine: `src/fusion/multi_source_validator.py`
4. Cross-validate OSM + AI detections
5. Calculate confidence scores for all 1,977 poles
6. Generate 3-tier classification

### This Week:
1. Download HIFLD electric transmission lines (PA subset)
2. Download HIFLD cellular towers (PA subset)
3. Search PASDA for Pennsylvania utility datasets
4. Update backend API with new verification endpoints
5. Update dashboard to show real 3-tier distribution

### This Month:
1. Contact Dauphin County GIS for local data
2. Implement FCC ULS parser
3. Multi-temporal NAIP analysis
4. Scale to neighboring counties

---

**Document Status**: Research Complete
**Real Data Sources Identified**: 8 (3 implemented, 5 available)
**Mock Data Sources**: 0 (strict compliance with NO MOCK DATA rule)
**Ready for Implementation**: YES ✅
