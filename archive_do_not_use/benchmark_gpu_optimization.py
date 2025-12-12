
"""
DGX Spark GPU Optimization Benchmark (Isolated Process Mode)
------------------------------------------------------------
Runs sequential training jobs via CLI to allow full VRAM cleanup between runs.
This ensures stability benchmarks are accurate for the Unified Memory architecture.

Configurations:
1. Batch = -1 (Auto)
2. Batch = 0.7 (70% Target)
3. Batch = 0.8 (80% Target)
4. Batch = 0.9 (90% Target)

Usage:
  python benchmark_gpu_optimization.py
"""
import subprocess
import logging
import sys
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DGX_Benchmark")

def run_command(cmd, log_name):
    logger.info(f"🚀 Executing Benchmark: {log_name}")
    logger.info(f"Command: {cmd}")
    
    start_time = time.time()
    try:
        # Run process and stream output
        process = subprocess.Popen(
            cmd, 
            shell=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # Stream logs to console
        for line in process.stdout:
            print(line, end='')
            
        process.wait()
        
        duration = time.time() - start_time
        if process.returncode == 0:
            logger.info(f"✅ {log_name} Complete. Duration: {duration:.2f}s")
            return True
        else:
            logger.error(f"❌ {log_name} Failed with code {process.returncode}")
            return False
            
    except Exception as e:
        logger.error(f"Execution Error: {e}")
        return False

def run_benchmark_suite():
    logger.info("Starting DGX Spark Optimization Benchmark Suite...")
    
    # Common Parameters
    model = "yolo11l.pt"
    data = "/workspace/data/processed/pole_training_dataset_512/dataset.yaml"
    imgsz = 512
    workers = 12       # Fixed Optimal for Grace CPU
    epochs = 1         # Single epoch for fast benchmarking
    device = 0
    project = "/workspace/models/benchmarks"
    
    configs = [
        {"name": "batch_32", "batch": 32},
        {"name": "batch_64", "batch": 64},
        {"name": "batch_96", "batch": 96},
    ]

    for cfg in configs:
        name = f"dgx_bench_{cfg['name']}"
        batch = cfg['batch']
        
        # Construct CLI Command
        cmd = (
            f"yolo detect train "
            f"model={model} "
            f"data={data} "
            f"epochs={epochs} "
            f"imgsz={imgsz} "
            f"batch={batch} "
            f"workers={workers} "
            f"cache='disk' "    # Use disk cache to avoid OOM
            f"device={device} "
            f"project={project} "
            f"name={name} "
            f"exist_ok=True "
        )
        
        success = run_command(cmd, name)
        
        if success:
            logger.info("Waiting 10s for VRAM cleanup...")
            time.sleep(10)
        else:
            logger.warning("Skipping cleanup due to failure.")

    logger.info("🏁 Benchmark Suite Complete. Inspect metrics in /workspace/models/benchmarks/")

if __name__ == "__main__":
    run_benchmark_suite()
