# Multi-Source Pole Verification System - Implementation Plan

## Current State (What We Have)

✅ **Single Data Source:**
- OpenStreetMap poles: 1,977 poles
- All marked as "verified" at 95.4% confidence
- No cross-validation
- No classification system

❌ **Missing (Per README):**
- Multi-source data fusion
- Confidence scoring algorithm
- Three-tier classification (Verified/In Question/Missing)
- Review queue for questionable poles

---

## Target State (Per README Requirements)

### **Data Sources to Integrate:**

1. **Historical Technician Reports** (CSV/Excel)
   - Fields: pole_id, lat, lon, inspection_date, status
   - Priority: Recent reports (<5 years)

2. **Satellite/Aerial Imagery** (Already have NAIP)
   - AI Detection with YOLOv8
   - Confidence scores from model

3. **GIS Database** (Verizon pole inventory)
   - Official pole locations
   - Pole metadata

4. **OpenStreetMap** (Currently implemented)
   - Public pole data
   - Community-verified locations

### **Confidence Scoring Algorithm:**

```
Total Confidence = (0.40 × AI_Detection) + (0.30 × Recency) + (0.30 × Spatial_Match)

Where:
- AI_Detection: YOLOv8 confidence (0.0-1.0)
- Recency: 1.0 if <1yr, 0.8 if <3yr, 0.5 if <5yr, 0.2 if >5yr
- Spatial_Match: 1.0 if <2m, 0.8 if <5m, 0.5 if <10m, 0.2 if >10m
```

### **Three-Tier Classification:**

1. **✅ Verified Good** (Auto-Approved)
   - Conditions:
     - Detection matches report coords (<5m distance)
     - High confidence (>0.8)
     - Recent verified status
   - Action: Eliminate from review, mark as compliant

2. **⚠️ In Question** (Human Review Required)
   - Conditions:
     - Mismatch >5m between sources
     - OR low confidence (<0.6)
     - OR conflicting reports
   - Action: Flag for human review in dashboard

3. **🚨 New/Missing** (Field Verification Required)
   - Conditions:
     - AI detections without matching reports
     - OR poles in reports but no detection
   - Action: Escalate for field verification

---

## Implementation Steps

### **Phase 1: Create Mock Multi-Source Data**

Since we don't have real technician reports or GIS data yet, we'll create realistic mock data:

**A. Technician Reports CSV:**
```csv
pole_id,lat,lon,inspection_date,status,inspector,notes
TECH-001,40.2732,-76.8867,2024-03-15,verified,John Doe,Good condition
TECH-002,40.2735,-76.8870,2022-06-20,needs_repair,Jane Smith,Leaning 5 degrees
TECH-003,40.2740,-76.8875,2020-01-10,verified,Bob Johnson,Old report
```

**B. GIS Inventory CSV:**
```csv
pole_id,lat,lon,pole_type,voltage,material,last_updated
GIS-A001,40.2732,-76.8867,distribution,7200,wood,2023-12-01
GIS-A002,40.2738,-76.8872,transmission,138000,steel,2024-01-15
```

**C. AI Detections (From YOLOv8):**
```csv
detection_id,lat,lon,confidence,image_source
DET-001,40.2733,-76.8868,0.954,NAIP_tile_42
DET-002,40.2735,-76.8871,0.823,NAIP_tile_42
DET-003,40.2741,-76.8876,0.456,NAIP_tile_43
```

### **Phase 2: Build Fusion & Scoring Engine**

Create `src/fusion/multi_source_validator.py`:

```python
class MultiSourceValidator:
    def __init__(self):
        self.sources = {
            'osm': load_osm_poles(),
            'tech_reports': load_technician_reports(),
            'gis': load_gis_inventory(),
            'ai_detections': load_ai_detections()
        }

    def calculate_confidence(self, pole):
        # 40% AI detection confidence
        ai_score = pole.get('ai_confidence', 0.0) * 0.40

        # 30% recency score
        recency_score = self.get_recency_score(pole) * 0.30

        # 30% spatial match score
        spatial_score = self.get_spatial_match_score(pole) * 0.30

        return ai_score + recency_score + spatial_score

    def classify_pole(self, pole, confidence):
        if confidence >= 0.8 and pole['spatial_distance'] < 5.0:
            return 'verified'
        elif confidence < 0.6 or pole['spatial_distance'] > 5.0:
            return 'in_question'
        else:
            return 'verified'  # Medium confidence

    def find_missing_poles(self):
        # Poles in reports but not detected
        # OR detections without matching reports
        pass
```

### **Phase 3: Update Backend API**

Add new endpoints to `backend/app/api/v1/`:

**A. `verification.py`:**
```python
@router.get("/verification/summary")
async def get_verification_summary():
    return {
        "total_poles": 1977,
        "verified": 1500,  # 76%
        "in_question": 400,  # 20%
        "missing": 77,      # 4%
        "automation_rate": 0.76
    }

@router.get("/verification/in-question")
async def get_poles_in_question(limit: int = 100):
    # Return poles flagged for human review
    # With reasons: mismatch, low_confidence, conflicting_data
    pass

@router.get("/verification/missing")
async def get_missing_poles():
    # Return poles needing field verification
    pass
```

### **Phase 4: Update Dashboard**

**A. Status Breakdown (3 Categories):**
```tsx
// Update Dashboard.tsx
<div>Auto-Approved: 1500 (76%)</div>
<div>Needs Review: 400 (20%)</div>
<div>Needs Field Visit: 77 (4%)</div>
```

**B. Review Queue Page:**
- Filter by issue type: mismatch, low_confidence, conflicting
- Show reason for flagging
- Display multiple data sources side-by-side
- Actions: Approve, Reject, Request Field Visit

### **Phase 5: Map View Enhancements**

**A. Color Code by Classification:**
```tsx
- Green: Verified (confidence >0.8, match <5m)
- Yellow: In Question (needs review)
- Red: Missing (needs field visit)
```

**B. Show Data Source Info:**
```tsx
// In modal
Data Sources:
✓ OSM: 40.2732, -76.8867
✓ Tech Report (2024-03-15): 40.2733, -76.8868 (1.2m away)
✓ AI Detection (95.4%): 40.2733, -76.8868
⚠ Mismatch: GIS shows 40.2750, -76.8890 (18m away)

Confidence Score: 72% (In Question)
Reason: GIS location mismatch >5m
```

---

## Mock Data Generation

Since we don't have real data yet, let's generate realistic mock data that simulates:

1. **Perfect Matches** (75%): All sources agree, high confidence
2. **Questionable Poles** (20%): Some mismatch or low confidence
3. **Missing/New** (5%): Detected but no reports, or reported but not detected

**Mock Data Script:**
```python
import random
import pandas as pd
from datetime import datetime, timedelta

def generate_mock_multi_source_data():
    base_poles = pd.read_csv('osm_poles_harrisburg_real.csv')

    tech_reports = []
    gis_inventory = []
    ai_detections = []

    for idx, pole in base_poles.iterrows():
        scenario = random.choices(
            ['perfect', 'mismatch', 'missing'],
            weights=[0.75, 0.20, 0.05]
        )[0]

        if scenario == 'perfect':
            # All sources match
            tech_reports.append({
                'pole_id': f'TECH-{idx}',
                'lat': pole['lat'] + random.uniform(-0.00001, 0.00001),  # <1m
                'lon': pole['lon'] + random.uniform(-0.00001, 0.00001),
                'inspection_date': (datetime.now() - timedelta(days=random.randint(0, 365))).strftime('%Y-%m-%d'),
                'status': 'verified',
                'confidence_tech': 0.95
            })

            ai_detections.append({
                'detection_id': f'DET-{idx}',
                'lat': pole['lat'],
                'lon': pole['lon'],
                'confidence': random.uniform(0.85, 0.99)
            })

        elif scenario == 'mismatch':
            # Create mismatch (>5m) or old report
            tech_reports.append({
                'pole_id': f'TECH-{idx}',
                'lat': pole['lat'] + random.uniform(-0.0001, 0.0001),  # ~10m
                'lon': pole['lon'] + random.uniform(-0.0001, 0.0001),
                'inspection_date': (datetime.now() - timedelta(days=random.randint(1800, 2500))).strftime('%Y-%m-%d'),
                'status': 'needs_review'
            })

            ai_detections.append({
                'detection_id': f'DET-{idx}',
                'lat': pole['lat'],
                'lon': pole['lon'],
                'confidence': random.uniform(0.50, 0.75)  # Low confidence
            })

        else:  # missing
            # Detection but no tech report (new pole)
            ai_detections.append({
                'detection_id': f'DET-{idx}',
                'lat': pole['lat'],
                'lon': pole['lon'],
                'confidence': random.uniform(0.70, 0.90)
            })
            # No tech report for this pole

    return tech_reports, gis_inventory, ai_detections
```

---

## Expected Dashboard After Implementation

### **Summary Metrics:**
```
Total Poles: 1,977
├─ Verified Good: 1,500 (76%) ✓
├─ In Question: 400 (20%) ⚠️
└─ Needs Field Visit: 77 (4%) 🚨

Automation Rate: 76%
Cost Savings: $28,755 (1,500 poles × $19.17 avg)
Human Review Queue: 400 poles
```

### **Review Queue Page:**
```
Showing 400 poles requiring review:

[Pole OSM-1777378246]
Issue: Location Mismatch
├─ OSM: 40.2732, -76.8867
├─ Tech Report (2022): 40.2750, -76.8890 (18m away) ⚠️
├─ AI Detection: 40.2733, -76.8868 (95.4%)
└─ Confidence: 62% (needs review)

Actions: [✓ Approve OSM] [✓ Approve Tech] [🚨 Request Field Visit]

[Pole OSM-1777378247]
Issue: Low AI Confidence
├─ OSM: 40.3466, -76.7730
├─ Tech Report: None
├─ AI Detection: 40.3466, -76.7731 (54.3%) ⚠️
└─ Confidence: 51% (low detection)

Actions: [✓ Approve] [✗ Reject Detection] [🚨 Field Visit]
```

---

## Next Steps

1. **Create mock multi-source data** (tech_reports.csv, gis_inventory.csv, ai_detections.csv)
2. **Build fusion engine** (multi_source_validator.py)
3. **Update backend API** with verification endpoints
4. **Update Dashboard** to show 3 categories
5. **Build Review Queue page** with filtering and actions
6. **Update Map** to color-code by classification

**Would you like me to implement this multi-source verification system now?**
