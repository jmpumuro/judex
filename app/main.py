"""
SafeVid FastAPI application.

API Structure (v1):
- /v1/evaluate - Main evaluation endpoint
- /v1/evaluations/* - Evaluation management
- /v1/criteria/* - Criteria/preset management
- /v1/live/* - Live feed analysis

Legacy endpoints (deprecated):
- /v1/evaluate/batch, /v1/evaluate/generic - Use /v1/evaluate
- /v1/presets/* - Use /v1/criteria/presets
- /v1/results/*, /v1/checkpoints/* - Now internal
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router as utility_router
from app.api.evaluations import router as evaluation_router
from app.api.live import router as live_router
from app.api.criteria_routes import router as criteria_router
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("main")


# Ensure temp directory exists
os.makedirs(settings.temp_dir, exist_ok=True)


def init_database():
    """Initialize database tables and seed data."""
    try:
        from app.db.connection import init_db, get_db_session
        from app.db.seeds import run_all_seeds
        
        logger.info("Initializing database...")
        init_db()
        logger.info("✓ Database tables created")
        
        # Seed built-in data (presets, etc.)
        logger.info("Seeding database...")
        with get_db_session() as session:
            run_all_seeds(session)
        logger.info("✓ Database seeded")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        logger.warning("Database features may not work correctly")


def init_storage():
    """Initialize MinIO object storage."""
    try:
        from app.utils.storage import get_storage_service
        logger.info(f"Initializing MinIO storage ({settings.minio_endpoint})...")
        storage = get_storage_service()
        storage.initialize()
        logger.info("✓ MinIO storage initialized")
    except Exception as e:
        logger.error(f"MinIO storage initialization failed: {e}")
        logger.warning("File storage will fall back to local filesystem")


def preload_models():
    """Pre-load all models at startup using the model registry (singletons)."""
    import threading
    
    def load_in_background():
        try:
            from app.models import preload_all_models
            preload_all_models()
        except Exception as e:
            logger.error(f"Error pre-loading models: {e}")
            logger.warning("Some models will load on first request")
    
    # Run in background thread to not block server startup
    thread = threading.Thread(target=load_in_background, daemon=True)
    thread.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    logger.info("Starting SafeVid service")
    logger.info(f"Models cache: {settings.hf_home}")
    logger.info(f"Temp directory: {settings.temp_dir}")
    logger.info(f"Database: {settings.database_url.split('@')[1] if '@' in settings.database_url else 'configured'}")
    logger.info(f"MinIO: {settings.minio_endpoint}")
    
    # Initialize database
    init_database()
    
    # Initialize MinIO storage
    init_storage()
    
    # Pre-load models in background to warm up
    preload_models()
    
    yield
    
    # Shutdown
    logger.info("Shutting down SafeVid service")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Video evaluation framework with configurable criteria",
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

# ===== New Evaluation-Centric API =====
# Primary API - all new code should use these
app.include_router(evaluation_router)  # /v1/evaluate, /v1/evaluations/*
app.include_router(criteria_router)    # /v1/criteria/*
app.include_router(live_router, prefix=settings.api_prefix)  # /v1/live/*

# ===== Utility Routes =====
# Health check and model info
app.include_router(utility_router, prefix=settings.api_prefix)


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
