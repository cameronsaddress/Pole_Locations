import os
import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger("PipelineManager")

# API Container sees data at /data
# GPU Container sees data at /workspace/data
LOCAL_DATA_DIR = Path("/data/imagery") 

class PipelineManager:
    @staticmethod
    def list_datasets() -> Dict[str, List[Dict[str, Any]]]:
        """
        Returns a comprehensive list of datasets with status.
        grouped by State.
        Status:
         - 'available': Ready / Processed (Found in naip_multi_county)
         - 'supported': In Catalogue but not downloaded
         - 'mining': Currently being mined (Simulated)
        """
        naip_dir = LOCAL_DATA_DIR / "naip_multi_county"
        
        # Check availability
        available_folders = set()
        if naip_dir.exists():
            available_folders = {p.name.lower() for p in naip_dir.iterdir() if p.is_dir()}

        def get_status(cid):
            # Check full ID or ID without state suffix
            is_avail = (cid in available_folders) or (cid.replace("_pa", "").replace("_wa", "").replace("_ny", "") in available_folders)
            if is_avail:
                return "available"
            return "supported" # Default if not on disk

        # Define Catalogue
        catalogue = {
            "Pennsylvania": [
                {"id": "dauphin_pa", "name": "Dauphin County"},
                {"id": "cumberland_pa", "name": "Cumberland County"},
                {"id": "york_pa", "name": "York County"},
                {"id": "adams_pa", "name": "Adams County"},
                {"id": "allegheny_pa", "name": "Allegheny County"},
                {"id": "philadelphia_pa", "name": "Philadelphia County"},
            ],
            "Washington": [
                {"id": "spokane_wa", "name": "Spokane County"},
                {"id": "king_wa", "name": "King County (Seattle)"},
                {"id": "snohomish_wa", "name": "Snohomish County"},
                {"id": "pierce_wa", "name": "Pierce County"},
            ],
            "New York": [
                 {"id": "new_york_ny", "name": "New York City"},
            ],
             "Oregon": [
                 {"id": "multnomah_or", "name": "Multnomah County (Portland)"},
            ]
        }

        datasets = {}
        for state, counties in catalogue.items():
            datasets[state] = []
            for c in counties:
                datasets[state].append({
                    "id": c["id"],
                    "name": c["name"],
                    "status": get_status(c["id"])
                })
        
        return datasets

    _active_job = None  # { "type": str, "process": Popen, "start_time": float }

    @staticmethod
    def get_job_status() -> Dict[str, Any]:
        """
        Returns the status of the currently running job, if any.
        """
        job = PipelineManager._active_job
        if job is None:
            return {"is_running": False, "status": "idle", "job_type": None}
        
        # Check if process is still running
        retcode = job["process"].poll()
        if retcode is None:
            return {
                "is_running": True, 
                "status": "running", 
                "job_type": job["type"],
                "start_time": job["start_time"]
            }
        else:
            # Process finished
            PipelineManager._active_job = None # Clear it
            status = "completed" if retcode == 0 else "failed"
            return {
                "is_running": False, 
                "status": status, 
                "job_type": job["type"],
                "exit_code": retcode
            }

    @staticmethod
    def run_job(job_type: str, params: Dict[str, Any]) -> int:
        """
        Executes a pipeline step inside the GPU container via Docker.
        """
        # 1. Check if job already running
        if PipelineManager._active_job and PipelineManager._active_job["process"].poll() is None:
             raise ValueError(f"A job ({PipelineManager._active_job['type']}) is already running.")

        base_cmd = ["docker", "exec", "polevision-gpu"]
        cmd = []
        
        # 1. DATA MINING (Stage 1)
        if job_type == "mining":
            targets = params.get("targets", [])
            target_str = ",".join(targets) if targets else "all"
            # Pass targets as env var or arg. Script needs to handle it.
            # We'll pass as an argument: --targets id1,id2
            cmd = base_cmd + ["python3", "/workspace/src/training/mine_grid_for_labels.py", "--targets", target_str]

        # 2. INTEGRITY CHECK
        elif job_type == "integrity":
            cmd = base_cmd + ["python3", "/workspace/src/utils/integrity.py"]
        
        # 3. TRAIN SATELLITE
        elif job_type == "train_satellite":
            epochs = params.get("epochs", 50)
            batch = params.get("batch_size", 16)
            cmd = base_cmd + [
                "yolo", "detect", "train",
                "model=yolo11l.pt",
                "data=/workspace/data/training/satellite_expert/dataset.yaml",
                f"epochs={epochs}",
                f"batch={batch}",
                "imgsz=640",
                "project=/workspace/models/checkpoints",
                "name=yolo11l_satellite_expert",
                "device=0",
                "exist_ok=True"
            ]

        # 4. TRAIN STREET
        elif job_type == "train_street":
            epochs = params.get("epochs", 50)
            batch = params.get("batch_size", 16)
            cmd = base_cmd + [
                "yolo", "detect", "train",
                "model=yolo11l.pt",
                "data=/workspace/data/training/street_expert/dataset.yaml",
                f"epochs={epochs}",
                f"batch={batch}",
                "imgsz=640",
                "project=/workspace/models/checkpoints",
                "name=yolo11l_street_expert",
                "device=0",
                "exist_ok=True"
            ]

        # 5. INFERENCE (DETECT + FUSE)
        elif job_type == "inference":
            targets = params.get("targets", [])
            
            # Paths must be GPU container paths
            target_paths = [f"/workspace/data/imagery/naip_multi_county/{t}" for t in targets]
            
            cmd = base_cmd + [
                "python3", "/workspace/src/pipeline/runner.py",
                "--dirs"
            ] + target_paths

        # 6. FULL PIPELINE
        elif job_type == "full_pipeline":
             cmd = base_cmd + ["python3", "/workspace/run_full_enterprise_pipeline.py"]

        else:
            raise ValueError(f"Unknown job type: {job_type}")

        logger.info(f"Starting job {job_type}: {' '.join(cmd)}")
        
        # Log Logic:
        # We write stdout of the docker command (which streams the container output)
        # to a local file in the API container (/app/pipeline.log)
        log_file_path = "/app/pipeline.log"
        
        with open(log_file_path, "w") as f:
            f.write(f"--- STARTED JOB: {job_type} ---\n")

        # Open in append mode for the process
        log_file = open(log_file_path, "a")
        
        process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT
        )
        
        import time
        PipelineManager._active_job = {
            "type": job_type,
            "process": process,
            "start_time": time.time()
        }
            
        return process.pid

    @staticmethod
    def get_logs(lines: int = 100) -> str:
        """Reads the last N lines of the pipeline log."""
        log_path = Path("/app/pipeline.log")
        if not log_path.exists():
            return "No logs available."
        
        try:
            result = subprocess.run(["tail", "-n", str(lines), str(log_path)], capture_output=True, text=True)
            return result.stdout
        except Exception:
            return "Error reading logs."
