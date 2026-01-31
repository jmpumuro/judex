"""
Judex FastAPI application.

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
from app.api.stages_routes import router as stages_router
from app.api.config_routes import router as config_router
from app.api.chat_routes import router as chat_router
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("main")


# Ensure temp directory exists
os.makedirs(settings.temp_dir, exist_ok=True)


def init_database():
    """Initialize database tables and seed data.
    
    Non-blocking: logs error and continues if database unavailable.
    Set SKIP_DB_INIT=true to skip entirely.
    """
    import os
    if os.getenv("SKIP_DB_INIT", "false").lower() == "true":
        logger.info("SKIP_DB_INIT=true - skipping database initialization")
        return
        
    try:
        import signal
        
        # Timeout handler to prevent hanging on unreachable database
        def timeout_handler(signum, frame):
            raise TimeoutError("Database connection timed out")
        
        # Set 10 second timeout (only works on Unix)
        old_handler = None
        try:
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(10)
        except (ValueError, AttributeError):
            pass  # SIGALRM not available on Windows
        
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
        finally:
            # Reset alarm
            try:
                signal.alarm(0)
                if old_handler:
                    signal.signal(signal.SIGALRM, old_handler)
            except (ValueError, AttributeError):
                pass
        
    except TimeoutError:
        logger.error("Database connection timed out after 10s")
        logger.warning("Database features may not work - set DATABASE_URL correctly")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        logger.warning("Database features may not work correctly")


def init_storage():
    """Initialize MinIO object storage.
    
    Non-blocking: logs error and continues if MinIO unavailable.
    Set SKIP_STORAGE_INIT=true to skip entirely.
    """
    import os
    if os.getenv("SKIP_STORAGE_INIT", "false").lower() == "true":
        logger.info("SKIP_STORAGE_INIT=true - skipping storage initialization")
        return
        
    try:
        from app.utils.storage import get_storage_service
        logger.info(f"Initializing MinIO storage ({settings.minio_endpoint})...")
        storage = get_storage_service()
        storage.initialize()
        logger.info("✓ MinIO storage initialized")
    except Exception as e:
        logger.error(f"MinIO storage initialization failed: {e}")
        logger.warning("File storage will fall back to local filesystem")


def init_external_stages():
    """Load external stage configurations from database.
    
    Non-blocking: logs warning and continues if unavailable.
    Skipped if database initialization was skipped.
    """
    import os
    if os.getenv("SKIP_DB_INIT", "false").lower() == "true":
        logger.info("Skipping external stages (database not initialized)")
        return
        
    try:
        from app.external_stages.registry import load_external_stages_from_db
        logger.info("Loading external stage configurations...")
        load_external_stages_from_db()
        logger.info("✓ External stages loaded")
    except Exception as e:
        logger.warning(f"Could not load external stages: {e}")
        logger.info("External stages can be configured via Settings")


def preload_models():
    """Pre-load all models at startup using the model registry (singletons).
    
    Skipped when:
    - USE_MODEL_SERVICE=true (models handled by separate service)
    - PRELOAD_MODELS=false (lazy load for faster startup)
    """
    # Skip if using external model service (separated architecture)
    if settings.use_model_service:
        logger.info("Using external model service - skipping local model preload")
        return
    
    # Skip if preloading disabled (for faster Cloud Run startup)
    if not settings.preload_models:
        logger.info("PRELOAD_MODELS=false - models will lazy-load on first request")
        return
    
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


async def recover_interrupted_pipelines():
    """
    Recover any pipelines interrupted by container restart.
    
    Industry standard: On startup, detect stuck evaluations and resume them
    using existing reprocess infrastructure (no redundancy).
    
    Runs in background to not block server startup.
    Skipped if database initialization was skipped.
    """
    import asyncio
    import os
    
    if os.getenv("SKIP_DB_INIT", "false").lower() == "true":
        logger.info("Skipping pipeline recovery (database not initialized)")
        return
    
    async def recovery_task():
        # Wait for services to fully initialize
        await asyncio.sleep(15)
        
        try:
            from app.pipeline.recovery import recover_all_stuck_evaluations
            
            logger.info("Checking for stuck evaluations to recover...")
            result = await recover_all_stuck_evaluations(
                stuck_threshold_minutes=10,  # Industry standard: catch stuck faster
                max_concurrent=2,
            )
            
            total = result.get("total", 0)
            recovered = result.get("recovered", 0)
            failed = result.get("failed", 0)
            
            if total == 0:
                logger.info("✓ No stuck evaluations found")
            elif failed == 0:
                logger.info(f"✓ Recovered {recovered}/{total} stuck evaluations")
            else:
                logger.warning(f"Recovery: {recovered} succeeded, {failed} failed out of {total}")
                
        except Exception as e:
            logger.error(f"Pipeline recovery check failed: {e}")
            logger.info("Use GET /v1/evaluations/stuck to check manually")
    
    # Run in background
    asyncio.create_task(recovery_task())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    logger.info("Starting Judex service")
    logger.info(f"Models cache: {settings.hf_home}")
    logger.info(f"Temp directory: {settings.temp_dir}")
    logger.info(f"Database: {settings.database_url.split('@')[1] if '@' in settings.database_url else 'configured'}")
    logger.info(f"MinIO: {settings.minio_endpoint}")
    
    # Initialize database
    init_database()
    
    # Initialize MinIO storage
    init_storage()
    
    # Load external stages from database
    init_external_stages()
    
    # Pre-load models in background to warm up
    preload_models()
    
    # Recover any interrupted pipelines (industry standard: resume from crash)
    await recover_interrupted_pipelines()
    
    yield
    
    # Shutdown
    logger.info("Shutting down Judex service")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Vision evaluation framework with configurable criteria",
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
app.include_router(stages_router)      # /v1/stages/*
app.include_router(config_router)      # /v1/config/* - Schema, validation, versioning
app.include_router(chat_router)        # /v1/evaluations/{id}/chat/* - ReportChat agent
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
