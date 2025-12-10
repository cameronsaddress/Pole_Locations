# Operations Center & Real Intelligence Implementation Plan

## Objective
Convert the "Command Center" dashboard from a mock visualization into a fully functional, data-driven Operations Center powered by real AI inference. All metrics, feeds, and interactions must stem from the actual asset database and computer vision analysis.

---

## 1. AI & Computer Vision Strategy ("Real Intelligence")

To display specific issues like "Severe Lean", "Vegetation Encroachment", or "Rust", we cannot rely on the current generic "Pole" detection model. We must implement a multi-stage inference pipeline.

### A. Defect Detection Classes
We need to expand the YOLOv8 model (or train a secondary Classifier model) to detect the following specific classes/attributes:
1.  **Grid Assets**: `Pole`, `Transformer`, `Insulator`, `Crossarm`.
2.  **Defects/Anomalies**:
    *   `leaning_pole` (Geometric Inference or bbox aspect ratio).
    *   `vegetation_encroachment` (Segmentation mask overlap or specific class).
    *   `damaged_insulator` (Visual defect).
    *   `rust_corrosion` (Texture/color analysis).

### B. "Grid Health" Scoring Algorithm
Instead of a hardcoded "99.8%", we will implement a live scoring algorithm:
*   **Formula**: `Grid Health = 100 - (Weighted Defect Score / Total Assets)`
*   **Weights**:
    *   Critical Lean: 10 pts
    *   Veg Encroachment: 5 pts
    *   Rust: 1 pt

### C. Financial Modeling (ROI)
*   **Preventative Savings**: Calculated dynamically based on detected defects.
    *   *Logic*: Detected "Vegetation Encroachment" (Cost to trim: $200) vs "Outage/Fire from Veg" (Cost: $50,000).
    *   *Display*: Sum of avoided risk costs for all "Verified" detections.

---

## 2. Backend Architecture (FastAPI + Python)

### A. New API Endpoints
We need to expose the operational data to the frontend `CommandCenter`.

1.  **`GET /api/v2/ops/metrics`**
    *   Returns: `{ total_assets, grid_health, critical_anomalies_count, projected_savings }`
    *   Source: Live aggregation of the DB.

2.  **`GET /api/v2/ops/feed/anomalies`**
    *   Returns: List of assets specifically flagged with `status="CRITICAL"` or `issue_type != null`.
    *   Usage: Powers the "Satellite Intel Feed" in the Command Center.

3.  **`GET /api/v2/ops/audit-log`**
    *   Returns: Time-sorted stream of recent model inferences (Verified vs Flagged).

### B. Database Schema Expansion
Update the `Asset` model to include:
```python
class Asset(BaseModel):
    id: str
    issues: List[str] = [] # e.g. ["lean", "vegetation"]
    health_score: float # 0.0 to 1.0
    last_audit: datetime
    financial_impact: float # Calculated savings
```

---

## 3. Frontend Implementation ("Clickable Reality")

### A. Interactive Command Center
The "Satellite Intel Feed" currently cycles mock locations. It will be updated to:
1.  **Fetch**: Load real assets with detected issues from `/api/v2/ops/feed/anomalies`.
2.  **Visualize**: Show the *actual* satellite image of that asset.
3.  **Interact**: Clicking the feed opens the **Expanded 3D Inspection Modal** (LiveMap3D view) for that specific asset.

### B. Drill-Down Metrics
Each corporate stat card must be clickable and route to a filtered view of the Data Assets table.
1.  **Click "Critical Anomalies" (3)** -> Routes to `/assets?status=critical`.
2.  **Click "Total Assets"** -> Routes to `/assets`.
3.  **Click "Grid Health"** -> Opens a new "Analytics/Reports" modal or page.

### C. Live Audit Log
1.  Connect to a WebSocket or Polling hook to show inferences *as they happen* in the backend.
2.  Clicking a log entry opens the Asset Detail view (Drawer/Modal).

---

## 4. Execution Steps

### Phase 1: Data Structure & API (Day 1)
- [ ] Modify Backend `Asset` schema to support `issues` and `health_score`.
- [ ] Implement `calculate_grid_health()` helper function.
- [ ] Create `/api/v2/ops/*` endpoints backed by real DB queries.

### Phase 2: AI Inference Upgrade (Day 1-2)
- [ ] **Option A (Quick)**: Update `pole_detector.py` to add heuristic "mock" inferences (e.g., random "Lean" based on aspect ratio) to simulate data flow until model training is complete.
- [ ] **Option B (Real)**: Collect dataset for "Leaning Poles" and "Vegetation". Fine-tune YOLOv8 model.
- [ ] **Action**: We will start with **Option A (Heuristic)** to validate the pipeline, then swap in the trained model (Option B).

### Phase 3: Frontend Wiring (Day 2)
- [ ] Replace `CommandCenter.tsx` mock `LOCATIONS` with `useQuery` fetch from API.
- [ ] Make all Command Center elements `onClick` navigable.
- [ ] Update `Dashboard.tsx` to fetch real operational stats.

