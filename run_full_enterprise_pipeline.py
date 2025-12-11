
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
    
    # --- STEP 1: TRAIN YOLO11 ---
    logger.info("--- [STEP 1/4] Training YOLO11l Model ---")
    train_cmd = (
        "yolo detect train "
        "model=yolo11l.pt "
        "data=/workspace/data/processed/pole_training_dataset_512/dataset.yaml "
        "epochs=50 "
        "imgsz=512 "
        "batch=16 "
        "project=/workspace/models/checkpoints "
        "name=yolo11l_full_run "
        "device=0 "
        "exist_ok=True"
    )
    run_command(train_cmd)
    
    # --- STEP 2: INFERENCE & FULL PIPELINE ---
    logger.info("--- [STEP 2/4] Running Enterprise Pipeline on PA Counties ---")
    
    target_dirs = [
        "/data/imagery/naip_multi_county/dauphin_pa",
        "/data/imagery/naip_multi_county/york_pa",
        "/data/imagery/naip_multi_county/cumberland_pa"
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
