import os
import requests
import zipfile
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Target directory for downloads
DOWNLOAD_DIR = Path("/home/canderson/PoleLocations/data/training/open_source")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

def download_file(url, target_path):
    """Download a file from a URL to a target path."""
    try:
        logger.info(f"Downloading from {url}...")
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(target_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(f"Downloaded to {target_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return False

def extract_zip(zip_path, extract_to):
    """Extract a zip file to a target directory."""
    try:
        logger.info(f"Extracting {zip_path}...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        logger.info(f"Extracted to {extract_to}")
        return True
    except Exception as e:
        logger.error(f"Failed to extract {zip_path}: {e}")
        return False

def fetch_github_dataset():
    """
    Attempt to fetch the dataset referenced in the Adco30 GitHub repo.
    Since we can't browse, we'll try to find a direct link or clone the repo if it contains data.
    The repo is https://github.com/Adco30/Utility-Pole-Detection.
    We will try to clone it to a temp dir and check for a 'dataset' folder.
    """
    repo_url = "https://github.com/Adco30/Utility-Pole-Detection.git"
    repo_dir = DOWNLOAD_DIR / "Adco30_Repo"
    
    if repo_dir.exists():
        logger.info(f"Repo already exists at {repo_dir}")
    else:
        logger.info(f"Cloning {repo_url}...")
        os.system(f"git clone {repo_url} {repo_dir}")
        
    # Check for dataset structure
    dataset_path = repo_dir / "dataset" # Anticipated path
    if dataset_path.exists():
        logger.info(f"Found dataset folder in {dataset_path}")
        # List contents
        for item in dataset_path.glob("*"):
            logger.info(f"  - {item.name}")
    else:
        logger.warning(f"No 'dataset' folder found in {repo_dir}")
        # Look for zip files
        zips = list(repo_dir.glob("*.zip"))
        if zips:
            logger.info(f"Found zip files: {[z.name for z in zips]}")
            for z in zips:
                extract_zip(z, repo_dir / "extracted_data")

def main():
    logger.info("Starting Open Source Data Acquisition...")
    
    # Strategy 1: GitHub Clone
    fetch_github_dataset()
    
    # Strategy 2: Check for other known open URLs (placeholder for now)
    # If we had a direct URL for a Kaggle dataset zip, we would verify it here.
    
    logger.info("Data Acquisition Steps Completed.")

if __name__ == "__main__":
    main()
