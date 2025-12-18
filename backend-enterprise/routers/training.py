
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
import logging
import asyncio
import subprocess
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))
from src.training.llm_optimizer import LLMHyperparameterOptimizer

router = APIRouter()
logger = logging.getLogger(__name__)

# --- SHARED CONTEXT ---
job_context = {
    "active_job": None, 
    "trials_queue": [], 
    "is_running": False,
    "current_process": None
}

# --- MODELS ---
class TrainingJobConfig(BaseModel):
    epochs: int
    batchSize: int
    autoTune: bool
    detectorModel: str = "yolo11l"
    dataset: str = "street"

class ClassificationJobConfig(BaseModel):
    labels: str
    confidence: float
    grokAssistant: bool
    model: str = "vit-l"

# --- HELPERS ---
async def run_script(script_path: str, args: list):
    """Run a python script inside the GPU container via docker exec."""
    # Map local relative path (src/...) to container workspace path (/workspace/src/...)
    container_script_path = f"/workspace/{script_path}"
    
    cmd = ["/usr/bin/docker", "exec", "polevision-gpu", "python", "-u", container_script_path] + [str(a) for a in args]
    logger.info(f"Running in GPU Container: {' '.join(cmd)}")
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    # Allow cancellation
    job_context["current_process"] = proc
    
    final_json = None
    
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        line_str = line.decode().strip()
        if not line_str:
            continue
        
        # Log to UI if it's not a JSON dict we process specially
        is_handled = False
        
        try:
            data = json.loads(line_str)
            
            # Handle Live Telemetry/Stats
            if data.get("type") == "epoch":
                job_context["trials_queue"].append({
                    "type": "stats", # UI expects 'stats' type for charts
                    "payload": data
                })
                # VISIBILITY FIX: Log epoch text for CLI window
                job_context["trials_queue"].append({
                    "type": "log",
                    "payload": f"[EXEC] Epoch {data.get('epoch')}/{data.get('total_epochs', '?')}: mAP50={data.get('map50', 0):.3f} Loss={data.get('box_loss', 0):.3f}"
                })
                is_handled = True
            elif data.get("type") in ["log", "progress"]:
                job_context["trials_queue"].append({
                    "type": "log",
                    "payload": data.get("payload", str(data))
                })
                is_handled = True
            
            # Keep track of last valid JSON for return value
            final_json = data
            
        except:
            pass
            
        if not is_handled:
             job_context["trials_queue"].append({
                "type": "log",
                "payload": f"[EXEC] {line_str}"
            })
            
    await proc.wait()
    job_context["current_process"] = None
    return final_json

# --- LOOPS ---

async def optimize_detector_closed_loop(config: TrainingJobConfig):
    job_context["active_job"] = "detector"
    job_context["is_running"] = True
    job_context["trials_queue"] = []
    
    llm = LLMHyperparameterOptimizer()
    
    # Initial Params (Best Practice Defaults)
    current_params = {
        "lr0": 0.01,
        "momentum": 0.937,
        "weight_decay": 0.0005,
        "epochs": config.epochs
    }
    
    trials_history = []
    max_iter = 5 if config.autoTune else 1
    
    for i in range(1, max_iter + 1):
        # 1. Broadcast Start
        job_context["trials_queue"].append({
            "type": "log",
            "payload": f"Starting Trial {i}/{max_iter} with LR={current_params['lr0']} on {config.dataset}"
        })
        
        # 2. Run Training Script
        result = await run_script("src/training/train_detector.py", [
            "--lr0", current_params['lr0'],
            "--momentum", current_params['momentum'],
            "--weight_decay", current_params['weight_decay'],
            "--epochs", current_params['epochs'],
            "--batch", config.batchSize,
            "--dataset", config.dataset
        ])
        
        if not result:
            logger.error("Script failed to produce JSON")
            break
            
        # 3. Record & Broadcast Result
        metrics = {
            "map50": result.get("map50", 0.0),
            "box_loss": result.get("box_loss", 0.0)
        }
        trials_history.append({"params": current_params.copy(), "metrics": metrics})
        
        job_context["trials_queue"].append({
            "type": "trial",
            "payload": {
                "id": i,
                "map": f"{metrics['map50']:.3f}",
                "lr": str(current_params['lr0']),
                "status": "completed",
                "insight": "Trial Complete.",
                "param": f"LR: {current_params['lr0']}"
            }
        })
        
        # 4. Grok Step
        if i < max_iter:
            job_context["trials_queue"].append({
                "type": "log",
                "payload": "Consulting Grok-4.1 for next parameters..."
            })
            
            new_params = llm.suggest_hyperparameters(
                current_best=trials_history[-1], # Simplified: pass last as current
                recent_trials=trials_history,
                mode="detector"
            )
            
            # Update params
            current_params.update(new_params)
            
            # Broadcast Plan
            job_context["trials_queue"].append({
                "type": "trial",
                "payload": {
                    "id": i+1,
                    "map": "...",
                    "status": "active",
                    "insight": "Grok Recommendation: Adjusting LR/Momentum based on loss curve.",
                    "param": f"LR: {current_params['lr0']}"
                }
            })
            
    job_context["is_running"] = False


async def optimize_clip_closed_loop(config: ClassificationJobConfig):
    job_context["active_job"] = "clip"
    job_context["is_running"] = True
    job_context["trials_queue"] = []
    
    llm = LLMHyperparameterOptimizer()
    
    # Initial Params
    current_params = {
        "confidence": config.confidence,
        "nms": 0.45
    }
    
    trials_history = []
    max_iter = 5 if config.grokAssistant else 1
    
    # Initial broadcast
    job_context["trials_queue"].append({
         "type": "trial",
         "payload": {
             "id": 1,
             "f1": "...",
             "status": "active",
             "insight": "Initializing Zero-Shot Validation...",
             "param": f"Conf: {current_params['confidence']}"
         }
    })

    for i in range(1, max_iter + 1):
        # 1. Run Validation Script
        result = await run_script("src/training/tune_clip.py", [
            "--confidence", current_params['confidence'],
            "--nms", current_params['nms']
        ])
        
        if not result:
            break
            
        rate = result.get("defect_rate", 0.0)
        
        # 2. Record
        metrics = {"defect_rate": rate}
        trials_history.append({"params": current_params.copy(), "metrics": metrics})
        
        # 3. Broadcast
        job_context["trials_queue"].append({
            "type": "trial",
            "payload": {
                "id": i,
                "f1": f"{rate*100:.1f}%", # Display Defect Rate instead of F1
                "status": "completed",
                "insight": f"Defect Rate: {rate:.1%} ({result.get('defect_count',0)} items)",
                "param": f"Conf: {current_params['confidence']:.2f}"
            }
        })
        
        # 4. Grok
        if i < max_iter:
            job_context["trials_queue"].append({
                "type": "log",
                "payload": "Analysis: Defect rate distribution check..."
            })
            
            new_params = llm.suggest_hyperparameters(
                current_best=trials_history[-1],
                recent_trials=trials_history,
                mode="clip"
            )
            
            current_params.update(new_params)
            
            job_context["trials_queue"].append({
                "type": "trial",
                "payload": {
                    "id": i+1,
                    "f1": "...",
                    "status": "active",
                    "insight": "Grok: Optimization based on defect density.",
                    "param": f"Conf: {current_params['confidence']:.2f}"
                }
            })

    job_context["is_running"] = False

# --- ENDPOINTS ---

@router.post("/start")
async def start_training(config: TrainingJobConfig, background_tasks: BackgroundTasks):
    background_tasks.add_task(optimize_detector_closed_loop, config)
    return {"status": "initiated", "message": "Detector optimization started."}
@router.post("/stop")
async def stop_training():
    """Stop the currently running training job."""
    if job_context["current_process"]:
        try:
            job_context["current_process"].terminate()
            logger.info("Terminated docker exec process.")
        except Exception as e:
            logger.error(f"Failed to terminate process: {e}")

    # Ensure heavy process inside container is killed
    try:
        cmd = ["/usr/bin/docker", "exec", "polevision-gpu", "pkill", "-f", "train_detector.py"]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await proc.wait()
        logger.info("Sent pkill to GPU container.")
    except Exception as e:
        logger.error(f"Failed to pkill in container: {e}")

    job_context["is_running"] = False
    job_context["trials_queue"].append({
        "type": "log",
        "payload": "[CMD] Training Job Stopped by User."
    })
    return {"status": "stopped"}


@router.post("/start-clip")
async def start_clip_training(config: ClassificationJobConfig, background_tasks: BackgroundTasks):
    background_tasks.add_task(optimize_clip_closed_loop, config)
    return {"status": "initiated", "message": "CLIP optimization started."}

async def run_production_inference(limit: int = 15, task: str = "full"):
    """
    Executes the real python script for production inference.
    """
    job_context["active_job"] = f"deploy-{task}"
    job_context["is_running"] = True
    job_context["trials_queue"] = []
    
    # script_path = "src/training/run_production_job.py"
    # Execute in GPU Container
    container_script_path = "/workspace/src/training/run_production_job.py"
    cmd = ["/usr/bin/docker", "exec", "polevision-gpu", "python", "-u", container_script_path, "--limit", str(limit), "--task", task]
    
    logger.info(f"Starting Production Deployment: {cmd}")
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        job_context["current_process"] = process
        
        job_context["trials_queue"].append({
            "type": "log",
            "payload": f"[SYS] INITIALIZING {task.upper()} PIPELINE..."
        })

        while True:
            line = await process.stdout.readline()
            if not line:
                break
            
            line_str = line.decode().strip()
            if not line_str:
                continue
                
            try:
                data = json.loads(line_str)
                
                if data.get("type") == "progress":
                    defects_str = ""
                    if task == "full":
                         defects_str = f" ({len(data.get('defects', {}))} defects)"
                    
                    msg = f"Processed Tile {data['tiles_processed']}/{data['total_tiles']}. Found {data['poles_found']} poles.{defects_str}"
                    
                    job_context["trials_queue"].append({
                        "type": "log",
                        "payload": msg
                    })

                elif data.get("type") == "complete":
                    job_context["trials_queue"].append({
                        "type": "log",
                        "payload": f"[SUCCESS] JOB COMPLETE. Results: {data.get('output_file')}"
                    })

            except json.JSONDecodeError:
                job_context["trials_queue"].append({
                    "type": "log",
                    "payload": f"[OUT] {line_str}"
                })
        
        await process.wait()
        
    except Exception as e:
        logger.error(f"Failed to run deployment: {e}")
        job_context["trials_queue"].append({
            "type": "log",
            "payload": f"[ERR] Deployment Failed: {str(e)}"
        })
    finally:
        job_context["is_running"] = False
        job_context["current_process"] = None

@router.post("/deploy/detector")
async def deploy_detector(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_production_inference, limit=15, task="detect-only")
    return {"status": "initiated", "message": "Detector inference started."}

@router.post("/deploy/classifier")
async def deploy_classifier(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_production_inference, limit=15, task="full")
    return {"status": "initiated", "message": "Classifier full pipeline started."}
