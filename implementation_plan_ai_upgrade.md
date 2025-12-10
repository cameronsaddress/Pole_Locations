# Operations Center Intelligence Upgrade Plan

## Objective
Transition "Operational Intelligence" (Lean, Vegetation, Damage) from frontend heuristics to a robust, AI-driven pipeline using Multi-Class Computer Vision.

---

## 1. Model Strategy: Multi-Class Detection
Instead of detecting a generic "Pole" and guessing its status, we will retrain the YOLOv8 model to strictly identify specific conditions as distinct classes.

### Target Classes
1.  `0: pole_good`: Standard vertical pole, clear clearance.
2.  `1: pole_leaning`: Pole listing > 10 degrees from vertical.
3.  `2: pole_vegetation`: Pole structure obscured > 30% by canopy.
4.  `3: pole_damage`: Visible crossarm misalignment or broken insulators.

### Advantages
*   **Speed**: Single-stage inference (no need to crop & classify separately).
*   **Context**: YOLO learns context (e.g., leaves touching the pole) better than a cropped classifier might.

---

## 2. Dataset Refinement (Action Required)
To support these classes, we must refine our training data.

### Labelling Protocol
*   **Existing Labels**: Remap all current "Poles" to `pole_good` by default.
*   **Active Learning Loop**:
    1.  Run the current model on the dataset.
    2.  Filter for "low confidence" detections (often implies occlusion/lean).
    3.  Human Reviewer (User) re-tags these specific edge cases as `leaning`, `vegetation`, or `damage`.
    4.  Retrain model.

---

## 3. Pipeline Implementation

### A. Update `pole_detector.py`
The current `detect()` function already captures `class` and `class_name`. We need to ensure:
1.  The model is initialized with the correct `names` mapping.
2.  The `detect()` output prioritizes specific defects (e.g., if a box overlaps a "good" and "leaning" prediction, prioritize "leaning").

### B. Update `run_pilot.py`
*   Modify the CSV export logic to include the `class_name` column.
*   Map model classes to the Operational Status:
    *   `pole_good` -> Status: **Verified**, Issue: None.
    *   `pole_leaning` -> Status: **Critical**, Issue: **Severe Lean**.
    *   `pole_vegetation` -> Status: **Flagged**, Issue: **Veg Encroachment**.
    *   `pole_damage` -> Status: **Flagged**, Issue: **Equipment Check**.

### C. Update Backend `main.py`
*   Remove the "Phase 1 Heuristics" entirely.
*   Read `row['class_name']` directly from the CSV.
*   Hydrate the `search_issues` and `financial_impact` based on the *confirmed* class from the model.

---

## 4. Execution Step-by-Step

1.  **Modify `PoleDetector`**: Ensure it explicitly handles class names mapping and passes them to detections.
2.  **Update `run_pilot`**: Ensure CSV output captures `classification` column from inference.
3.  **Simulate Training**: Since we don't have the labeled dataset yet, we will:
    *   Create a "Mock Model" wrapper that *randomly assigns these classes* during the `detect()` phase for demonstration purposes, proving the pipeline works end-to-end.
    *   (In production, you would drop in the real `.pt` file).
4.  **Finalize Backend**: Switch `load_real_assets` to trust the CSV input.

