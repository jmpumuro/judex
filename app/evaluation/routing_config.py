"""
Routing Configuration - Centralized configuration for criterion-to-detector routing.

This separates configuration from logic, making the routing system
configurable without code changes.
"""
from typing import Dict, List, Set
from dataclasses import dataclass, field
from enum import Enum
import os


class DetectorCapability(str, Enum):
    """What each detector can analyze."""
    VISUAL_OBJECTS = "visual_objects"          # YOLO26 - standard object detection
    VISUAL_OPEN_VOCAB = "visual_open_vocab"    # YOLOWORLD - open vocabulary detection
    VIOLENCE_VIDEO = "violence_video"          # X-CLIP - video violence analysis
    AUDIO_SPEECH = "audio_speech"              # Whisper - speech transcription
    VISUAL_TEXT = "visual_text"                # OCR - on-screen text extraction
    TEXT_MODERATION = "text_moderation"        # Content moderation of text


@dataclass
class DetectorConfig:
    """Configuration for a single detector."""
    id: str
    capabilities: List[DetectorCapability]
    priority: int  # Lower = runs earlier
    always_include: bool = False


@dataclass
class RoutingConfig:
    """
    Complete routing configuration.
    
    Override via environment variables:
      - ROUTING_DEFAULT_DETECTORS: comma-separated list of always-included detectors
      - ROUTING_MIN_KEYWORD_LENGTH: minimum keyword length (default 3)
    """
    # Detector definitions
    detectors: Dict[str, DetectorConfig] = field(default_factory=dict)
    
    # Keyword -> capabilities mapping
    keyword_to_capabilities: Dict[str, List[DetectorCapability]] = field(default_factory=dict)
    
    # Default detectors when no match
    default_detector_ids: Set[str] = field(default_factory=set)
    
    # Minimum keyword length for matching
    min_keyword_length: int = 3
    
    @classmethod
    def create_default(cls) -> "RoutingConfig":
        """Create default routing configuration."""
        return cls(
            detectors={
                "yolo26": DetectorConfig(
                    id="yolo26",
                    capabilities=[DetectorCapability.VISUAL_OBJECTS],
                    priority=10,
                    always_include=True
                ),
                "yoloworld": DetectorConfig(
                    id="yoloworld", 
                    capabilities=[DetectorCapability.VISUAL_OPEN_VOCAB],
                    priority=15,
                    always_include=True
                ),
                "xclip": DetectorConfig(
                    id="xclip",
                    capabilities=[DetectorCapability.VIOLENCE_VIDEO],
                    priority=20
                ),
                "whisper": DetectorConfig(
                    id="whisper",
                    capabilities=[DetectorCapability.AUDIO_SPEECH],
                    priority=30,
                    always_include=True
                ),
                "ocr": DetectorConfig(
                    id="ocr",
                    capabilities=[DetectorCapability.VISUAL_TEXT],
                    priority=40
                ),
                "text_moderation": DetectorConfig(
                    id="text_moderation",
                    capabilities=[DetectorCapability.TEXT_MODERATION],
                    priority=50
                ),
            },
            keyword_to_capabilities={
                # Violence-related
                "violence": [DetectorCapability.VIOLENCE_VIDEO, DetectorCapability.VISUAL_OBJECTS, DetectorCapability.VISUAL_OPEN_VOCAB],
                "fight": [DetectorCapability.VIOLENCE_VIDEO, DetectorCapability.VISUAL_OBJECTS],
                "weapon": [DetectorCapability.VISUAL_OBJECTS, DetectorCapability.VISUAL_OPEN_VOCAB],
                "blood": [DetectorCapability.VISUAL_OBJECTS, DetectorCapability.VIOLENCE_VIDEO],
                "gore": [DetectorCapability.VISUAL_OBJECTS, DetectorCapability.VIOLENCE_VIDEO],
                
                # Text/speech moderation
                "profanity": [DetectorCapability.AUDIO_SPEECH, DetectorCapability.TEXT_MODERATION, DetectorCapability.VISUAL_TEXT],
                "hate": [DetectorCapability.AUDIO_SPEECH, DetectorCapability.TEXT_MODERATION, DetectorCapability.VISUAL_TEXT],
                "harassment": [DetectorCapability.AUDIO_SPEECH, DetectorCapability.TEXT_MODERATION],
                "slur": [DetectorCapability.AUDIO_SPEECH, DetectorCapability.TEXT_MODERATION],
                "discrimination": [DetectorCapability.AUDIO_SPEECH, DetectorCapability.TEXT_MODERATION],
                "extremism": [DetectorCapability.AUDIO_SPEECH, DetectorCapability.TEXT_MODERATION],
                
                # Sexual content
                "sexual": [DetectorCapability.VISUAL_OBJECTS, DetectorCapability.VISUAL_OPEN_VOCAB, DetectorCapability.TEXT_MODERATION],
                "nudity": [DetectorCapability.VISUAL_OBJECTS, DetectorCapability.VISUAL_OPEN_VOCAB],
                "adult": [DetectorCapability.VISUAL_OBJECTS, DetectorCapability.TEXT_MODERATION],
                
                # Drugs
                "drug": [DetectorCapability.VISUAL_OBJECTS, DetectorCapability.VISUAL_OPEN_VOCAB, DetectorCapability.TEXT_MODERATION],
                "substance": [DetectorCapability.VISUAL_OBJECTS, DetectorCapability.VISUAL_OPEN_VOCAB],
                
                # General text-based
                "spam": [DetectorCapability.VISUAL_TEXT, DetectorCapability.TEXT_MODERATION, DetectorCapability.AUDIO_SPEECH],
                "scam": [DetectorCapability.VISUAL_TEXT, DetectorCapability.TEXT_MODERATION, DetectorCapability.AUDIO_SPEECH],
                "controversial": [DetectorCapability.AUDIO_SPEECH, DetectorCapability.TEXT_MODERATION],
                "negative": [DetectorCapability.TEXT_MODERATION, DetectorCapability.AUDIO_SPEECH],
            },
            default_detector_ids={"yolo26", "yoloworld", "xclip", "whisper", "ocr", "text_moderation"},
            min_keyword_length=3
        )
    
    @classmethod
    def from_env(cls) -> "RoutingConfig":
        """Create config with environment variable overrides."""
        config = cls.create_default()
        
        # Override default detectors
        if val := os.getenv("ROUTING_DEFAULT_DETECTORS"):
            config.default_detector_ids = set(val.split(","))
        
        # Override min keyword length
        if val := os.getenv("ROUTING_MIN_KEYWORD_LENGTH"):
            config.min_keyword_length = int(val)
            
        return config


# Singleton
_routing_config: RoutingConfig = None


def get_routing_config() -> RoutingConfig:
    """Get global routing config."""
    global _routing_config
    if _routing_config is None:
        _routing_config = RoutingConfig.from_env()
    return _routing_config


def reset_routing_config() -> None:
    """Reset routing config (for testing)."""
    global _routing_config
    _routing_config = None
