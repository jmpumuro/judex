"""
Fusion Configuration - Centralizes all configurable values.

All magic numbers, weights, and class lists are defined here.
Override via environment variables or config file.
"""
from typing import Dict, Set, List
from dataclasses import dataclass, field
import os


@dataclass
class SignalWeights:
    """Configurable weights for signal aggregation."""
    # Violence scoring weights
    violence_video: float = 0.6      # X-CLIP violence model
    violence_visual: float = 0.3     # YOLO weapon detections
    violence_text: float = 0.1       # Text mentions
    
    # Sexual content weights
    sexual_text: float = 0.85
    sexual_person_boost: float = 0.15
    
    # Drug scoring weights
    drug_visual: float = 0.5         # YOLO detections
    drug_text: float = 0.5           # Text mentions
    
    # Controversial scoring weights
    controversial_hate: float = 0.7
    controversial_violence: float = 0.3
    
    # Negative sentiment weights
    negative_violence: float = 0.5
    negative_hate: float = 0.3
    negative_text: float = 0.2
    
    # Default scorer weights
    default_max_weight: float = 0.5
    default_avg_weight: float = 0.5


@dataclass  
class DetectionClasses:
    """Configurable detection class lists."""
    # Violence-related
    weapon_classes: Set[str] = field(default_factory=lambda: {
        "knife", "gun", "weapon", "pistol", "rifle", "sword", 
        "blood", "injury", "fight"
    })
    
    # Drug-related
    drug_classes: Set[str] = field(default_factory=lambda: {
        "cigarette", "bottle", "drug", "pill", "syringe", 
        "needle", "paraphernalia", "smoke", "alcohol"
    })
    
    # Sexual-related (for visual detection)
    sexual_classes: Set[str] = field(default_factory=lambda: {
        "nudity", "lingerie", "underwear"
    })


@dataclass
class ScorerThresholds:
    """Configurable thresholds for scoring logic."""
    # Context boost thresholds
    sexual_person_score_threshold: float = 0.3
    violence_segment_threshold: float = 0.5
    
    # Spam detection thresholds
    spam_high_ocr_count: int = 20
    spam_medium_ocr_count: int = 10
    spam_high_score: float = 0.4
    spam_medium_score: float = 0.2


@dataclass
class FusionConfig:
    """
    Main configuration container for fusion system.
    
    Can be overridden via environment variables:
      - FUSION_VIOLENCE_VIDEO_WEIGHT=0.7
      - FUSION_SPAM_HIGH_OCR_COUNT=30
      etc.
    """
    weights: SignalWeights = field(default_factory=SignalWeights)
    classes: DetectionClasses = field(default_factory=DetectionClasses)
    thresholds: ScorerThresholds = field(default_factory=ScorerThresholds)
    
    @classmethod
    def from_env(cls) -> "FusionConfig":
        """Create config with environment variable overrides."""
        config = cls()
        
        # Weight overrides
        if val := os.getenv("FUSION_VIOLENCE_VIDEO_WEIGHT"):
            config.weights.violence_video = float(val)
        if val := os.getenv("FUSION_VIOLENCE_VISUAL_WEIGHT"):
            config.weights.violence_visual = float(val)
        if val := os.getenv("FUSION_VIOLENCE_TEXT_WEIGHT"):
            config.weights.violence_text = float(val)
        if val := os.getenv("FUSION_DRUG_VISUAL_WEIGHT"):
            config.weights.drug_visual = float(val)
        if val := os.getenv("FUSION_DRUG_TEXT_WEIGHT"):
            config.weights.drug_text = float(val)
            
        # Threshold overrides
        if val := os.getenv("FUSION_SPAM_HIGH_OCR_COUNT"):
            config.thresholds.spam_high_ocr_count = int(val)
        if val := os.getenv("FUSION_SPAM_MEDIUM_OCR_COUNT"):
            config.thresholds.spam_medium_ocr_count = int(val)
        if val := os.getenv("FUSION_SEXUAL_PERSON_THRESHOLD"):
            config.thresholds.sexual_person_score_threshold = float(val)
            
        # Class list overrides (comma-separated)
        if val := os.getenv("FUSION_WEAPON_CLASSES"):
            config.classes.weapon_classes = set(val.lower().split(","))
        if val := os.getenv("FUSION_DRUG_CLASSES"):
            config.classes.drug_classes = set(val.lower().split(","))
            
        return config


# Global config instance (lazily loaded)
_config: FusionConfig = None


def get_fusion_config() -> FusionConfig:
    """Get global fusion config (singleton with env overrides)."""
    global _config
    if _config is None:
        _config = FusionConfig.from_env()
    return _config


def reset_config() -> None:
    """Reset config (for testing)."""
    global _config
    _config = None
