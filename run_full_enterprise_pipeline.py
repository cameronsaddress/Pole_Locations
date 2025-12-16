
"""
Full Enterprise Pipeline Orchestrator
-------------------------------------
1. TRAIN: YOLO11l on Pole Dataset (50 Epochs).
2. DETECT: Run Inference on Dauphin, York, and Cumberland counties.
3. ENRICH: Apply Lidar & PASDA filters.
4. FUSE: Validate with FAA & OpenInfraGrid.
"""
import subprocess
import logging
import sys
import time
from pathlib import Path

# Fix paths
PROJECT_ROOT = Path("/workspace")
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "backend-enterprise"))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("EnterpriseOrchestrator")

def run_command(cmd, cwd=None, env=None):
    logger.info(f"🚀 Executing: {cmd}")
    try:
        # Stream output to logger/stdout
        process = subprocess.Popen(
            cmd, 
            shell=True, 
            cwd=cwd, 
            env=env,
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT,
            text=True
        )
        
        for line in process.stdout:
            print(line, end='')
            
        process.wait()
        if process.returncode != 0:
            logger.error(f"❌ Command failed with code {process.returncode}")
            sys.exit(process.returncode)
            
    except Exception as e:
        logger.error(f"Execution Error: {e}")
        sys.exit(1)

def main():
    logger.info("Starting Full Enterprise Pipeline Run (Train -> Detect -> Fuse)")
    
    # Check flags
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-train", action="store_true", help="Skip YOLO training and use existing weights")
    parser.add_argument("--skip-integrity", action="store_true", help="Skip Data Integrity/Repair check (e.g. if running separately)")
    # Parse only known args to avoid conflicts if needed, or just parse_args
    args, unknown = parser.parse_known_args()
    
    # --- PRE-FLIGHT CHECK: DATA INTEGRITY ---
    if not args.skip_integrity:
        logger.info("--- [PRE-FLIGHT] Checking Data Integrity ---")
        
        target_dirs = [
            "/workspace/data/imagery/naip_multi_county/osm_poles_dauphin_pa",
            "/workspace/data/imagery/naip_multi_county/osm_poles_york_pa",
            "/workspace/data/imagery/naip_multi_county/osm_poles_cumberland_pa"
        ]
        
        # Import here to avoid overhead if not needed globally, or move to top
        from src.utils.integrity import scan_and_repair
        scan_and_repair(target_dirs)
        
        # Ensure Grid Backbone Exists
        grid_file = Path("/workspace/data/processed/grid_backbone.geojson")
        if not grid_file.exists():
            logger.info("--- [PRE-FLIGHT] Grid Backbone Missing. Fetching from OpenInfraMap... ---")
             # We need to call the function directly or via script.
            # Easiest is to invoke python -c or a thin script
            cmd = "python3 -c \"from src.ingestion.connectors.openinframap import fetch_grid_backbone; fetch_grid_backbone()\""
            run_command(cmd)
        else:
            logger.info("✅ Grid Backbone Exists.")
            
        # Ensure Water Data Exists
        water_file = Path("/workspace/data/processed/water_osm.geojson")
        if not water_file.exists():
            logger.info("--- [PRE-FLIGHT] Water Data Missing. Fetching from OSM (Overpass)... ---")
            run_command("python src/ingestion/fetch_regional_water.py")
        else:
             logger.info("✅ Water Data Exists.")
    else:
        logger.info("⏭️  Skipping Data Integrity Check (User Request).")

    # --- STEP 1: TRAIN YOLO11 (Dual-Stream) ---
    if not args.skip_train:
        logger.info("--- [STEP 1/4] Training YOLO11l Model (Dual-Stream) ---")
        
        # 1. Generate Dataset YAML
        logger.info("Generating Dual-Stream Dataset YAML...")
        
        # Create helper script if it doesn't exist (simpler than inline)
        yaml_script = """
import yaml
import os
from pathlib import Path

data = {
    'path': '/workspace/data/training/unified_dataset',
    'train': 'images/train',
    'val': 'images/val',
    'nc': 1,
    'names': ['utility_pole']
}

Path('/workspace/data/training/unified_dataset').mkdir(parents=True, exist_ok=True)
with open('/workspace/data/training/unified_dataset/dataset.yaml', 'w') as f:
    yaml.dump(data, f)
print("YAML Generated.")
"""
        with open("src/utils/gen_yaml.py", "w") as f:
            f.write(yaml_script)
            
        run_command("python3 src/utils/gen_yaml.py")
        
        # 2. Prepare Data (Merge Sat + Street)
        # We need a script to shuffle and split the data into train/val
        logger.info("Merging Satellite and Street datasets...")
        merge_cmd = "python3 src/utils/prepare_dual_stream_dataset.py" 
        # (We need to create this script, or we can inline it if simple)
        # For now, assuming we will create it.
        run_command(merge_cmd)

        # 3. Train
        train_cmd = (
            "yolo detect train "
            "model=yolo11l.pt "
            "data=/workspace/data/training/unified_dataset/dataset.yaml "
            "epochs=50 "
            "imgsz=640 " # Increased to 640 for better small object detection
            "batch=16 "
            "workers=8 "
            "project=/workspace/models/checkpoints "
            "name=yolo11l_dual_stream "
            "device=0 "
            "exist_ok=True"
        )
        run_command(train_cmd)
    else:
        logger.info("⏭️  Skipping Training (User Request). Using existing checkpoints.")
    
    # --- STEP 2: INFERENCE & FULL PIPELINE ---
    logger.info("--- [STEP 2/4] Running Enterprise Pipeline on PA Counties ---")
    
    target_dirs = [
        "/workspace/data/imagery/naip_multi_county/osm_poles_dauphin_pa",
        "/workspace/data/imagery/naip_multi_county/osm_poles_york_pa",
        "/workspace/data/imagery/naip_multi_county/osm_poles_cumberland_pa"
    ]
    
    # Verify dirs exist inside container view
    dirs_arg = " ".join(target_dirs)
    
    pipeline_cmd = (
        f"python src/pipeline/runner.py "
        f"--dirs {dirs_arg}"
    )
    
    # Ensure env vars are set
    env = {
        "PYTHONPATH": "/workspace:/workspace/backend-enterprise",
        "DATABASE_URL": "postgresql://pole_user:pole_secure_password@localhost:5433/polevision",
        "PATH": "/usr/local/bin:/usr/bin:/bin" # Basic path
    }
    
    run_command(pipeline_cmd, env=env)
    
    logger.info("✅ Full Enterprise Run Complete.")

if __name__ == "__main__":
    main()
