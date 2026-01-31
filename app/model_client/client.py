"""
HTTP Client for Model Service.
Provides async methods to call model prediction endpoints.
"""
import base64
import httpx
import numpy as np
from typing import Optional
from PIL import Image
import io

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("model_client")

# Singleton instance
_client: Optional["ModelClient"] = None


class ModelClient:
    """
    HTTP client for the Model Service.
    
    Usage:
        client = ModelClient("http://localhost:8001")
        result = await client.detect_yolo26(image_np)
    """
    
    def __init__(self, base_url: str = None, timeout: float = 120.0):
        """
        Initialize the model client.
        
        Args:
            base_url: Model service URL (default from settings)
            timeout: Request timeout in seconds (default 120s for large models)
        """
        self.base_url = base_url or settings.model_service_url
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        logger.info(f"ModelClient initialized with base_url={self.base_url}")
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    def _encode_image(self, image: np.ndarray, format: str = "JPEG") -> str:
        """Encode numpy image to base64."""
        pil_image = Image.fromarray(image)
        buffer = io.BytesIO()
        pil_image.save(buffer, format=format)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    
    def _encode_frames(self, frames: list[np.ndarray]) -> list[str]:
        """Encode multiple frames to base64."""
        return [self._encode_image(f) for f in frames]
    
    def _encode_audio(self, audio_bytes: bytes) -> str:
        """Encode audio bytes to base64."""
        return base64.b64encode(audio_bytes).decode("utf-8")
    
    # =========================================================================
    # Health Check
    # =========================================================================
    
    async def health(self) -> dict:
        """Check model service health."""
        client = await self._get_client()
        response = await client.get("/health")
        response.raise_for_status()
        return response.json()
    
    # =========================================================================
    # YOLO26 Detection
    # =========================================================================
    
    async def detect_yolo26(
        self,
        image: np.ndarray,
        confidence: float = 0.25,
    ) -> list[dict]:
        """
        Run YOLO26 object detection.
        
        Args:
            image: Input image as numpy array (RGB)
            confidence: Detection confidence threshold
            
        Returns:
            List of detections with label, confidence, bbox
        """
        client = await self._get_client()
        
        payload = {
            "image_b64": self._encode_image(image),
            "confidence": confidence,
        }
        
        response = await client.post("/predict/yolo26", json=payload)
        response.raise_for_status()
        
        result = response.json()
        logger.debug(f"YOLO26: {len(result['detections'])} detections in {result['inference_time_ms']:.1f}ms")
        
        return result["detections"]
    
    # =========================================================================
    # YOLO-World Detection
    # =========================================================================
    
    async def detect_yoloworld(
        self,
        image: np.ndarray,
        classes: list[str] = None,
        confidence: float = 0.25,
    ) -> list[dict]:
        """
        Run YOLO-World open-vocabulary detection.
        
        Args:
            image: Input image as numpy array (RGB)
            classes: List of class names to detect
            confidence: Detection confidence threshold
            
        Returns:
            List of detections with label, confidence, bbox
        """
        client = await self._get_client()
        
        payload = {
            "image_b64": self._encode_image(image),
            "confidence": confidence,
        }
        if classes:
            payload["classes"] = classes
        
        response = await client.post("/predict/yoloworld", json=payload)
        response.raise_for_status()
        
        result = response.json()
        logger.debug(f"YOLO-World: {len(result['detections'])} detections in {result['inference_time_ms']:.1f}ms")
        
        return result["detections"]
    
    # =========================================================================
    # Violence Detection
    # =========================================================================
    
    async def detect_violence(self, frames: list[np.ndarray]) -> dict:
        """
        Run violence detection on video frames.
        
        Args:
            frames: List of video frames as numpy arrays (RGB)
            
        Returns:
            Dict with is_violent, confidence, label
        """
        client = await self._get_client()
        
        payload = {
            "frames_b64": self._encode_frames(frames),
        }
        
        response = await client.post("/predict/violence", json=payload)
        response.raise_for_status()
        
        result = response.json()
        logger.debug(f"Violence: {result['label']} ({result['confidence']:.2f}) in {result['inference_time_ms']:.1f}ms")
        
        return {
            "is_violent": result["is_violent"],
            "confidence": result["confidence"],
            "label": result["label"],
        }
    
    # =========================================================================
    # Whisper Transcription
    # =========================================================================
    
    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str = None,
    ) -> dict:
        """
        Transcribe audio using Whisper.
        
        Args:
            audio_bytes: Audio file bytes (WAV/MP3)
            language: Optional language hint
            
        Returns:
            Dict with text, language
        """
        client = await self._get_client()
        
        payload = {
            "audio_b64": self._encode_audio(audio_bytes),
        }
        if language:
            payload["language"] = language
        
        response = await client.post("/predict/whisper", json=payload)
        response.raise_for_status()
        
        result = response.json()
        logger.debug(f"Whisper: {len(result['text'])} chars in {result['inference_time_ms']:.1f}ms")
        
        return {
            "text": result["text"],
            "language": result.get("language"),
        }
    
    # =========================================================================
    # Text Moderation
    # =========================================================================
    
    async def moderate_text(self, text: str) -> dict:
        """
        Moderate text for harmful content.
        
        Args:
            text: Text to moderate
            
        Returns:
            Dict with is_flagged, categories, scores
        """
        client = await self._get_client()
        
        payload = {"text": text}
        
        response = await client.post("/predict/moderation", json=payload)
        response.raise_for_status()
        
        result = response.json()
        logger.debug(f"Moderation: flagged={result['is_flagged']} in {result['inference_time_ms']:.1f}ms")
        
        return {
            "flagged": result["is_flagged"],
            "categories": result["categories"],
            "scores": result["scores"],
        }
    
    # =========================================================================
    # Qwen LLM
    # =========================================================================
    
    async def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> dict:
        """
        Generate text using Qwen LLM.
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            
        Returns:
            Dict with text, tokens_generated
        """
        client = await self._get_client()
        
        payload = {
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        response = await client.post("/predict/qwen", json=payload)
        response.raise_for_status()
        
        result = response.json()
        logger.debug(f"Qwen: {result['tokens_generated']} tokens in {result['inference_time_ms']:.1f}ms")
        
        return {
            "text": result["text"],
            "tokens": result["tokens_generated"],
        }
    
    # =========================================================================
    # Utility
    # =========================================================================
    
    async def preload(self, models: list[str] = None) -> dict:
        """Preload models on the service."""
        client = await self._get_client()
        response = await client.post("/preload", json=models)
        response.raise_for_status()
        return response.json()
    
    async def unload(self, model_name: str) -> dict:
        """Unload a model from the service."""
        client = await self._get_client()
        response = await client.post(f"/unload/{model_name}")
        response.raise_for_status()
        return response.json()


def get_model_client() -> ModelClient:
    """Get singleton model client instance."""
    global _client
    if _client is None:
        _client = ModelClient()
    return _client
