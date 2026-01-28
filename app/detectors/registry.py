"""
Detector registry - maps detector types to implementations.

New detectors can be registered here to make them available in EvaluationSpecs.
"""
from typing import Dict, Type, List, Optional
from app.evaluation.spec import DetectorSpec, DetectorType
from app.detectors.base import BaseDetector, DetectorResult


class DetectorNotFoundError(Exception):
    """Raised when a detector type is not registered."""
    pass


class DetectorRegistry:
    """
    Registry for detector implementations.
    
    Maps DetectorType -> BaseDetector subclass
    """
    
    _detectors: Dict[str, Type[BaseDetector]] = {}
    _instances: Dict[str, BaseDetector] = {}  # Cache for singleton detectors
    
    @classmethod
    def register(
        cls,
        detector_type: str,
        detector_class: Type[BaseDetector]
    ) -> None:
        """
        Register a detector implementation.
        
        Args:
            detector_type: DetectorType value (e.g., "yolo26")
            detector_class: BaseDetector subclass
        """
        cls._detectors[detector_type] = detector_class
    
    @classmethod
    def get(cls, spec: DetectorSpec) -> BaseDetector:
        """
        Get a detector instance for the given spec.
        
        Args:
            spec: DetectorSpec with type and configuration
            
        Returns:
            Configured BaseDetector instance
            
        Raises:
            DetectorNotFoundError: If detector type not registered
        """
        detector_type = spec.type.value
        
        if detector_type not in cls._detectors:
            available = list(cls._detectors.keys())
            raise DetectorNotFoundError(
                f"Detector type '{detector_type}' not registered. "
                f"Available: {available}"
            )
        
        detector_class = cls._detectors[detector_type]
        
        # Create new instance (could add caching if needed)
        return detector_class(spec)
    
    @classmethod
    def get_cached(cls, spec: DetectorSpec) -> BaseDetector:
        """
        Get a cached detector instance (singleton per detector_id).
        
        Useful when the same detector is used multiple times.
        """
        cache_key = f"{spec.type.value}:{spec.id}"
        
        if cache_key not in cls._instances:
            cls._instances[cache_key] = cls.get(spec)
        
        return cls._instances[cache_key]
    
    @classmethod
    def clear_cache(cls) -> None:
        """Clear the instance cache."""
        for instance in cls._instances.values():
            instance.unload_model()
        cls._instances.clear()
    
    @classmethod
    def list_types(cls) -> List[str]:
        """List registered detector types."""
        return list(cls._detectors.keys())
    
    @classmethod
    def is_registered(cls, detector_type: str) -> bool:
        """Check if a detector type is registered."""
        return detector_type in cls._detectors


# ===== CONVENIENCE FUNCTIONS =====

def get_detector(spec: DetectorSpec) -> BaseDetector:
    """Get a detector instance for the given spec."""
    return DetectorRegistry.get(spec)


def register_detector(
    detector_type: str,
    detector_class: Type[BaseDetector]
) -> None:
    """Register a detector implementation."""
    DetectorRegistry.register(detector_type, detector_class)


def list_detectors() -> List[str]:
    """List registered detector types."""
    return DetectorRegistry.list_types()


# ===== REGISTER BUILT-IN DETECTORS =====

def _register_builtin_detectors():
    """Register all built-in detector implementations."""
    
    # Import and register each detector wrapper
    from app.detectors.wrappers.yolo26_detector import YOLO26DetectorWrapper
    from app.detectors.wrappers.yoloworld_detector import YOLOWorldDetectorWrapper
    from app.detectors.wrappers.xclip_detector import XCLIPViolenceDetector
    from app.detectors.wrappers.whisper_detector import WhisperASRDetector
    from app.detectors.wrappers.ocr_detector import OCRDetector
    from app.detectors.wrappers.text_moderation_detector import TextModerationDetector
    
    DetectorRegistry.register(DetectorType.YOLO26.value, YOLO26DetectorWrapper)
    DetectorRegistry.register(DetectorType.YOLOWORLD.value, YOLOWorldDetectorWrapper)
    DetectorRegistry.register(DetectorType.XCLIP_VIOLENCE.value, XCLIPViolenceDetector)
    DetectorRegistry.register(DetectorType.WHISPER_ASR.value, WhisperASRDetector)
    DetectorRegistry.register(DetectorType.OCR.value, OCRDetector)
    DetectorRegistry.register(DetectorType.TEXT_MODERATION.value, TextModerationDetector)


# Auto-register on import
try:
    _register_builtin_detectors()
except ImportError as e:
    # Some detectors may not be available (missing dependencies)
    import logging
    logging.getLogger(__name__).warning(f"Failed to register some detectors: {e}")
