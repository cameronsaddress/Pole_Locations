import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routers import ops, training, work_orders

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- LIFESPAN MANAGER ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("PoleVision Enterprise API starting up...")
    yield
    # Shutdown
    logger.info("Shutting down...")

app = FastAPI(lifespan=lifespan)

# --- MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for the UI
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- ROUTERS ---
app.include_router(ops.router)
app.include_router(training.router, prefix="/api/v2/training")
app.include_router(work_orders.router)

# --- WEBSOCKETS ---
@app.websocket("/ws/training")
async def training_endpoint(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({
        "type": "log", 
        "payload": "Connected to NVIDIA GB10 Telemetry & Job Bus"
    })
    
    import subprocess
    
    def get_real_gpu_metrics():
        try:
            # Query nvidia-smi for real data from the GPU container
            result = subprocess.run(
                ['/usr/bin/docker', 'exec', 'polelocations-gpu', 'nvidia-smi', '--query-gpu=utilization.gpu,memory.used,power.draw', '--format=csv,noheader,nounits'],
                capture_output=True, text=True
            )
            output = result.stdout.strip()
            if output:
                # Output format example: "0, 4, 10" or "95, [N/A], 52.78"
                parts = [p.strip() for p in output.split(',')]
                
                def safe_parse(val, type_func):
                    try:
                        return type_func(val)
                    except:
                        return 0

                return {
                    "gpu": safe_parse(parts[0], int),
                    "vram": safe_parse(parts[1], float) / 1024, # MB to GB
                    "power": safe_parse(parts[2], float)
                }
        except Exception:
            pass
        return {"gpu": 0, "vram": 0, "power": 0}
    
    try:
        while True:
            # 1. Emit REAL Telemetry
            data = get_real_gpu_metrics()
            
            telemetry = {
                "type": "telemetry",
                "payload": {
                    "gpu": data['gpu'],
                    "vram": round(data['vram'], 1),
                    "power": data['power'],
                    "status": "Training" if training.job_context["is_running"] else "Idle"
                }
            }
            await websocket.send_json(telemetry)
            
            # 2. Check for Events (Logs, Stats, Trials) from Workers
            # We pop all available events to ensure low latency
            while training.job_context["trials_queue"]:
                event = training.job_context["trials_queue"].pop(0)
                await websocket.send_json(event)
            
            await asyncio.sleep(0.5) # Poll frequency
            
    except WebSocketDisconnect:
        logger.info("Training Dashboard disconnected")
    except Exception as e:
        logger.error(f"WebSocket Error: {e}")
            
    except WebSocketDisconnect:
        logger.info("Training Dashboard disconnected")
    except Exception as e:
        logger.error(f"WebSocket Error: {e}")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "2.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
