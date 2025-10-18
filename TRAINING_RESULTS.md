# YOLOv8 Pole Detection Training Results

**Date:** October 14, 2025, 9:23 PM
**Status:** ⚠️ Training completed but low performance - Issue identified

---

## Training Summary

### Dataset
- **Source**: 100% REAL data (OSM poles + NAIP imagery)
- **Training images**: 253
- **Validation images**: 64
- **Total**: 317 real pole crops
- **Image size**: 100×100 pixels (resized to 128×128 by YOLOv8)
- **Resolution**: 0.6 meters/pixel

### Model Configuration
- **Architecture**: YOLOv8n (nano)
- **Parameters**: 3,005,843
- **Optimizer**: Adam
- **Initial epochs**: 100
- **Actual epochs**: 61 (early stopped at epoch 11)
- **Training time**: 7.6 minutes (0.126 hours)
- **Device**: CPU (Apple M1)

### Performance Metrics

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Precision | **3.2%** | 85%+ | ❌ Low |
| Recall | **14.1%** | 80%+ | ❌ Low |
| mAP50 | **1.7%** | 70%+ | ❌ Low |
| mAP50-95 | **0.6%** | 50%+ | ❌ Low |

**Result**: ❌ Model performance is too low for production use

---

## Root Cause Analysis

### Issue Identified: **Poles Too Small**

**Annotation Statistics:**
- Average box size: **5.0 × 8.0 pixels**
- In 100×100 pixel images: Only 0.4% of image area
- In 128×128 pixel images (YOLOv8 auto-resize): Even smaller

**Why This Matters:**
- YOLOv8 struggles with objects **<10×10 pixels**
- Tiny objects get lost during downsampling in CNN layers
- Detection heads expect larger objects for reliable localization

### Contributing Factors

1. **Small Crop Size**
   - Used: 100×100 pixel crops
   - Problem: Poles are only 5-8 pixels in this size
   - Industry standard for small objects: 256×256 or 512×512

2. **NAIP Resolution**
   - Resolution: 0.6 meters/pixel
   - Pole width: ~0.3 meters (typical utility pole)
   - Result: Pole = 0.5 pixels wide in original imagery
   - Even in 100×100 crops, poles are barely visible

3. **OSM Coordinate Accuracy**
   - OSM data is crowd-sourced (±5-10m accuracy)
   - Poles may not be perfectly centered in crops
   - Some crops may miss poles entirely

---

## Solutions & Recommendations

### ✅ Option 1: Increase Crop Size (Recommended)
**Extract larger crops to make poles more visible**

```python
# Current
crop_size = 100  # 5×8 pixel poles

# Recommended
crop_size = 256  # 13×20 pixel poles (2.5× larger)
# OR
crop_size = 512  # 26×40 pixel poles (5× larger)
```

**Benefits:**
- Poles become 2.5-5× larger in pixels
- Better for YOLOv8 detection
- More context around poles

**Trade-offs:**
- 6.5× more disk space (256px) or 26× more (512px)
- Slower training

### ✅ Option 2: Higher Resolution Imagery
**Use NAIP's 0.3m or 0.15m resolution instead of 0.6m**

**Benefits:**
- Poles are 2-4× larger in original imagery
- Better detail and visibility

**Trade-offs:**
- May not be available for all areas
- Larger file downloads

### ✅ Option 3: Manual Annotation Review
**Verify that OSM pole coordinates actually contain visible poles**

Create a manual review workflow:
1. Display each crop to human reviewer
2. Confirm pole is visible and centered
3. Adjust bounding box if needed
4. Remove crops with no visible pole

**Benefits:**
- Ensures training data quality
- Removes false positives from OSM data

**Trade-offs:**
- Time-consuming (317 images to review)
- Requires human labor

### ✅ Option 4: Different Detection Approach
**Use segmentation or keypoint detection instead of bounding boxes**

For very small objects, sometimes pixel-wise segmentation works better:
- YOLOv8-seg (segmentation variant)
- U-Net for pole pixel classification
- Simple blob detection on preprocessed imagery

---

## Next Steps (Recommended Order)

### 1. Re-extract with Larger Crops
```bash
# Modify extract_pole_crops.py to use 256×256 crops
python src/utils/extract_pole_crops.py --crop-size 256

# Prepare dataset
python src/utils/prepare_yolo_dataset.py

# Retrain
python src/detection/train_pole_model.py
```

### 2. Manual Quality Check
```bash
# Inspect sample crops
python src/utils/inspect_training_samples.py

# Review sample_inspection.png to verify poles are visible
open data/processed/pole_training_dataset/sample_inspection.png
```

### 3. Adjust Bounding Box Size
If poles are larger in 256×256 crops, update annotation script:
```python
# In extract_pole_crops.py, adjust box size
width = 10.0 / crop_size   # 10px instead of 5px
height = 20.0 / crop_size  # 20px instead of 8px
```

### 4. Retrain with Better Parameters
```python
# In train_pole_model.py
epochs = 150  # More epochs
batch_size = 8  # Smaller batch for larger images
img_size = 256  # Match crop size
```

---

## Files Generated

### Model Files
- ✅ [best.pt](models/pole_detector_v1/weights/best.pt) - Best checkpoint (epoch 11)
- ✅ [last.pt](models/pole_detector_v1/weights/last.pt) - Final checkpoint (epoch 61)
- ✅ [pole_detector_real.pt](models/pole_detector_real.pt) - Production model (copy of best.pt)

### Training Visualizations
- ✅ [results.png](models/pole_detector_v1/results.png) - Training curves (242 KB)
- ✅ [confusion_matrix.png](models/pole_detector_v1/confusion_matrix.png) - Confusion matrix (88 KB)
- ✅ [train_batch0.jpg](models/pole_detector_v1/train_batch0.jpg) - Training samples
- ✅ [val_batch0_labels.jpg](models/pole_detector_v1/val_batch0_labels.jpg) - Validation ground truth
- ✅ [val_batch0_pred.jpg](models/pole_detector_v1/val_batch0_pred.jpg) - Validation predictions
- ✅ [sample_inspection.png](data/processed/pole_training_dataset/sample_inspection.png) - Manual inspection

### Logs
- ✅ [training.log](training.log) - Complete training output

---

## Lessons Learned

### ✅ What Worked
1. **Real Data Acquisition**
   - Successfully downloaded NAIP imagery from Microsoft Planetary Computer
   - Successfully retrieved OSM pole coordinates
   - 317 real pole crops extracted with proper CRS transformation

2. **Pipeline Architecture**
   - End-to-end pipeline works correctly
   - Coordinate transformation (EPSG:4326 → EPSG:26918) successful
   - YOLO annotation format correct

3. **Training Infrastructure**
   - YOLOv8 integration successful
   - Early stopping prevented overfitting
   - Model saved and ready for use

### ⚠️ What Didn't Work
1. **Object Scale**
   - 100×100 pixel crops make poles too small (5×8 pixels)
   - YOLOv8 cannot reliably detect objects this small
   - Need 256×256 or larger crops

2. **Resolution Challenge**
   - 0.6m/pixel NAIP resolution barely captures 0.3m wide poles
   - Poles are ~0.5 pixels wide in original imagery
   - Need higher resolution or larger crop context

3. **Dataset Size**
   - 317 images is small for deep learning
   - Typical YOLO datasets have 1,000-10,000+ images
   - Need more coverage area or download additional NAIP tiles

---

## Production Readiness

### Current Status: ❌ NOT READY

**Blocking Issues:**
1. ❌ Precision 3.2% (target: 85%+)
2. ❌ Recall 14.1% (target: 80%+)
3. ❌ Would produce 96.8% false positives
4. ❌ Would miss 85.9% of real poles

**Required Before Production:**
1. ✅ Re-extract with 256×256 or 512×512 crops
2. ✅ Retrain model and achieve >85% precision
3. ✅ Validate on held-out test set
4. ✅ Manual review of predictions
5. ✅ A/B test against human inspectors

---

## Cost-Benefit Analysis

### Current Automation Rate: ~3%
- Only 3.2% of automated verifications would be correct
- 96.8% would require manual review anyway
- **Result**: Model adds no value in current state

### Target Automation Rate: 70-90%
- With improved model (85% precision):
  - 85% of automated verifications correct
  - 15% require manual review
  - **Savings**: $2.55 - $5.10 per pole

### Break-Even Point
- Model becomes useful at >70% precision
- Recommended minimum: 80% precision for production

---

## Commands for Next Iteration

### Re-extract with Larger Crops
```bash
# Edit extract_pole_crops.py, change crop_size to 256
vim src/utils/extract_pole_crops.py

# Re-run extraction
python src/utils/extract_pole_crops.py

# Prepare dataset
python src/utils/prepare_yolo_dataset.py

# Retrain
python src/detection/train_pole_model.py
```

### Monitor Training
```bash
# Watch training progress
tail -f training.log

# Check results
ls -lh models/pole_detector_v1/
```

---

## Conclusion

✅ **Successfully completed first training iteration on 100% REAL data**
- No synthetic or mock data used
- Real NAIP satellite imagery
- Real OSM pole coordinates
- Complete training pipeline functional

⚠️ **Performance too low for production use**
- Root cause: Poles too small (5×8 pixels)
- Solution: Re-extract with 256×256 crops
- Expected improvement: 2.5× larger poles → 60-80% better detection

🎯 **Next Action: Increase crop size and retrain**

The infrastructure is solid. We just need to adjust the scale to make poles more visible to the neural network.
