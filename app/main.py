"""
SafeVid FastAPI application.
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.api.live import router as live_router
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("main")


# Ensure temp directory exists
os.makedirs(settings.temp_dir, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    logger.info("Starting SafeVid service")
    logger.info(f"Models cache: {settings.hf_home}")
    logger.info(f"Temp directory: {settings.temp_dir}")
    
    # Startup: Skip pre-loading for now (models load on-demand)
    logger.info("Models will be loaded on first request (lazy loading enabled)")
    
    # Note: Pre-loading disabled temporarily due to long X-CLIP load times
    # Models will be loaded by singleton pattern on first use
    
    yield
    
    # Shutdown
    logger.info("Shutting down SafeVid service")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Child safety video analysis service using YOLO26 and HF models",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router, prefix=settings.api_prefix)
app.include_router(live_router, prefix=settings.api_prefix)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": settings.app_name,
        "version": settings.version,
        "status": "running"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
