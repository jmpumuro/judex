"""
Unified Configuration Schema for Fusion and Stage Settings.

This module provides:
1. FusionSettings - Policy/verdict strategy controls
2. StageKnobs - Safe, bounded stage/model parameters
3. ConfigSchema - Schema endpoint for UI-driven rendering
4. Validation with user-friendly error messages

Industry Standard: Schema-driven UI rendering - backend defines knobs, frontend renders generically.
"""
from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum


# =============================================================================
# Enums for Type Safety
# =============================================================================

class VerdictStrategy(str, Enum):
    """Strategy for determining final verdict from multiple criteria."""
    ANY_UNSAFE = "any_unsafe"           # UNSAFE if any criterion is unsafe
    MAJORITY_UNSAFE = "majority_unsafe" # UNSAFE if majority of criteria are unsafe
    WEIGHTED_AVERAGE = "weighted_average" # Use weighted average of all scores
    CRITICAL_ONLY = "critical_only"     # Only critical-severity criteria affect verdict
    TOP_N = "top_n"                      # Use top N highest scores


class SensitivityLevel(str, Enum):
    """Pre-configured sensitivity profiles for stages."""
    CONSERVATIVE = "conservative"  # Lower confidence, more detections (catches more)
    BALANCED = "balanced"          # Default behavior
    AGGRESSIVE = "aggressive"      # Higher confidence, fewer detections (higher precision)


class QualityMode(str, Enum):
    """Speed vs quality tradeoff."""
    FAST = "fast"
    BALANCED = "balanced"
    ACCURATE = "accurate"


# =============================================================================
# Fusion / Policy Settings (Level 1 Controls)
# =============================================================================

class CriterionOverride(BaseModel):
    """Override settings for a single criterion."""
    weight: Optional[float] = Field(
        None, 
        ge=0.0, 
        le=5.0, 
        description="Weight multiplier for this criterion (0.0-5.0)"
    )
    threshold_safe: Optional[float] = Field(
        None, 
        ge=0.0, 
        le=1.0,
        description="Custom safe threshold"
    )
    threshold_caution: Optional[float] = Field(
        None, 
        ge=0.0, 
        le=1.0,
        description="Custom caution threshold"
    )
    threshold_unsafe: Optional[float] = Field(
        None, 
        ge=0.0, 
        le=1.0,
        description="Custom unsafe threshold"
    )
    enabled: Optional[bool] = Field(None, description="Override enabled state")
    
    @model_validator(mode='after')
    def validate_threshold_order(self):
        """Ensure thresholds are in ascending order if all provided."""
        safe = self.threshold_safe
        caution = self.threshold_caution
        unsafe = self.threshold_unsafe
        
        if all(v is not None for v in [safe, caution, unsafe]):
            if not (safe <= caution <= unsafe):
                raise ValueError("Thresholds must be in order: safe <= caution <= unsafe")
        return self


class FusionSettings(BaseModel):
    """
    Policy/Fusion configuration - determines how scores are aggregated.
    
    This is Level 1 (Default) controls - safe for all users.
    """
    verdict_strategy: VerdictStrategy = Field(
        default=VerdictStrategy.ANY_UNSAFE,
        description="Strategy for determining final verdict"
    )
    top_n_count: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of top scores to consider (for TOP_N strategy)"
    )
    criterion_overrides: Dict[str, CriterionOverride] = Field(
        default_factory=dict,
        description="Per-criterion weight and threshold overrides"
    )
    confidence_floor: float = Field(
        default=0.0,
        ge=0.0,
        le=0.5,
        description="Minimum confidence to include in scoring"
    )
    escalation_threshold: float = Field(
        default=0.9,
        ge=0.5,
        le=1.0,
        description="Score threshold for immediate escalation"
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return self.model_dump(mode='json', exclude_none=True)


# =============================================================================
# Stage Knobs (Level 2 Controls - Advanced)
# =============================================================================

class StageKnobs(BaseModel):
    """
    Safe, bounded parameters for a pipeline stage.
    
    This is Level 2 (Advanced) controls - curated subset of model parameters.
    """
    # === Common Settings ===
    sensitivity: SensitivityLevel = Field(
        default=SensitivityLevel.BALANCED,
        description="Detection sensitivity profile"
    )
    confidence_threshold: float = Field(
        default=0.5,
        ge=0.1,
        le=0.95,
        description="Minimum confidence for detections"
    )
    max_detections: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum detections per frame"
    )
    include_classes: Optional[List[str]] = Field(
        None,
        description="Only detect these classes (if supported)"
    )
    exclude_classes: Optional[List[str]] = Field(
        None,
        description="Exclude these classes from detection"
    )
    quality_mode: QualityMode = Field(
        default=QualityMode.BALANCED,
        description="Speed vs quality tradeoff"
    )
    
    # === Violence Detection Settings ===
    temporal_window: int = Field(
        default=16,
        ge=8,
        le=32,
        description="Number of frames for action recognition (X-CLIP, VideoMAE)"
    )
    
    # === Window Mining Settings ===
    motion_threshold: float = Field(
        default=0.3,
        ge=0.1,
        le=0.8,
        description="Motion level threshold for hotspot detection"
    )
    
    # === Pose Heuristics Settings ===
    interaction_distance: float = Field(
        default=0.3,
        ge=0.1,
        le=0.6,
        description="Max distance for person interaction detection"
    )
    
    # === NSFW Detection Settings ===
    nsfw_threshold: float = Field(
        default=0.6,
        ge=0.3,
        le=0.9,
        description="Threshold for adult content flagging"
    )
    
    # === Text Moderation Settings ===
    profanity_threshold: float = Field(
        default=0.5,
        ge=0.2,
        le=0.9,
        description="Threshold for profanity flagging"
    )
    
    @field_validator('include_classes', 'exclude_classes')
    @classmethod
    def validate_class_lists(cls, v):
        if v is not None:
            # Normalize to lowercase
            return [c.lower().strip() for c in v if c.strip()]
        return v
    
    def apply_sensitivity(self) -> Dict[str, Any]:
        """
        Convert sensitivity profile to concrete parameter values.
        
        This is the mapping layer between UI-friendly controls and model internals.
        """
        profiles = {
            SensitivityLevel.CONSERVATIVE: {
                "confidence_threshold": max(0.1, self.confidence_threshold - 0.15),
                "max_detections": min(200, int(self.max_detections * 1.5)),
            },
            SensitivityLevel.BALANCED: {
                "confidence_threshold": self.confidence_threshold,
                "max_detections": self.max_detections,
            },
            SensitivityLevel.AGGRESSIVE: {
                "confidence_threshold": min(0.95, self.confidence_threshold + 0.15),
                "max_detections": max(1, int(self.max_detections * 0.5)),
            },
        }
        return profiles.get(self.sensitivity, profiles[SensitivityLevel.BALANCED])


class StageOverrides(BaseModel):
    """Collection of per-stage knob overrides."""
    stages: Dict[str, StageKnobs] = Field(
        default_factory=dict,
        description="Per-stage configuration overrides"
    )
    
    def get_knobs(self, stage_type: str) -> Optional[StageKnobs]:
        """Get knobs for a specific stage, or None if not overridden."""
        return self.stages.get(stage_type)


# =============================================================================
# UI Schema Definition (for schema-driven rendering)
# =============================================================================

class KnobType(str, Enum):
    """Types of UI controls."""
    ENUM = "enum"
    NUMBER = "number"
    RANGE = "range"
    BOOLEAN = "boolean"
    STRING_LIST = "string_list"
    STRING = "string"


class KnobDefinition(BaseModel):
    """Definition of a single configurable knob for UI rendering."""
    id: str = Field(..., description="Unique knob identifier")
    label: str = Field(..., description="Human-readable label")
    description: str = Field(..., description="Help text for users")
    type: KnobType = Field(..., description="Control type")
    default: Any = Field(..., description="Default value")
    
    # Type-specific constraints
    min_value: Optional[float] = Field(None, description="Minimum value (for number/range)")
    max_value: Optional[float] = Field(None, description="Maximum value (for number/range)")
    step: Optional[float] = Field(None, description="Step increment (for range)")
    options: Optional[List[Dict[str, str]]] = Field(
        None, 
        description="Options for enum type [{value, label}]"
    )
    
    # Metadata
    category: str = Field(default="general", description="Grouping category")
    level: Literal["basic", "advanced"] = Field(default="basic", description="Complexity level")
    stage_types: Optional[List[str]] = Field(
        None,
        description="Which stage types support this knob (None = all)"
    )


class ConfigSchemaResponse(BaseModel):
    """Schema response for UI-driven rendering."""
    fusion_knobs: List[KnobDefinition] = Field(..., description="Policy/fusion settings knobs")
    stage_knobs: List[KnobDefinition] = Field(..., description="Per-stage settings knobs")
    supported_stages: List[str] = Field(..., description="Stage types that support knobs")


# =============================================================================
# Schema Factory - Defines all available knobs
# =============================================================================

def get_fusion_knobs() -> List[KnobDefinition]:
    """Define all fusion/policy knobs for UI rendering."""
    return [
        KnobDefinition(
            id="verdict_strategy",
            label="Verdict Strategy",
            description="How to determine the final verdict from multiple criteria scores",
            type=KnobType.ENUM,
            default=VerdictStrategy.ANY_UNSAFE.value,
            options=[
                {"value": "any_unsafe", "label": "Any Unsafe → UNSAFE (strictest)"},
                {"value": "majority_unsafe", "label": "Majority Unsafe → UNSAFE"},
                {"value": "weighted_average", "label": "Weighted Average Score"},
                {"value": "critical_only", "label": "Critical Criteria Only"},
                {"value": "top_n", "label": "Top N Scores"},
            ],
            category="verdict",
            level="basic",
        ),
        KnobDefinition(
            id="top_n_count",
            label="Top N Count",
            description="Number of highest scores to consider (for Top N strategy)",
            type=KnobType.NUMBER,
            default=3,
            min_value=1,
            max_value=10,
            step=1,
            category="verdict",
            level="advanced",
        ),
        KnobDefinition(
            id="confidence_floor",
            label="Confidence Floor",
            description="Minimum detection confidence to include in scoring",
            type=KnobType.RANGE,
            default=0.0,
            min_value=0.0,
            max_value=0.5,
            step=0.05,
            category="scoring",
            level="advanced",
        ),
        KnobDefinition(
            id="escalation_threshold",
            label="Escalation Threshold",
            description="Score above this triggers immediate escalation",
            type=KnobType.RANGE,
            default=0.9,
            min_value=0.5,
            max_value=1.0,
            step=0.05,
            category="scoring",
            level="advanced",
        ),
    ]


def get_stage_knobs() -> List[KnobDefinition]:
    """Define all stage knobs for UI rendering."""
    return [
        # === Detection Sensitivity ===
        KnobDefinition(
            id="sensitivity",
            label="Detection Sensitivity",
            description="How aggressively to detect potential issues",
            type=KnobType.ENUM,
            default=SensitivityLevel.BALANCED.value,
            options=[
                {"value": "conservative", "label": "Conservative (catch more, more false positives)"},
                {"value": "balanced", "label": "Balanced (default)"},
                {"value": "aggressive", "label": "Aggressive (fewer detections, higher confidence)"},
            ],
            category="detection",
            level="basic",
            stage_types=["yolo26", "yoloworld", "violence", "xclip", "videomae_violence", "nsfw_detection", "ocr"],
        ),
        
        # === Confidence Threshold ===
        KnobDefinition(
            id="confidence_threshold",
            label="Confidence Threshold",
            description="Minimum confidence score to include a detection",
            type=KnobType.RANGE,
            default=0.5,
            min_value=0.1,
            max_value=0.95,
            step=0.05,
            category="detection",
            level="advanced",
            stage_types=["yolo26", "yoloworld", "violence", "xclip", "videomae_violence", "pose_heuristics", "nsfw_detection", "ocr"],
        ),
        
        # === Max Detections ===
        KnobDefinition(
            id="max_detections",
            label="Max Detections",
            description="Maximum number of detections per frame",
            type=KnobType.NUMBER,
            default=50,
            min_value=1,
            max_value=200,
            step=10,
            category="detection",
            level="advanced",
            stage_types=["yolo26", "yoloworld"],
        ),
        
        # === Quality Mode ===
        KnobDefinition(
            id="quality_mode",
            label="Quality Mode",
            description="Trade off between speed and accuracy",
            type=KnobType.ENUM,
            default=QualityMode.BALANCED.value,
            options=[
                {"value": "fast", "label": "Fast (lower quality)"},
                {"value": "balanced", "label": "Balanced"},
                {"value": "accurate", "label": "Accurate (slower)"},
            ],
            category="performance",
            level="advanced",
            stage_types=["yolo26", "yoloworld", "whisper", "videomae_violence"],
        ),
        
        # === Violence-specific: Temporal Window ===
        KnobDefinition(
            id="temporal_window",
            label="Temporal Window (frames)",
            description="Number of frames to analyze together for action recognition",
            type=KnobType.NUMBER,
            default=16,
            min_value=8,
            max_value=32,
            step=4,
            category="detection",
            level="advanced",
            stage_types=["violence", "xclip", "videomae_violence"],
        ),
        
        # === Window Mining: Motion Threshold ===
        KnobDefinition(
            id="motion_threshold",
            label="Motion Threshold",
            description="Minimum motion level to flag a segment as a hotspot",
            type=KnobType.RANGE,
            default=0.3,
            min_value=0.1,
            max_value=0.8,
            step=0.05,
            category="detection",
            level="advanced",
            stage_types=["window_mining"],
        ),
        
        # === Pose Heuristics: Interaction Distance ===
        KnobDefinition(
            id="interaction_distance",
            label="Interaction Distance",
            description="Maximum distance between persons to consider as interaction",
            type=KnobType.RANGE,
            default=0.3,
            min_value=0.1,
            max_value=0.6,
            step=0.05,
            category="detection",
            level="advanced",
            stage_types=["pose_heuristics"],
        ),
        
        # === NSFW: Adult Content Threshold ===
        KnobDefinition(
            id="nsfw_threshold",
            label="NSFW Threshold",
            description="Minimum score to flag visual content as adult/NSFW",
            type=KnobType.RANGE,
            default=0.6,
            min_value=0.3,
            max_value=0.9,
            step=0.05,
            category="detection",
            level="basic",
            stage_types=["nsfw_detection"],
        ),
        
        # === Text Moderation: Profanity Threshold ===
        KnobDefinition(
            id="profanity_threshold",
            label="Profanity Threshold",
            description="Minimum score to flag text as containing profanity",
            type=KnobType.RANGE,
            default=0.5,
            min_value=0.2,
            max_value=0.9,
            step=0.05,
            category="detection",
            level="basic",
            stage_types=["text_moderation"],
        ),
    ]


# All stages that support configuration knobs
SUPPORTED_STAGES = [
    # Object Detection
    "yolo26", 
    "yoloworld",
    # Violence Detection Stack
    "window_mining",
    "violence",
    "xclip",
    "videomae_violence",
    "pose_heuristics",
    # Content Moderation
    "nsfw_detection",
    "whisper",
    "ocr",
    "text_moderation",
]


def get_config_schema() -> ConfigSchemaResponse:
    """Get full configuration schema for UI rendering."""
    return ConfigSchemaResponse(
        fusion_knobs=get_fusion_knobs(),
        stage_knobs=get_stage_knobs(),
        supported_stages=SUPPORTED_STAGES,
    )


# =============================================================================
# Validation Helpers
# =============================================================================

class ConfigValidationError(BaseModel):
    """Structured validation error."""
    field: str
    message: str
    value: Any = None


class ConfigValidationResult(BaseModel):
    """Result of config validation."""
    valid: bool
    errors: List[ConfigValidationError] = Field(default_factory=list)
    warnings: List[ConfigValidationError] = Field(default_factory=list)


def validate_fusion_settings(settings: FusionSettings) -> ConfigValidationResult:
    """Validate fusion settings with user-friendly messages."""
    errors = []
    warnings = []
    
    # Validate TOP_N strategy has reasonable count
    if settings.verdict_strategy == VerdictStrategy.TOP_N:
        if settings.top_n_count < 2:
            warnings.append(ConfigValidationError(
                field="top_n_count",
                message="Top N count of 1 is equivalent to using max score",
                value=settings.top_n_count
            ))
    
    # Validate criterion overrides
    for criterion_id, override in settings.criterion_overrides.items():
        if override.weight is not None and override.weight > 3.0:
            warnings.append(ConfigValidationError(
                field=f"criterion_overrides.{criterion_id}.weight",
                message=f"Weight of {override.weight} is very high and may dominate scoring",
                value=override.weight
            ))
    
    return ConfigValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


def validate_stage_knobs(knobs: StageKnobs, stage_type: str) -> ConfigValidationResult:
    """Validate stage knobs with user-friendly messages."""
    errors = []
    warnings = []
    
    # Validate confidence threshold
    if knobs.confidence_threshold < 0.2:
        warnings.append(ConfigValidationError(
            field="confidence_threshold",
            message="Very low confidence threshold may produce many false positives",
            value=knobs.confidence_threshold
        ))
    
    if knobs.confidence_threshold > 0.9:
        warnings.append(ConfigValidationError(
            field="confidence_threshold",
            message="Very high confidence threshold may miss valid detections",
            value=knobs.confidence_threshold
        ))
    
    # Validate class lists don't conflict
    if knobs.include_classes and knobs.exclude_classes:
        overlap = set(knobs.include_classes) & set(knobs.exclude_classes)
        if overlap:
            errors.append(ConfigValidationError(
                field="include_classes/exclude_classes",
                message=f"Classes appear in both include and exclude lists: {overlap}",
                value=list(overlap)
            ))
    
    return ConfigValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )
