
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
    import argparse
    parser = argparse.ArgumentParser()
    # Logic Inversion: Default is SKIP training (Fast Path). Use --train to enforce training.
    parser.add_argument("--train", action="store_true", help="Force YOLO training (defaults to using existing weights)")
    parser.add_argument("--skip-integrity", action="store_true", help="Skip Data Integrity/Repair check")
    parser.add_argument("--mining-targets", type=str, help="Comma-separated list of targets to mine")
    parser.add_argument("--inference-targets", type=str, help="Comma-separated list of targets to run inference on (defaults to all)")
    
    args, unknown = parser.parse_known_args()
    
    # --- STEP 0: DATA MINING (Optional) ---
    if hasattr(args, 'mining_targets') and args.mining_targets:
        targets_list = args.mining_targets.split(',')
        logger.info(f"--- [STEP 0/4] Mining New Regions: {targets_list} ---")
        
        # We call the mining script directly
        mine_cmd = f"python src/training/mine_grid_for_labels.py --targets {args.mining_targets}"
        run_command(mine_cmd)
        
        logger.info("✅ Mining Complete. New datasets should be available.")
    else:
        logger.info("⏭️  Skipping Mining (No targets provided).")
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

    # --- STEP 1: TRAIN YOLO11 (Dual-Expert) ---
    if args.train:
        logger.info("--- [STEP 1/4] Training YOLO11l Specialist Models (Dual-Expert) ---")
        
        # 1. Train Satellite Expert
        logger.info("Training Satellite Expert Model...")
        
        # Gen YAML for Sat
        with open("src/utils/gen_sat_yaml.py", "w") as f:
            f.write("""
import yaml
from pathlib import Path
import os

# Create dir if not exists (for sat expert)
Path('/workspace/data/training/satellite_expert').mkdir(parents=True, exist_ok=True)

data = {
    'path': '/workspace/data/training/satellite_expert',
    'train': 'images/train', 
    'val': 'images/val', 
    'nc': 1,
    'names': ['utility_pole']
}

with open('/workspace/data/training/satellite_expert/dataset.yaml', 'w') as f:
    yaml.dump(data, f)

print("YAML Generated.")
""")
        # Actually, let's just make a new preparation script that splits BOTH properly.
        # We will assume 'src/utils/prepare_expert_datasets.py' is created.
        logger.info("Preparing Expert Datasets...")
        run_command("python3 src/utils/prepare_expert_datasets.py")

        # Train Sat
        run_command(
            "yolo detect train "
            "model=yolo11l.pt "
            "data=/workspace/data/training/satellite_expert/dataset.yaml "
            "epochs=50 "
            "imgsz=640 "
            "project=/workspace/models/checkpoints "
            "name=yolo11l_satellite_expert "
            "device=0 "
            "exist_ok=True"
        )
        
        # 2. Train Street Expert
        logger.info("Training Street Expert Model...")
        run_command(
            "yolo detect train "
            "model=yolo11l.pt "
            "data=/workspace/data/training/street_expert/dataset.yaml "
            "epochs=50 "
            "imgsz=640 " # Street view benefits from higher Res, maybe 1280? sticking to 640 for speed/parity
            "project=/workspace/models/checkpoints "
            "name=yolo11l_street_expert "
            "device=0 "
            "exist_ok=True"
        )
        
    else:
        logger.info("⏭️  Skipping Training (User Request). Using existing checkpoints.")
    
    # --- STEP 2: INFERENCE & FULL PIPELINE ---
    logger.info("--- [STEP 2/4] Running Enterprise Pipeline on PA Counties ---")
    
    # Dynamic Discovery of Targets
    base_data_dir = Path("/workspace/data/imagery/naip_multi_county")
    target_dirs = []
    
    if base_data_dir.exists():
        all_dirs = [str(p) for p in base_data_dir.iterdir() if p.is_dir()]
        
        # Filter if targets provided
        if hasattr(args, 'inference_targets') and args.inference_targets:
            whitelist = args.inference_targets.split(',')
            # Normalize strings for matching
            target_dirs = [d for d in all_dirs if any(w.strip() in Path(d).name for w in whitelist)]
            logger.info(f"Targeting specific datasets ({len(target_dirs)}): {[Path(t).name for t in target_dirs]}")
        else:
            target_dirs = all_dirs
            logger.info(f"Targeting ALL datasets ({len(target_dirs)})")
    
    if not target_dirs:
         logger.warning("No datasets found in naip_multi_county. Defaulting to empty list.")
    
    # Verify dirs exist inside container view
    dirs_arg = " ".join(target_dirs)
    
    pipeline_cmd = (
        f"python3 -m src.pipeline.runner "
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
