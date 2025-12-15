import pandas as pd
import boto3
from botocore import UNSIGNED
from botocore.client import Config
import os
import logging
from pathlib import Path
import requests
import io

# Config
DATA_DIR = Path("/home/canderson/PoleLocations/data/training/open_images")
DATA_DIR.mkdir(parents=True, exist_ok=True)
IMG_DIR = DATA_DIR / "images"
IMG_DIR.mkdir(exist_ok=True)
LABEL_DIR = DATA_DIR / "labels"
LABEL_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OID Resources
CLASS_DESC_URL = "https://storage.googleapis.com/openimages/v7/oidv7-class-descriptions-boxable.csv"
ANNOTATIONS_URL = "https://storage.googleapis.com/openimages/v6/oidv6-train-annotations-bbox.csv"

def download_class_descriptions():
    logger.info("Downloading class descriptions...")
    r = requests.get(CLASS_DESC_URL)
    df = pd.read_csv(io.StringIO(r.text), names=["LabelName", "DisplayName"])
    return df

def download_metadata_and_filter(target_class="/m/033rq4"):
    """
    Download annotations and filter for target class using strict streaming (no pandas read).
    """
    logger.info("Downloading annotations (streaming)...")
    local_csv = DATA_DIR / "oidv6-train-annotations-bbox.csv"
    
    if not local_csv.exists():
        with requests.get(ANNOTATIONS_URL, stream=True) as r:
            r.raise_for_status()
            with open(local_csv, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024*1024): # 1MB chunks
                    f.write(chunk)
    
    logger.info("Filtering annotations (streaming mode)...")
    
    import csv
    pole_rows = []
    
    # Use standard csv module for zero-overhead streaming
    with open(local_csv, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        # Identify columns
        try:
            label_idx = header.index("LabelName")
            img_id_idx = header.index("ImageID")
        except ValueError:
            logger.error("Invalid CSV header")
            return pd.DataFrame()
            
        count = 0
        for row in reader:
            if row[label_idx] == target_class:
                pole_rows.append(row)
                count += 1
                if count >= 1000: # Limit to 1000 annotations for speed
                    break
    
    if not pole_rows:
        return pd.DataFrame()
        
    df_poles = pd.DataFrame(pole_rows, columns=header)
    logger.info(f"Found {len(df_poles)} annotations (limited).")
    return df_poles

def download_images_s3(image_ids):
    """
    Download images from public S3 bucket: s3://open-images-dataset
    Structure: train/{image_id}.jpg
    """
    s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))
    bucket = 'open-images-dataset'
    
    count = 0
    total = len(image_ids)
    
    for img_id in image_ids:
        key = f"train/{img_id}.jpg"
        target = IMG_DIR / f"{img_id}.jpg"
        
        if target.exists():
            continue
            
        try:
            s3.download_file(bucket, key, str(target))
            count += 1
            if count % 100 == 0:
                logger.info(f"Downloaded {count}/{total} images...")
        except Exception as e:
            logger.warning(f"Failed to download {key}: {e}")
            
    logger.info(f"Download complete. {count} new images.")

def main():
    # 1. verify class
    df_classes = download_class_descriptions()
    
    # Hardcoded 'Street light' /m/033rq4
    label_name = "/m/033rq4"
    logger.info(f"Target Class: {label_name} (Street light)")
    
    # 2. Get Annotations
    df_annots = download_metadata_and_filter(label_name)
    
    if df_annots.empty:
        logger.warning("No images found.")
        return
        
    # Save annotations locally
    df_annots.to_csv(DATA_DIR / "pole_annotations.csv", index=False)
    
    # 3. Download Images (Limit to 500 for demo speed)
    unique_images = df_annots['ImageID'].unique()[:500] 
    logger.info(f"Downloading subset of {len(unique_images)} images...")
    
    download_images_s3(unique_images)
    
if __name__ == "__main__":
    main()
