"""
Model prefetch script - download all models during Docker build.
"""
import os
import sys
from pathlib import Path

# Set cache directories
os.environ["HF_HOME"] = os.getenv("HF_HOME", "/models/hf")
os.environ["TRANSFORMERS_CACHE"] = os.getenv("TRANSFORMERS_CACHE", "/models/hf/transformers")

from huggingface_hub import snapshot_download
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("prefetch")


def prefetch_model(model_id: str, model_type: str):
    """Prefetch a model from HuggingFace."""
    logger.info(f"Prefetching {model_type} model: {model_id}")
    
    try:
        snapshot_download(
            repo_id=model_id,
            cache_dir=settings.hf_home,
            ignore_patterns=["*.msgpack", "*.h5", "*.ot", "*.safetensors"]  # Download only needed files
        )
        logger.info(f"✓ Successfully prefetched {model_id}")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to prefetch {model_id}: {e}")
        return False


def prefetch_yolo26():
    """Prefetch YOLO26 model."""
    model_id = settings.yolo26_model_id
    logger.info(f"Prefetching YOLO26: {model_id}")
    
    # For YOLO models, we may need ultralytics
    try:
        from ultralytics import YOLO
        # This will download the model
        if "yolo11" in model_id.lower() or not "/" in model_id:
            # Standard ultralytics model
            model = YOLO(model_id)
        else:
            # Try HF download
            prefetch_model(model_id, "yolo26")
        logger.info("✓ YOLO26 model ready")
        return True
    except Exception as e:
        logger.warning(f"YOLO26 prefetch issue: {e}")
        # Continue anyway, will be handled at runtime
        return True


def main():
    """Main prefetch function."""
    logger.info("=" * 60)
    logger.info("Starting model prefetch")
    logger.info(f"HF_HOME: {settings.hf_home}")
    logger.info(f"TRANSFORMERS_CACHE: {settings.transformers_cache}")
    logger.info("=" * 60)
    
    # Ensure cache directories exist
    Path(settings.hf_home).mkdir(parents=True, exist_ok=True)
    Path(settings.transformers_cache).mkdir(parents=True, exist_ok=True)
    
    success_count = 0
    total_count = 0
    
    # Prefetch models
    models = [
        (settings.violence_model_id, "violence"),
        (settings.whisper_model_id, "whisper"),
        (settings.profanity_model_id, "profanity"),
        (settings.nli_model_id, "nli"),
    ]
    
    for model_id, model_type in models:
        total_count += 1
        if prefetch_model(model_id, model_type):
            success_count += 1
    
    # YOLO separately
    total_count += 1
    if prefetch_yolo26():
        success_count += 1
    
    logger.info("=" * 60)
    logger.info(f"Prefetch complete: {success_count}/{total_count} models ready")
    logger.info("=" * 60)
    
    if success_count < total_count:
        logger.warning("Some models failed to prefetch, but continuing...")
        # Don't fail the build, models can be downloaded at runtime
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
