"""
YOLOv8-based utility pole detection from aerial/satellite imagery
"""
import logging
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import sys
import types
import numpy as np
import pandas as pd
import torch
import rasterio
from rasterio.windows import Window
import rasterio.errors
from PIL import Image

try:
    from transformers import pipeline
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False
    logging.getLogger(__name__).warning("transformers library not found. Zero-shot classification disabled. Install with `pip install transformers`")

if "cv2.dnn" not in sys.modules:
    cv2_dnn = types.ModuleType("cv2.dnn")
    cv2_dnn.DictValue = int  # type: ignore[attr-defined]
    sys.modules["cv2.dnn"] = cv2_dnn

import cv2

if not hasattr(cv2, "imshow"):
    # Ultralytics expects GUI-centric OpenCV functions; provide harmless stubs for headless builds.
    def _headless_imshow(*_args, **_kwargs):
        logging.getLogger(__name__).debug("cv2.imshow called in headless mode; ignoring.")

    cv2.imshow = _headless_imshow  # type: ignore[attr-defined]
    cv2.namedWindow = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
    cv2.waitKey = lambda *_args, **_kwargs: -1  # type: ignore[attr-defined]
    cv2.destroyAllWindows = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]

from ultralytics import YOLO
sys.path.append(str(Path(__file__).parent.parent))
from config import (  # type: ignore
    MODEL_TYPE,
    CONFIDENCE_THRESHOLD,
    IOU_THRESHOLD,
    CHECKPOINTS_DIR,
    TRAINING_DATA_DIR,
    MODEL_INPUT_SIZE,
    THRESHOLD_EXPORT_PATH,
    MODELS_DIR,
    DETECTION_LAT_OFFSET_DEG,
    DETECTION_LON_OFFSET_DEG,
    OUTPUTS_DIR,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PoleDetector:
    """
    Detect utility poles in imagery using YOLOv8
    """

    def __init__(
        self,
        model_path: Optional[Path] = None,
        confidence: Optional[float] = None,
        iou: Optional[float] = None,
        augment: bool = True
    ):
        """
        Initialize pole detector

        Args:
            model_path: Path to trained model weights (uses pretrained if None)
            confidence: Minimum confidence threshold for detections
            augment: Enable Test Time Augmentation (TTA) for higher accuracy
        """
        overrides = self._load_threshold_overrides()

        self.confidence = (
            confidence
            if confidence is not None
            else overrides.get("confidence", CONFIDENCE_THRESHOLD)
        )
        self.iou = (
            iou
            if iou is not None
            else overrides.get("iou", IOU_THRESHOLD)
        )
        self.lat_offset_deg = overrides.get("lat_offset_deg", DETECTION_LAT_OFFSET_DEG)
        self.lon_offset_deg = overrides.get("lon_offset_deg", DETECTION_LON_OFFSET_DEG)
        self.augment = augment

        resolved_model_path = self._resolve_model_path(model_path)

        if resolved_model_path is not None:
            logger.info("Loading custom model from %s", resolved_model_path)
            self.model = YOLO(str(resolved_model_path))
        else:
            logger.info("Loading pretrained %s model", MODEL_TYPE)
            self.model = YOLO(f'{MODEL_TYPE}.pt')

        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        if torch.cuda.is_available():
            logger.info("Using GPU: %s", torch.cuda.get_device_name(0))
        
        # Initialize Zero-Shot Classifier
        self.classifier = None
        self.classification_labels = [
            "clean utility pole",
            "utility pole with heavy vegetation encroachment", 
            "leaning utility pole", 
            "broken or damaged utility pole crossarm",
            "rusted utility pole transformer",
            "bird nest on utility pole"
        ]
        
        if HAS_TRANSFORMERS:
            try:
                logger.info("Loading CLIP model for zero-shot classification...")
                # device=0 for GPU, -1 for CPU
                clf_device = 0 if torch.cuda.is_available() else -1
                self.classifier = pipeline(
                    "zero-shot-image-classification", 
                    model="openai/clip-vit-base-patch32",
                    device=clf_device
                )
                logger.info("CLIP model loaded successfully.")
            except Exception as e:
                logger.warning(f"Failed to load CLIP model: {e}")
            try:
                device_name = torch.cuda.get_device_name(0)
            except Exception:  # pragma: no cover - defensive
                device_name = "CUDA device"
            logger.info("Using GPU acceleration on %s", device_name)
        else:
            logger.info("CUDA not available; running detector on CPU.")

        try:
            self.model.to(self.device)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Failed to move model to %s (%s). Falling back to CPU.",
                self.device,
                exc,
            )
            self.device = "cpu"

        logger.info(
            "Model loaded. Confidence threshold: %.3f | IoU threshold: %.3f | TTA: %s",
            self.confidence,
            self.iou,
            self.augment
        )
        if self.lat_offset_deg or self.lon_offset_deg:
            logger.info(
                "Geospatial calibration offsets applied: Δlat=%.6f°, Δlon=%.6f°",
                self.lat_offset_deg,
                self.lon_offset_deg,
            )

    def train(self, data_yaml: Path, epochs: int = 100, batch_size: int = 16,
              img_size: int = 640, patience: int = 20) -> Path:
        """
        Train YOLOv8 model on pole dataset

        Args:
            data_yaml: Path to dataset configuration YAML
            epochs: Number of training epochs
            batch_size: Batch size for training
            img_size: Input image size
            patience: Early stopping patience

        Returns:
            Path to best model weights
        """
        logger.info("=" * 60)
        logger.info(f"TRAINING YOLOV8 MODEL ON POLE DATASET")
        logger.info("=" * 60)
        logger.info(f"  Dataset: {data_yaml}")
        logger.info(f"  Epochs: {epochs}")
        logger.info(f"  Batch size: {batch_size}")
        logger.info(f"  Image size: {img_size}")
        logger.info(f"  Patience: {patience}")
        logger.info("=" * 60)

        # Train model
        results = self.model.train(
            data=str(data_yaml),
            epochs=epochs,
            batch=batch_size,
            imgsz=img_size,
            patience=patience,
            project=str(CHECKPOINTS_DIR),
            name='pole_detection',
            pretrained=True,
            verbose=True,
            device=self.device
        )

        # Get best weights path
        best_weights = CHECKPOINTS_DIR / 'pole_detection' / 'weights' / 'best.pt'

        logger.info("=" * 60)
        logger.info("TRAINING COMPLETE")
        logger.info(f"  Best weights: {best_weights}")
        logger.info("=" * 60)

        return best_weights

    def detect(self, image_path: Path) -> List[Dict]:
        """
        Detect poles in a single image

        Args:
            image_path: Path to image file

        Returns:
            List of detections with bounding boxes and confidence scores
        """
        # Load image for cropping
        # Only load if we have a classifier to use
        img = None
        if self.classifier:
            img = cv2.imread(str(image_path))
            if img is not None:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        results = self.model.predict(
            source=str(image_path),
            conf=self.confidence,
            iou=self.iou,
            augment=self.augment,
            verbose=False,
            device=self.device
        )

        detections = []

        for result in results:
            boxes = result.boxes

            for i in range(len(boxes)):
                # Extract box coordinates
                box = boxes.xyxy[i].cpu().numpy()  # [x1, y1, x2, y2]
                conf = float(boxes.conf[i].cpu().numpy())
                cls = int(boxes.cls[i].cpu().numpy())

                # Calculate center and dimensions
                x1, y1, x2, y2 = box
                center_x = (x1 + x2) / 2
                center_y = (y1 + y2) / 2
                width = x2 - x1
                height = y2 - y1
                
                # Default Class Name
                class_name = result.names[cls] if hasattr(result, 'names') else 'utility_pole'

                # --- ZERO-SHOT CLASSIFICATION ---
                if self.classifier and img is not None:
                    # Ensure coordinates are within bounds
                    h, w, _ = img.shape
                    ix1, iy1 = max(0, int(x1)), max(0, int(y1))
                    ix2, iy2 = min(w, int(x2)), min(h, int(y2))
                    
                    if ix2 > ix1 and iy2 > iy1:
                        crop = img[iy1:iy2, ix1:ix2]
                        try:
                            pil_crop = Image.fromarray(crop)
                            # Run classification
                            clip_result = self.classifier(images=pil_crop, candidate_labels=self.classification_labels)
                            # Result is a list of {'label': str, 'score': float}
                            # Get top prediction
                            top_label = clip_result[0]['label']
                            top_score = clip_result[0]['score']
                            
                            # Simple mapping to internal enum/short names
                            if top_score > 0.4: # Threshold for specific defect
                                if "leaning" in top_label:
                                    class_name = "pole_leaning"
                                elif "vegetation" in top_label:
                                    class_name = "pole_vegetation"
                                elif "broken" in top_label or "damaged" in top_label:
                                    class_name = "pole_damage"
                                else:
                                    class_name = "pole_good"
                        except Exception as e:
                            logger.debug(f"Classification failed for box {i}: {e}")

                detection = {
                    'bbox': [float(x1), float(y1), float(x2), float(y2)],
                    'center': [float(center_x), float(center_y)],
                    'dimensions': [float(width), float(height)],
                    'confidence': conf,
                    'class': cls,
                    'class_name': class_name
                }

                detections.append(detection)

        return detections

    @staticmethod
    def _load_threshold_overrides() -> Dict[str, float]:
        """
        Load persisted detection threshold overrides produced by the threshold sweeper.

        Returns:
            dict with optional 'confidence' and 'iou' float values.
        """
        if not THRESHOLD_EXPORT_PATH.exists():
            return {}

        try:
            with THRESHOLD_EXPORT_PATH.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            confidence = data.get("confidence_threshold")
            iou = data.get("iou_threshold")
            overrides: Dict[str, float] = {}
            if isinstance(confidence, (int, float)):
                overrides["confidence"] = float(confidence)
            if isinstance(iou, (int, float)):
                overrides["iou"] = float(iou)
            if overrides:
                logger.info(
                    "Loaded threshold overrides from %s -> %s",
                    THRESHOLD_EXPORT_PATH,
                    overrides,
                )
            return overrides
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Failed to read threshold overrides at %s: %s",
                THRESHOLD_EXPORT_PATH,
                exc,
            )
            return {}

    @staticmethod
    def _resolve_model_path(model_path: Optional[Path]) -> Optional[Path]:
        """
        Determine which model weights to load, preferring fine-tuned checkpoints when available.

        Args:
            model_path: Explicit path provided by the caller.

        Returns:
            Path to weights file or None if we should fall back to the base Ultralytics model.
        """
        candidates: List[Path] = []

        if model_path is not None:
            candidates.append(Path(model_path))

        candidates.extend([
            MODELS_DIR / "yolov8l_v1" / "weights" / "best.pt",
            MODELS_DIR / "pole_detector_v7" / "weights" / "best.pt",
            MODELS_DIR / "pole_detector_v6" / "weights" / "best.pt",
            MODELS_DIR / "pole_detector_v4" / "weights" / "best.pt",
            MODELS_DIR / "pole_detector_real.pt",
        ])

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate

        return None

    def detect_batch(self, image_paths: List[Path], batch_size: int = 8) -> Dict[str, List[Dict]]:
        """
        Detect poles in multiple images (batched for efficiency)

        Args:
            image_paths: List of image paths
            batch_size: Number of images to process in parallel

        Returns:
            Dictionary mapping image paths to detection lists
        """
        logger.info(f"Processing {len(image_paths)} images in batches of {batch_size}")

        all_detections = {}

        # Process in batches
        for i in range(0, len(image_paths), batch_size):
            batch = image_paths[i:i+batch_size]

            results = self.model.predict(
                source=[str(p) for p in batch],
                conf=self.confidence,
                iou=self.iou,
                augment=self.augment,
                verbose=False,
                device=self.device,
                stream=True
            )

            for path, result in zip(batch, results):
                detections = []

                if result.boxes is not None:
                    boxes = result.boxes

                    for j in range(len(boxes)):
                        box = boxes.xyxy[j].cpu().numpy()
                        conf = float(boxes.conf[j].cpu().numpy())
                        cls = int(boxes.cls[j].cpu().numpy())

                        x1, y1, x2, y2 = box
                        center_x = (x1 + x2) / 2
                        center_y = (y1 + y2) / 2

                        detection = {
                            'bbox': [float(x1), float(y1), float(x2), float(y2)],
                            'center': [float(center_x), float(center_y)],
                            'confidence': conf,
                            'class': cls
                        }

                        detections.append(detection)

                all_detections[str(path)] = detections

        logger.info(f"Detected poles in {len(all_detections)} images")
        return all_detections

    def sweep_thresholds(
        self,
        data_yaml: Path,
        confidence_values: List[float],
        iou_values: List[float],
        split: str = "val",
        batch_size: int = 16,
        imgsz: int = MODEL_INPUT_SIZE
    ) -> pd.DataFrame:
        """
        Evaluate detector performance across grids of confidence/IoU thresholds.

        Args:
            data_yaml: Dataset YAML describing validation set.
            confidence_values: List of confidence thresholds to evaluate.
            iou_values: List of IoU thresholds to evaluate.
            split: Dataset split to evaluate (default: val).
            batch_size: Batch size for evaluation.
            imgsz: Image size for evaluation.

        Returns:
            pandas.DataFrame with metrics for each (confidence, IoU) pair.
        """
        results = []
        eval_runs_dir = OUTPUTS_DIR / "threshold_eval"
        eval_runs_dir.mkdir(parents=True, exist_ok=True)

        for conf in confidence_values:
            for iou in iou_values:
                logger.info(
                    "Evaluating thresholds -> confidence: %.3f | IoU: %.3f",
                    conf,
                    iou
                )
                try:
                    eval_results = self.model.val(
                        data=str(data_yaml),
                        split=split,
                        conf=conf,
                        iou=iou,
                        batch=batch_size,
                        imgsz=imgsz,
                        verbose=False,
                        device=self.device,
                        project=str(eval_runs_dir),
                        name=f"conf_{conf:.3f}_iou_{iou:.3f}",
                        exist_ok=True,
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error(
                        "Threshold evaluation failed (conf=%.3f, iou=%.3f): %s",
                        conf,
                        iou,
                        exc
                    )
                    continue

                metrics = getattr(eval_results, "results_dict", None)
                if metrics is None:
                    metrics_obj = getattr(eval_results, "metrics", None)
                    if hasattr(metrics_obj, "results_dict"):
                        metrics = metrics_obj.results_dict
                    elif hasattr(metrics_obj, "dict"):
                        metrics = metrics_obj.dict()
                    else:
                        metrics = {}

                row = dict(metrics)
                row.update({
                    "confidence_threshold": conf,
                    "iou_threshold": iou
                })
                results.append(row)

        return pd.DataFrame(results)

    def pixel_to_latlon(self, pixel_coords: Tuple[float, float],
                        image_transform, crs) -> Tuple[float, float]:
        """
        Convert pixel coordinates to lat/lon using image geotransform

        Args:
            pixel_coords: (x, y) pixel coordinates
            image_transform: Rasterio affine transform
            crs: Coordinate reference system

        Returns:
            (lat, lon) coordinates in EPSG:4326
        """
        from rasterio.warp import transform as warp_transform

        # Convert pixel to image CRS coordinates
        x, y = pixel_coords
        lon, lat = image_transform * (x, y)

        # If not already in EPSG:4326, transform
        if crs != 'EPSG:4326':
            lon, lat = warp_transform(crs, 'EPSG:4326', [lon], [lat])
            lon, lat = lon[0], lat[0]

        lat += self.lat_offset_deg
        lon += self.lon_offset_deg

        return lat, lon

    @staticmethod
    def _approx_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Approximate planar distance between two lat/lon points in meters."""
        lat_m = (lat2 - lat1) * 111_000
        lon_m = (lon2 - lon1) * 85_000  # Approx at Harrisburg latitude
        return (lat_m ** 2 + lon_m ** 2) ** 0.5

    def detect_tiles(self, tile_paths: List[Path], crop_size: int = 640,
                     stride: int = 512, duplicate_threshold_m: float = 6.0) -> List[Dict]:
        """
        Run detection across large GeoTIFF tiles using a sliding window.

        Args:
            tile_paths: List of NAIP tile paths.
            crop_size: Size of inference window in pixels.
            stride: Sliding window stride in pixels.
            duplicate_threshold_m: Suppress detections within this distance.

        Returns:
            List of detection dictionaries with lat/lon + confidence.
        """
        detections: List[Dict] = []
        seen_coords: List[Tuple[float, float]] = []
        total_windows = 0

        logger.info(f"Running full-tile detection on {len(tile_paths)} tiles "
                    f"(crop={crop_size}px, stride={stride}px)")

        for tile_path in tile_paths:
            with rasterio.open(tile_path) as src:
                width, height = src.width, src.height
                transform = src.transform
                crs = src.crs

                logger.info(f"[Tile] {tile_path.name}: {width}x{height}px, CRS={crs}")

                row = 0
                while row < height:
                    col = 0
                    while col < width:
                        window = Window(col, row,
                                        min(crop_size, width - col),
                                        min(crop_size, height - row))
                        try:
                            data = src.read([1, 2, 3], window=window)
                        except rasterio.errors.RasterioIOError as err:
                            logger.warning(f"[Tile] {tile_path.name} window "
                                           f"({col},{row},{window.width},{window.height}) "
                                           f"failed to read: {err}")
                            col += stride
                            continue
                        if data.size == 0:
                            col += stride
                            continue

                        # Skip blank/low-information windows to save inference
                        if data.mean() < 12:
                            col += stride
                            continue

                        image = np.transpose(data, (1, 2, 0))
                        results = self.model.predict(
                            source=image,
                            conf=self.confidence,
                            iou=self.iou,
                            augment=self.augment,
                            verbose=False,
                            device=self.device
                        )

                        for result in results:
                            boxes = result.boxes
                            if boxes is None:
                                continue

                            for idx in range(len(boxes)):
                                conf = float(boxes.conf[idx].cpu().numpy())
                                if conf < self.confidence:
                                    continue

                                x1, y1, x2, y2 = boxes.xyxy[idx].cpu().numpy()
                                center_local_x = (x1 + x2) / 2
                                center_local_y = (y1 + y2) / 2
                                center_global_x = col + center_local_x
                                center_global_y = row + center_local_y

                                # EDGE FILTERING:
                                # Discard detections near the edge of the inference crop to avoid artifacts.
                                # Rely on overlapping windows to capture these as centered objects.
                                edge_margin = 32
                                is_edge_x = (x1 < edge_margin) or (x2 > crop_size - edge_margin)
                                is_edge_y = (y1 < edge_margin) or (y2 > crop_size - edge_margin)
                                
                                # Check if we are at the real boundary of the large image
                                at_image_left = (col == 0)
                                at_image_top = (row == 0)
                                at_image_right = (col + crop_size >= width)
                                at_image_bottom = (row + crop_size >= height)

                                # If near edge, drop it UNLESS it's a real image boundary
                                if is_edge_x:
                                    if (x1 < edge_margin and not at_image_left) or \
                                       (x2 > crop_size - edge_margin and not at_image_right):
                                        continue
                                
                                if is_edge_y:
                                    if (y1 < edge_margin and not at_image_top) or \
                                       (y2 > crop_size - edge_margin and not at_image_bottom):
                                        continue

                                lat, lon = self.pixel_to_latlon(
                                    (center_global_x, center_global_y),
                                    transform,
                                    crs
                                )

                                # Deduplicate nearby detections from overlapping windows
                                if any(
                                    self._approx_distance_m(lat, lon, s_lat, s_lon) <
                                    duplicate_threshold_m
                                    for s_lat, s_lon in seen_coords
                                ):
                                    continue

                                ndvi_value = self._sample_ndvi(src, center_global_x, center_global_y)
                                
                                # Default Class
                                class_name = "utility_pole"
                                
                                # --- ZERO-SHOT CLASSIFICATION ---
                                if self.classifier:
                                    try:
                                        # Crop from local window `image` using local box coords
                                        h_img, w_img, _ = image.shape
                                        ix1, iy1 = max(0, int(x1)), max(0, int(y1))
                                        ix2, iy2 = min(w_img, int(x2)), min(h_img, int(y2))
                                        
                                        if ix2 > ix1 and iy2 > iy1:
                                            # image is typically RGB from rasterio read([1,2,3])
                                            crop = image[iy1:iy2, ix1:ix2]
                                            # Converting numpy array to PIL
                                            # Ensure uint8
                                            if crop.dtype != np.uint8:
                                                # NAIP is usually 8-bit, but just in case
                                                crop = (crop / crop.max() * 255).astype(np.uint8)
                                            
                                            pil_crop = Image.fromarray(crop)
                                            
                                            clip_result = self.classifier(images=pil_crop, candidate_labels=self.classification_labels)
                                            top_label = clip_result[0]['label']
                                            top_score = clip_result[0]['score']

                                            if top_score > 0.35: # Slightly lower threshold for specific features
                                                if "leaning" in top_label:
                                                    class_name = "pole_leaning"
                                                elif "vegetation" in top_label:
                                                    class_name = "pole_vegetation"
                                                elif "damaged" in top_label or "broken" in top_label:
                                                    class_name = "pole_damage"
                                                elif "rusted" in top_label:
                                                    class_name = "pole_rust"
                                                elif "bird nest" in top_label:
                                                    class_name = "pole_nest"
                                                else:
                                                    class_name = "pole_good"
                                    except Exception as e:
                                        # Use a logger.debug to avoid spamming logs if classification fails often
                                        pass

                                detections.append({
                                    'pole_id': f"AI_DET_{tile_path.stem}_{len(detections) + 1}",
                                    'lat': lat,
                                    'lon': lon,
                                    'ai_confidence': conf,
                                    'tile_path': str(tile_path),
                                    'pixel_x': float(center_global_x),
                                    'pixel_y': float(center_global_y),
                                    'bbox': [float(x1 + col), float(y1 + row),
                                             float(x2 + col), float(y2 + row)],
                                    'source': 'ai_detection',
                                    'ndvi': ndvi_value,
                                    'class_name': class_name
                                })
                                seen_coords.append((lat, lon))

                        total_windows += 1
                        col += stride
                    row += stride

        logger.info(f"Tile detection complete: {len(detections)} unique poles "
                    f"from {total_windows} windows.")
        return detections

    @staticmethod
    def _sample_ndvi(src: rasterio.DatasetReader, x: float, y: float) -> Optional[float]:
        """Sample NDVI at the given pixel coordinates within an open NAIP dataset."""
        try:
            col = int(round(x))
            row = int(round(y))
            if not (0 <= row < src.height and 0 <= col < src.width):
                return None

            window = Window(col, row, 1, 1)
            try:
                red = src.read(1, window=window).astype(float)
                nir = src.read(4, window=window).astype(float)
            except rasterio.errors.RasterioIOError:
                return None

            denom = nir + red
            if denom == 0:
                return None
            ndvi = (nir - red) / denom
            value = float(ndvi.squeeze())
            if np.isnan(value) or np.isinf(value):
                return None
            return value
        except Exception:
            return None


def main():
    """
    Demo: Train and test pole detector
    """
    logger.info("=" * 60)
    logger.info("POLE DETECTOR DEMO")
    logger.info("=" * 60)

    # Initialize detector with pretrained YOLOv8
    detector = PoleDetector()

    # Check if training data exists
    data_yaml = TRAINING_DATA_DIR / 'pole_dataset.yaml'

    if data_yaml.exists():
        logger.info(f"\nFound training dataset: {data_yaml}")
        logger.info("\nTo train the model, uncomment the training code below")
        logger.info("Training will take several hours depending on your hardware\n")

        # Uncomment to train:
        # best_model = detector.train(
        #     data_yaml=data_yaml,
        #     epochs=100,
        #     batch_size=16,
        #     img_size=640,
        #     patience=20
        # )
        # logger.info(f"Training complete! Best model: {best_model}")

    else:
        logger.info(f"\nTraining dataset not found at {data_yaml}")
        logger.info("Run imagery_downloader.py first to set up training data")

    logger.info("\n" + "=" * 60)
    logger.info("DETECTOR READY")
    logger.info("=" * 60)
    logger.info("\nUsage:")
    logger.info("  detector = PoleDetector()")
    logger.info("  detections = detector.detect('path/to/image.jpg')")
    logger.info("  batch_results = detector.detect_batch(image_paths)")


if __name__ == "__main__":
    main()
