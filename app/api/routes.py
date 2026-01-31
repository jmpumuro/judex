"""
FastAPI routes for Judex service.

This module contains utility endpoints (health, models).
Primary API is in evaluations.py and criteria_routes.py.
"""
from fastapi import APIRouter
from app.api.schemas import HealthResponse, ModelsListResponse, ModelInfo
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("api.routes")

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version=settings.version,
        models_loaded=True
    )


@router.get("/models", response_model=ModelsListResponse)
async def list_models():
    """List configured models and their cache status."""
    models = [
        # Object Detection
        ModelInfo(
            model_id=settings.yolo26_model_id,
            model_type="vision",
            cached=True,
            status="ready"
        ),
        ModelInfo(
            model_id="yolov8n.pt",  # YOLOE
            model_type="vision_realtime",
            cached=True,
            status="ready"
        ),
        ModelInfo(
            model_id="yolov8s-worldv2.pt",  # YOLO-World
            model_type="vision_openworld",
            cached=True,
            status="ready"
        ),
        # Violence Detection (X-CLIP)
        ModelInfo(
            model_id=settings.violence_model_id,
            model_type="violence_xclip",
            cached=True,
            status="ready"
        ),
        # Violence Detection (VideoMAE - Action Specialist)
        ModelInfo(
            model_id="MCG-NJU/videomae-base-finetuned-kinetics",
            model_type="violence_videomae",
            cached=True,
            status="ready"
        ),
        # Pose Estimation (MediaPipe)
        ModelInfo(
            model_id="mediapipe-pose-lite",
            model_type="pose_heuristics",
            cached=True,
            status="ready"
        ),
        # Audio/Speech
        ModelInfo(
            model_id=settings.whisper_model_id,
            model_type="asr",
            cached=True,
            status="ready"
        ),
        # Text Moderation
        ModelInfo(
            model_id=settings.profanity_model_id,
            model_type="moderation",
            cached=True,
            status="ready"
        ),
        ModelInfo(
            model_id=settings.nli_model_id,
            model_type="moderation",
            cached=True,
            status="ready"
        ),
        # LLM
        ModelInfo(
            model_id=settings.qwen_model_id,
            model_type="llm",
            cached=True,
            status="ready" if settings.llm_provider == "qwen" else "disabled"
        )
    ]
    
    return ModelsListResponse(models=models)


@router.get("/llm/status")
async def get_llm_status():
    """
    Get LLM provider status and configuration.
    
    Returns available providers and their health status.
    Industry Standard: Factory pattern with provider discovery.
    """
    try:
        from app.llm.factory import list_providers, get_default_provider
        
        return {
            "default_provider": get_default_provider(),
            "providers": list_providers(),
        }
    except Exception as e:
        logger.warning(f"Failed to get LLM status: {e}")
        return {
            "default_provider": settings.llm_provider,
            "providers": {},
            "error": str(e),
        }
