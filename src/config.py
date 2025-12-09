"""
Configuration settings for PoleLocations system
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
IMAGERY_DIR = DATA_DIR / "imagery"
TRAINING_DATA_DIR = DATA_DIR / "training"

MODELS_DIR = PROJECT_ROOT / "models"
CHECKPOINTS_DIR = MODELS_DIR / "checkpoints"
EXPORTS_DIR = MODELS_DIR / "exports"
THRESHOLD_EXPORT_PATH = EXPORTS_DIR / "detection_thresholds.json"

OUTPUTS_DIR = PROJECT_ROOT / "outputs"
REPORTS_DIR = OUTPUTS_DIR / "reports"
EXPORTS_OUTPUT_DIR = OUTPUTS_DIR / "exports"
LOGS_DIR = OUTPUTS_DIR / "logs"

# Geospatial Configuration
CRS_STANDARD = "EPSG:4326"  # WGS84 lat/lon
BUFFER_DISTANCE_METERS = 15  # Buffer zone around poles
MATCH_THRESHOLD_METERS = 10  # Maximum distance for spatial matching

# East Coast Bounding Box (NY to VA)
EAST_COAST_BBOX = {
    "minx": -80.0,  # Western edge
    "miny": 36.5,   # Southern edge (VA)
    "maxx": -71.0,  # Eastern edge
    "maxy": 45.0    # Northern edge (NY/New England)
}

# AI Model Configuration
MODEL_TYPE = "yolov8l"  # YOLOv8 large (enterprise grade accuracy)
MODEL_INPUT_SIZE = 640
# Minimum confidence for detections
CONFIDENCE_THRESHOLD = float(os.getenv("DETECTION_CONFIDENCE_THRESHOLD", "0.25"))
IOU_THRESHOLD = float(os.getenv("DETECTION_IOU_THRESHOLD", "0.45"))  # Intersection over Union for NMS

# Detection geospatial calibration (degrees)
DETECTION_LAT_OFFSET_DEG = float(os.getenv("DETECTION_LAT_OFFSET_DEG", "0.0"))
DETECTION_LON_OFFSET_DEG = float(os.getenv("DETECTION_LON_OFFSET_DEG", "0.0"))

# Classification Thresholds
VERIFIED_DISTANCE_THRESHOLD = 5.0  # meters
VERIFIED_CONFIDENCE_THRESHOLD = 0.8
IN_QUESTION_CONFIDENCE_THRESHOLD = 0.6

# Detection Context Filtering
FILTER_MAX_ROAD_DISTANCE_M = float(os.getenv("FILTER_MAX_ROAD_DISTANCE_M", "120.0"))
FILTER_MIN_SURFACE_ELEV_M = float(os.getenv("FILTER_MIN_SURFACE_ELEV_M", "0.0"))
FILTER_NDVI_LOWER = float(os.getenv("FILTER_NDVI_LOWER", "-0.3"))
FILTER_NDVI_UPPER = float(os.getenv("FILTER_NDVI_UPPER", "0.75"))
FILTER_DROP_FAILURES = True  # Always drop failures in enterprise mode

# Confidence Scoring Weights
WEIGHT_IMAGERY = 0.4
WEIGHT_RECENCY = 0.3
WEIGHT_DISTANCE = 0.3

# Report Recency Weights
RECENCY_WEIGHTS = {
    "under_1yr": 1.0,
    "1_to_3yr": 0.8,
    "3_to_5yr": 0.5,
    "over_5yr": 0.2
}

# Imagery Configuration
NAIP_S3_BUCKET = "usgs-naip"
IMAGERY_TILE_SIZE = 1024  # pixels (1km² at 1m resolution)
IMAGERY_RESOLUTION = 1.0  # meters per pixel (NAIP standard)

# AWS Configuration (for NAIP access)
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", None)
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", None)

# Training Configuration
TRAIN_VAL_SPLIT = 0.9  # 90% train, 10% validation
BATCH_SIZE = 16
EPOCHS = 100
EARLY_STOPPING_PATIENCE = 20

# Dashboard Configuration
DASHBOARD_HOST = "localhost"
DASHBOARD_PORT = 8501
DASHBOARD_TITLE = "PoleLocations - Verizon Pole Verification System"

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Performance Configuration
MAX_WORKERS = os.cpu_count() or 4  # For parallel processing
CHUNK_SIZE = 1000  # Poles to process per batch

# Create directories if they don't exist
for directory in [
    DATA_DIR, RAW_DATA_DIR, PROCESSED_DATA_DIR, IMAGERY_DIR, TRAINING_DATA_DIR,
    MODELS_DIR, CHECKPOINTS_DIR, EXPORTS_DIR,
    OUTPUTS_DIR, REPORTS_DIR, EXPORTS_OUTPUT_DIR, LOGS_DIR
]:
    directory.mkdir(parents=True, exist_ok=True)
