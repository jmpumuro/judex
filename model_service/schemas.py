"""
Request/Response schemas for model service endpoints.
"""
from pydantic import BaseModel, Field
from typing import Optional
import base64


class ImageRequest(BaseModel):
    """Request with base64 encoded image."""
    image_b64: str = Field(..., description="Base64 encoded image (JPEG/PNG)")
    
    def decode_image(self) -> bytes:
        """Decode base64 image to bytes."""
        return base64.b64decode(self.image_b64)


class FramesRequest(BaseModel):
    """Request with multiple base64 encoded frames."""
    frames_b64: list[str] = Field(..., description="List of base64 encoded frames")
    
    def decode_frames(self) -> list[bytes]:
        """Decode all frames."""
        return [base64.b64decode(f) for f in self.frames_b64]


class AudioRequest(BaseModel):
    """Request with base64 encoded audio."""
    audio_b64: str = Field(..., description="Base64 encoded audio (WAV/MP3)")
    language: Optional[str] = Field(None, description="Language hint for transcription")
    
    def decode_audio(self) -> bytes:
        """Decode base64 audio to bytes."""
        return base64.b64decode(self.audio_b64)


class TextRequest(BaseModel):
    """Request with text for moderation."""
    text: str = Field(..., description="Text to moderate")


class YOLORequest(ImageRequest):
    """YOLO detection request."""
    confidence: float = Field(0.25, ge=0, le=1, description="Confidence threshold")
    classes: Optional[list[str]] = Field(None, description="Classes to detect (YOLO-World only)")


class ViolenceRequest(FramesRequest):
    """Violence detection request with video frames."""
    pass


class QwenRequest(BaseModel):
    """Qwen LLM generation request."""
    prompt: str = Field(..., description="Input prompt")
    max_tokens: int = Field(512, ge=1, le=4096)
    temperature: float = Field(0.7, ge=0, le=2)


# Response schemas

class Detection(BaseModel):
    """Single detection result."""
    label: str
    confidence: float
    bbox: Optional[list[float]] = None  # [x1, y1, x2, y2] normalized


class YOLOResponse(BaseModel):
    """YOLO detection response."""
    detections: list[Detection]
    inference_time_ms: float


class ViolenceResponse(BaseModel):
    """Violence detection response."""
    is_violent: bool
    confidence: float
    label: str
    inference_time_ms: float


class TranscriptionResponse(BaseModel):
    """Whisper transcription response."""
    text: str
    language: Optional[str] = None
    inference_time_ms: float


class ModerationResponse(BaseModel):
    """Text moderation response."""
    is_flagged: bool
    categories: dict[str, bool]
    scores: dict[str, float]
    inference_time_ms: float


class QwenResponse(BaseModel):
    """Qwen LLM response."""
    text: str
    tokens_generated: int
    inference_time_ms: float


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    models_loaded: dict[str, bool]
    gpu_available: bool
    gpu_memory_used_mb: Optional[float] = None
