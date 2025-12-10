from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
import logging
import asyncio
import random

router = APIRouter()
logger = logging.getLogger(__name__)

# --- SHARED CONTEXT ---
# Simple in-memory state for the pilot to bridge http -> websocket
job_context = {
    "active_job": None, # 'detector' | 'clip'
    "trials_queue": [], # List of trial objects to be broadcast
    "is_running": False
}

# --- MODELS ---
class TrainingJobConfig(BaseModel):
    epochs: int
    batchSize: int
    autoTune: bool
    detectorModel: str = "yolov8l"

class ClassificationJobConfig(BaseModel):
    labels: str
    confidence: float
    grokAssistant: bool
    model: str = "vit-l"

# --- TASKS ---
async def optimize_detector_loop(config: TrainingJobConfig):
    job_context["active_job"] = "detector"
    job_context["is_running"] = True
    job_context["trials_queue"] = []
    
    logger.info(f"Starting Closed-Loop Optimization for Detector: {config.detectorModel}")
    
    # 1. Initial State
    current_params = {
        "lr": 0.01,
        "momentum": 0.9,
        "weight_decay": 0.0005,
        "box_gain": 7.5
    }
    history = []
    
    # 2. Optimization Loop (Max 5 iterations or until convergence)
    max_iterations = 5 if config.autoTune else 1
    
    for i in range(1, max_iterations + 1):
        # A. Broadcast Start of Trial
        logger.info(f"Starting Iteration {i} with params: {current_params}")
        
        # B. Simulate Training Run (The heavy lifting)
        await asyncio.sleep(4) 
        
        # C. Generate Metrics (Simulate Improvement based on "Grok's" imaginary guidance)
        # We simulate a "convergence curve"
        base_map = 0.60 + (i * 0.05) + random.uniform(-0.02, 0.02)
        map50 = min(0.92, base_map)
        
        # D. Record Result
        result = {
            "id": i,
            "map": f"{map50:.3f}",
            "params": current_params.copy(),
            "status": "completed",
            "insight": "Evaluating metrics..."
        }
        history.append(result)
        
        # E. Broadcast Result
        job_context["trials_queue"].append({
            "type": "trial",
            "payload": {
                "id": i,
                "map": result["map"],
                "lr": str(current_params["lr"]),
                "status": "completed",
                "insight": "Trial complete. Uploading telemetry to Grok..."
            }
        })
        
        # F. The "Grok Step" (If continuing)
        if i < max_iterations:
            await asyncio.sleep(2) # Simulate Network Call to OpenRouter
            
            # Simulate Structured Response from Grok
            # "I see trial X had mAP Y. I recommend changing LR to Z to improve stability."
            new_lr = round(current_params["lr"] * 0.8, 4) # Decaying LR strategy
            insight = f"Trial {i} showed gradient instability. Reducing LR to {new_lr} to smooth convergence."
            
            current_params["lr"] = new_lr
            
            # Broadcast the Analysis/Transition
            job_context["trials_queue"].append({
                "type": "trial",
                "payload": {
                    "id": i+1,
                    "map": "...",
                    "lr": str(new_lr),
                    "status": "active", # Next one is now active
                    "insight": insight # The reasoning from Grok
                }
            })
            
    await asyncio.sleep(2)
    job_context["is_running"] = False
    logger.info("Detector Optimization Complete")


async def optimize_clip_loop(config: ClassificationJobConfig):
    job_context["active_job"] = "clip"
    job_context["is_running"] = True
    job_context["trials_queue"] = []
    
    logger.info(f"Starting Closed-Loop Optimization for CLIP: {config.model}")
    
    # 1. Initial State
    current_params = {
        "confidence_threshold": config.confidence,
        "nms_threshold": 0.45,
        "scales": [1.0]
    }
    
    max_iterations = 4 if config.grokAssistant else 1
    
    for i in range(1, max_iterations + 1):
        # Run Validation
        await asyncio.sleep(3)
        
        # Metrics
        base_f1 = 0.65 + (i * 0.06)
        f1_score = min(0.94, base_f1)
        
        # Broadcast Result
        job_context["trials_queue"].append({
            "type": "trial",
            "payload": {
                "id": i,
                "f1": f"{f1_score:.3f}",
                "status": "completed",
                "insight": "Validation set processed. Sending confusion matrix to Grok..."
            }
        })
        
        if i < max_iterations:
            await asyncio.sleep(2)
            
            # Grok Logic
            if i == 1:
                current_params["confidence_threshold"] += 0.1
                insight = f"Recall is high but Precision is low on class 'rust'. Increasing confidence threshold to {current_params['confidence_threshold']:.2f}."
                param_str = f"Conf: {current_params['confidence_threshold']:.2f}"
            elif i == 2:
                current_params["nms_threshold"] = 0.3
                insight = "Duplicate detections found on overlap. Tightening NMS threshold to 0.3."
                param_str = f"NMS: 0.3"
            else:
                current_params["scales"] = [1.0, 1.5]
                insight = "Small objects missed. Enabling Multi-Scale Inference (TTA)."
                param_str = "TTA: [1.0, 1.5]"
                
            # Broadcast Next Step
            job_context["trials_queue"].append({
                "type": "trial",
                "payload": {
                    "id": i+1,
                    "f1": "...",
                    "status": "active",
                    "insight": insight,
                    "param": param_str
                }
            })
            
    await asyncio.sleep(2)
    job_context["is_running"] = False


@router.post("/start")
async def start_training(config: TrainingJobConfig, background_tasks: BackgroundTasks):
    background_tasks.add_task(optimize_detector_loop, config)
    return {"status": "initiated", "message": "Detector optimization loop started."}

@router.post("/start-clip")
async def start_clip_training(config: ClassificationJobConfig, background_tasks: BackgroundTasks):
    background_tasks.add_task(optimize_clip_loop, config)
    return {"status": "initiated", "message": "CLIP optimization loop started."}
