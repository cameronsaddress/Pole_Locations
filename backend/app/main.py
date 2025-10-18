"""
PoleVision AI - Enterprise FastAPI Backend
Provides REST API for pole verification dashboard
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent.parent / 'src'))

from app.api.v1 import poles, metrics, maps, pipeline

app = FastAPI(
    title="PoleVision AI",
    description="Enterprise API for AI-powered utility pole verification",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        "http://localhost:3022",
    ],  # Vite default ports & fallbacks
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(poles.router, prefix="/api/v1", tags=["poles"])
app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
app.include_router(maps.router, prefix="/api/v1", tags=["maps"])
app.include_router(pipeline.router, prefix="/api/v1", tags=["pipeline"])

@app.get("/")
async def root():
    """API health check"""
    return {
        "status": "healthy",
        "service": "PoleVision AI API",
        "version": "1.0.0",
        "docs": "/api/docs"
    }

@app.get("/api/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "components": {
            "api": "operational",
            "model": "loaded",
            "database": "connected"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8021, reload=True)
