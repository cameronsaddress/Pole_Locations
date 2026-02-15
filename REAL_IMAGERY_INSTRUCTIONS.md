# Real Satellite Imagery Download Instructions

**Status:** Google Earth Engine authentication initiated (awaiting browser completion)

## What Just Happened

1. ✅ Installed Earth Engine API (`earthengine-api`, `geemap`)
2. ✅ Installed SentinelSat for Sentinel-2 imagery
3. ✅ Created download script: `src/utils/download_real_imagery.py`
4. 🔄 **IN PROGRESS**: Google Earth Engine OAuth authentication

## Next Steps (After Browser Authentication Completes)

### Option 1: Google Earth Engine (RECOMMENDED - Best Quality)

**Once authentication completes in your browser:**

```bash
# Activate environment
source venv/bin/activate

# Download real NAIP imagery (1m resolution)
python3 src/utils/download_real_imagery.py
```

This will download:
- **NAIP imagery** (1 meter/pixel) from Harrisburg, PA region
- **5 square kilometers** coverage
- **RGB bands** for pole detection
- **GeoTIFF format** ready for AI training

### Option 2: Manual Download from Box.com (NO LOGIN REQUIRED)

If Earth Engine fails, download directly:

1. **Visit:** https://nrcs.app.box.com/v/naip
2. **Navigate to:** `pa` folder → `2021` folder
3. **Download:** Any `.tif` files (each is ~14MB, covers ~3.75 x 3.75 miles)
4. **Save to:** `./PoleLocations/data/imagery/`
5. Download 2-3 files to cover 5 square miles

### Option 3: USGS EarthExplorer (FREE SIGNUP)

1. **Register (free):** https://earthexplorer.usgs.gov/
2. **Search:** "Harrisburg, PA" or coordinates `40.2732, -76.8867`
3. **Datasets:**
   - Click "Aerial Imagery"
   - Select "NAIP"
   - Choose year 2021 or 2020
4. **Select tiles** covering ~5 square miles
5. **Download:** GeoTIFF format
6. **Place in:** `./PoleLocations/data/imagery/`

## What Happens After We Get Real Imagery

### 1. Extract Pole Locations (Script Ready)
```bash
python3 src/utils/extract_poles_from_imagery.py
```
- Uses our 8,852 processed pole coordinates
- Extracts 100x100 pixel crops around each location
- Creates training dataset

### 2. Label Poles (Using LabelImg)
```bash
pip install labelImg
labelImg data/training/images data/training/labels
```
- Manually verify/adjust pole bounding boxes
- Need ~1,000 labeled images minimum
- Takes 2-3 hours

### 3. Train YOLOv8 Model
```bash
python3 src/detection/train_model.py
```
- Trains on labeled pole dataset
- 100 epochs (~2-4 hours on CPU, 30 min on GPU)
- Targets 85%+ precision

### 4. Run Full Detection Pipeline
```bash
python3 run_pilot.py --with-real-detections
```
- Runs YOLOv8 on all imagery
- Matches with historical records
- Generates final results

## Expected Results with Real Data

| Metric | Current (Simulated) | With Real Imagery |
|--------|---------------------|-------------------|
| Automated Verification | 1.2% | **70-90%** |
| Review Queue | 77.1% | **10-30%** |
| Detection Accuracy | N/A | **85%+** |
| False Positives | N/A | **<5%** |

## Technical Details

### NAIP Imagery Specs
- **Resolution:** 1 meter/pixel (60cm in some areas)
- **Bands:** RGB (Red, Green, Blue) + NIR (Near-Infrared)
- **Coverage:** Updated every 2-3 years
- **Format:** GeoTIFF with embedded georeferencing
- **File Size:** ~10-50MB per tile
- **Coverage per tile:** ~3.75 x 3.75 miles

### Sentinel-2 Specs (Alternative)
- **Resolution:** 10 meters/pixel (RGB bands)
- **Bands:** 13 bands including RGB, NIR, SWIR
- **Coverage:** Global, updated every 5 days
- **Format:** SAFE or GeoTIFF
- **File Size:** ~1GB per scene
- **Pros:** Free, frequent updates, no signup
- **Cons:** Lower resolution (harder for pole detection)

## Current Project Status

✅ **Completed:**
- Full pipeline (ingestion, fusion, classification)
- Dashboard (5 pages, full UI)
- Data processing (8,852 poles ready)
- AI framework (YOLOv8 integrated)
- Export system (CSV, JSON, GeoJSON)

🔄 **In Progress:**
- Real imagery download (Earth Engine authenticating)

⏳ **Pending Real Imagery:**
- Model training
- Actual pole detection
- Accuracy validation
- Final results with 70-90% automation

## Troubleshooting

### If Earth Engine Authentication Fails

1. **Check browser:** Look for Google auth page
2. **Accept permissions:** Allow Earth Engine access
3. **Copy token:** Should auto-save after accepting
4. **Re-run:** `python3 src/utils/download_real_imagery.py`

### If Download is Slow

NAIP files are large (10-50MB each). Download will take 5-10 minutes per tile.

### If No Imagery Available for PA 2021

Try alternate years:
- 2020: Good coverage
- 2019: Available
- 2022: Most recent (may not be complete)

## Contact for Issues

- **Earth Engine Signup:** https://earthengine.google.com/signup
- **USGS Support:** https://www.usgs.gov/faqs
- **Box.com NAIP:** https://nrcs.app.box.com/v/naip

---

**Last Updated:** October 14, 2025
**Status:** Awaiting Earth Engine authentication completion in browser
