"""
Model Service - FastAPI application for ML model inference.
Designed to run on GPU instances, provides HTTP endpoints for predictions.
"""
import time
import torch
import gc
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from model_service.schemas import (
    HealthResponse,
    YOLORequest, YOLOResponse, Detection,
    ViolenceRequest, ViolenceResponse,
    AudioRequest, TranscriptionResponse,
    TextRequest, ModerationResponse,
    QwenRequest, QwenResponse,
)

# Model instances (lazy loaded)
_models: dict = {}


def get_gpu_memory_mb() -> float | None:
    """Get GPU memory usage in MB."""
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated() / 1024 / 1024
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    print("=" * 60)
    print("Model Service Starting")
    print(f"GPU Available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU Device: {torch.cuda.get_device_name(0)}")
    print("=" * 60)
    
    # Optionally preload models here for faster first request
    # For now, lazy load to reduce startup time
    
    yield
    
    # Cleanup on shutdown
    _models.clear()
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print("Model Service Shutdown")


app = FastAPI(
    title="Judex Model Service",
    description="GPU-optimized ML inference service",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Model Loaders (Lazy)
# =============================================================================

def get_yolo26():
    """Get or load YOLO26 model."""
    if "yolo26" not in _models:
        from app.models.yolo26 import YOLO26Detector
        detector = YOLO26Detector()
        detector.load()
        _models["yolo26"] = detector
    return _models["yolo26"]


def get_yoloworld():
    """Get or load YOLO-World model."""
    if "yoloworld" not in _models:
        from app.models.yoloworld import YOLOWorldDetector
        detector = YOLOWorldDetector()
        detector.load()
        _models["yoloworld"] = detector
    return _models["yoloworld"]


def get_violence():
    """Get or load violence detection model."""
    if "violence" not in _models:
        from app.models.violence import ViolenceDetector
        detector = ViolenceDetector()
        detector.load()
        _models["violence"] = detector
    return _models["violence"]


def get_whisper():
    """Get or load Whisper ASR model."""
    if "whisper" not in _models:
        from app.models.whisper_asr import WhisperASR
        model = WhisperASR()
        model.load()
        _models["whisper"] = model
    return _models["whisper"]


def get_moderation():
    """Get or load text moderation model."""
    if "moderation" not in _models:
        from app.models.moderation import TextModerator
        model = TextModerator()
        model.load()
        _models["moderation"] = model
    return _models["moderation"]


def get_qwen():
    """Get or load Qwen LLM."""
    if "qwen" not in _models:
        from app.models.qwen_llm import QwenLLM
        model = QwenLLM()
        model.load()
        _models["qwen"] = model
    return _models["qwen"]


# =============================================================================
# Health Endpoint
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check with model status."""
    return HealthResponse(
        status="healthy",
        models_loaded={name: True for name in _models.keys()},
        gpu_available=torch.cuda.is_available(),
        gpu_memory_used_mb=get_gpu_memory_mb(),
    )


# =============================================================================
# YOLO26 Endpoint
# =============================================================================

@app.post("/predict/yolo26", response_model=YOLOResponse)
async def predict_yolo26(request: YOLORequest):
    """Run YOLO26 object detection on image."""
    try:
        start = time.perf_counter()
        
        detector = get_yolo26()
        image_bytes = request.decode_image()
        
        # Convert bytes to numpy array
        import numpy as np
        from PIL import Image
        import io
        
        image = Image.open(io.BytesIO(image_bytes))
        image_np = np.array(image)
        
        # Run detection
        results = detector.detect(image_np, confidence=request.confidence)
        
        elapsed = (time.perf_counter() - start) * 1000
        
        detections = [
            Detection(
                label=r.get("label", "unknown"),
                confidence=r.get("confidence", 0.0),
                bbox=r.get("bbox"),
            )
            for r in results
        ]
        
        return YOLOResponse(detections=detections, inference_time_ms=elapsed)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# YOLO-World Endpoint
# =============================================================================

@app.post("/predict/yoloworld", response_model=YOLOResponse)
async def predict_yoloworld(request: YOLORequest):
    """Run YOLO-World open-vocabulary detection on image."""
    try:
        start = time.perf_counter()
        
        detector = get_yoloworld()
        image_bytes = request.decode_image()
        
        import numpy as np
        from PIL import Image
        import io
        
        image = Image.open(io.BytesIO(image_bytes))
        image_np = np.array(image)
        
        # Set classes if provided
        if request.classes:
            detector.set_classes(request.classes)
        
        results = detector.detect(image_np, confidence=request.confidence)
        
        elapsed = (time.perf_counter() - start) * 1000
        
        detections = [
            Detection(
                label=r.get("label", "unknown"),
                confidence=r.get("confidence", 0.0),
                bbox=r.get("bbox"),
            )
            for r in results
        ]
        
        return YOLOResponse(detections=detections, inference_time_ms=elapsed)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Violence Detection Endpoint
# =============================================================================

@app.post("/predict/violence", response_model=ViolenceResponse)
async def predict_violence(request: ViolenceRequest):
    """Run violence detection on video frames."""
    try:
        start = time.perf_counter()
        
        detector = get_violence()
        
        import numpy as np
        from PIL import Image
        import io
        
        frames = []
        for frame_b64 in request.frames_b64:
            import base64
            frame_bytes = base64.b64decode(frame_b64)
            image = Image.open(io.BytesIO(frame_bytes))
            frames.append(np.array(image))
        
        result = detector.predict(frames)
        
        elapsed = (time.perf_counter() - start) * 1000
        
        return ViolenceResponse(
            is_violent=result.get("is_violent", False),
            confidence=result.get("confidence", 0.0),
            label=result.get("label", "unknown"),
            inference_time_ms=elapsed,
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Whisper ASR Endpoint
# =============================================================================

@app.post("/predict/whisper", response_model=TranscriptionResponse)
async def predict_whisper(request: AudioRequest):
    """Transcribe audio using Whisper."""
    try:
        start = time.perf_counter()
        
        model = get_whisper()
        audio_bytes = request.decode_audio()
        
        # Save to temp file (Whisper needs file path)
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name
        
        try:
            result = model.transcribe(temp_path, language=request.language)
        finally:
            os.unlink(temp_path)
        
        elapsed = (time.perf_counter() - start) * 1000
        
        return TranscriptionResponse(
            text=result.get("text", ""),
            language=result.get("language"),
            inference_time_ms=elapsed,
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Text Moderation Endpoint
# =============================================================================

@app.post("/predict/moderation", response_model=ModerationResponse)
async def predict_moderation(request: TextRequest):
    """Moderate text for harmful content."""
    try:
        start = time.perf_counter()
        
        model = get_moderation()
        result = model.moderate(request.text)
        
        elapsed = (time.perf_counter() - start) * 1000
        
        return ModerationResponse(
            is_flagged=result.get("flagged", False),
            categories=result.get("categories", {}),
            scores=result.get("scores", {}),
            inference_time_ms=elapsed,
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Qwen LLM Endpoint
# =============================================================================

@app.post("/predict/qwen", response_model=QwenResponse)
async def predict_qwen(request: QwenRequest):
    """Generate text using Qwen LLM."""
    try:
        start = time.perf_counter()
        
        model = get_qwen()
        result = model.generate(
            prompt=request.prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )
        
        elapsed = (time.perf_counter() - start) * 1000
        
        return QwenResponse(
            text=result.get("text", ""),
            tokens_generated=result.get("tokens", 0),
            inference_time_ms=elapsed,
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Utility Endpoints
# =============================================================================

@app.post("/unload/{model_name}")
async def unload_model(model_name: str):
    """Unload a specific model to free memory."""
    if model_name in _models:
        del _models[model_name]
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return {"status": "unloaded", "model": model_name}
    return {"status": "not_loaded", "model": model_name}


@app.post("/preload")
async def preload_models(models: list[str] = None):
    """Preload specified models (or all if none specified)."""
    all_models = ["yolo26", "yoloworld", "violence", "whisper", "moderation"]
    to_load = models if models else all_models
    
    loaded = []
    for name in to_load:
        try:
            if name == "yolo26":
                get_yolo26()
            elif name == "yoloworld":
                get_yoloworld()
            elif name == "violence":
                get_violence()
            elif name == "whisper":
                get_whisper()
            elif name == "moderation":
                get_moderation()
            elif name == "qwen":
                get_qwen()
            loaded.append(name)
        except Exception as e:
            print(f"Failed to load {name}: {e}")
    
    return {"loaded": loaded, "gpu_memory_mb": get_gpu_memory_mb()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
