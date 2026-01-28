"""
Evaluation specification models.

Defines the schema for user-provided evaluation configurations that control:
- Criteria definitions (what to evaluate)
- Detector configurations (how to detect)
- Routing (which detectors feed which criteria)
- Fusion strategies (how to combine evidence into scores)
- Output specifications (what to include in results)
"""
from typing import Dict, List, Any, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum


# Schema version for compatibility checking
SCHEMA_VERSION = "1.0"


class VerdictLevel(str, Enum):
    """Standard verdict levels."""
    SAFE = "SAFE"
    CAUTION = "CAUTION"
    UNSAFE = "UNSAFE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class SeverityLevel(str, Enum):
    """Severity levels for violations."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ===== CRITERION SPEC =====

class VerdictThresholds(BaseModel):
    """Thresholds for determining verdict per criterion."""
    safe_below: float = Field(default=0.3, ge=0.0, le=1.0, description="Score below this is SAFE")
    caution_below: float = Field(default=0.6, ge=0.0, le=1.0, description="Score below this is CAUTION")
    unsafe_above: float = Field(default=0.6, ge=0.0, le=1.0, description="Score at or above this is UNSAFE")
    
    @model_validator(mode='after')
    def validate_thresholds(self):
        if self.safe_below > self.caution_below:
            raise ValueError("safe_below must be <= caution_below")
        if self.caution_below > self.unsafe_above:
            raise ValueError("caution_below must be <= unsafe_above")
        return self


class EvidenceRequirement(BaseModel):
    """Requirements for evidence to trigger a violation."""
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    min_occurrences: int = Field(default=1, ge=1)
    require_multi_signal: bool = Field(default=False, description="Require multiple detector sources")


class CriterionSpec(BaseModel):
    """
    Specification for a single evaluation criterion.
    
    A criterion represents something to evaluate (e.g., "violence", "profanity", "brand_safety").
    """
    id: str = Field(..., min_length=1, max_length=50, pattern=r'^[a-z][a-z0-9_]*$')
    label: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    enabled: bool = Field(default=True)
    
    # Severity configuration
    severity_weight: float = Field(default=1.0, ge=0.0, le=10.0, description="Weight for final score aggregation")
    severity_level: SeverityLevel = Field(default=SeverityLevel.MEDIUM)
    
    # Verdict thresholds
    thresholds: VerdictThresholds = Field(default_factory=VerdictThresholds)
    
    # Evidence requirements
    evidence_requirements: EvidenceRequirement = Field(default_factory=EvidenceRequirement)
    
    # Custom keywords/patterns for text-based detection (optional enhancement)
    custom_keywords: List[str] = Field(default_factory=list, max_length=100)
    
    @field_validator('id')
    @classmethod
    def validate_id(cls, v: str) -> str:
        reserved = ['id', 'type', 'score', 'verdict', 'evidence']
        if v in reserved:
            raise ValueError(f"'{v}' is a reserved identifier")
        return v


# ===== DETECTOR SPEC =====

class DetectorType(str, Enum):
    """Available detector types."""
    # Vision detectors
    YOLO26 = "yolo26"
    YOLOWORLD = "yoloworld"
    XCLIP_VIOLENCE = "xclip_violence"
    
    # Audio detectors
    WHISPER_ASR = "whisper_asr"
    
    # Text detectors
    OCR = "ocr"
    TEXT_MODERATION = "text_moderation"
    
    # Custom (for future extensibility)
    CUSTOM = "custom"


class DetectorSpec(BaseModel):
    """
    Specification for a detector to run.
    
    Detectors analyze video/audio/text and produce evidence items.
    """
    id: str = Field(..., min_length=1, max_length=50, pattern=r'^[a-z][a-z0-9_]*$')
    type: DetectorType
    enabled: bool = Field(default=True)
    
    # Model configuration (optional overrides)
    model_id: Optional[str] = Field(default=None, description="Specific model version to use")
    
    # Detector-specific parameters
    params: Dict[str, Any] = Field(default_factory=dict)
    
    # Output configuration
    outputs: List[str] = Field(
        default_factory=list,
        description="List of output fields this detector produces"
    )
    
    # Priority for execution ordering (lower = earlier)
    priority: int = Field(default=100, ge=0, le=1000)
    
    # Dependencies on other detectors
    depends_on: List[str] = Field(
        default_factory=list,
        description="Detector IDs that must run before this one"
    )

    @field_validator('params')
    @classmethod
    def validate_params(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        # Limit param depth and size
        import json
        try:
            serialized = json.dumps(v)
            if len(serialized) > 10000:
                raise ValueError("params too large (max 10KB)")
        except TypeError:
            raise ValueError("params must be JSON-serializable")
        return v


# ===== ROUTING SPEC =====

class RoutingRule(BaseModel):
    """Maps a detector output to a criterion."""
    detector_id: str
    output_field: str = Field(default="*", description="Specific output field or '*' for all")
    weight: float = Field(default=1.0, ge=0.0, le=10.0)
    transform: Optional[str] = Field(
        default=None,
        description="Optional transform: 'max', 'avg', 'sum', 'count'"
    )


class RoutingSpec(BaseModel):
    """
    Defines how detector outputs map to criteria.
    
    Each criterion can receive input from multiple detectors.
    """
    criterion_id: str
    sources: List[RoutingRule] = Field(default_factory=list)


# ===== FUSION SPEC =====

class FusionStrategy(str, Enum):
    """Strategies for combining detector outputs into criterion scores."""
    WEIGHTED_SUM = "weighted_sum"
    MAX = "max"
    AVERAGE = "average"
    RULE_BASED = "rule_based"
    CUSTOM = "custom"


class AggregationRule(str, Enum):
    """Rules for aggregating criterion verdicts into final verdict."""
    ANY_UNSAFE = "any_unsafe"  # Any UNSAFE criterion -> UNSAFE
    MAJORITY = "majority"  # Majority vote
    WEIGHTED = "weighted"  # Weighted by severity
    THRESHOLD = "threshold"  # Based on aggregated score threshold


class FusionSpec(BaseModel):
    """
    Specification for how to fuse evidence into scores and verdicts.
    """
    # Per-criterion fusion strategy
    criterion_strategy: FusionStrategy = Field(default=FusionStrategy.WEIGHTED_SUM)
    
    # Final verdict aggregation rule
    verdict_aggregation: AggregationRule = Field(default=AggregationRule.ANY_UNSAFE)
    
    # For rule-based fusion
    rules: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Custom rules for rule_based strategy"
    )
    
    # For weighted aggregation
    criterion_weights: Dict[str, float] = Field(
        default_factory=dict,
        description="Override weights for criteria in final aggregation"
    )
    
    # Multi-signal confirmation
    require_confirmation: bool = Field(
        default=True,
        description="Require multiple signals before marking UNSAFE"
    )
    confirmation_threshold: int = Field(
        default=2,
        ge=1,
        description="Number of confirming signals required"
    )


# ===== OUTPUT SPEC =====

class RedactionConfig(BaseModel):
    """Configuration for redacting sensitive content."""
    redact_faces: bool = Field(default=False)
    redact_text: bool = Field(default=False)
    redact_audio: bool = Field(default=False)
    blur_strength: float = Field(default=20.0, ge=1.0, le=100.0)


class OutputSpec(BaseModel):
    """
    Specification for what to include in the evaluation response.
    """
    include_labeled_video: bool = Field(default=True)
    include_raw_evidence: bool = Field(default=True)
    include_report: bool = Field(default=True)
    include_timestamps: bool = Field(default=True)
    include_confidence_scores: bool = Field(default=True)
    include_model_versions: bool = Field(default=True)
    include_timing: bool = Field(default=True)
    
    # Explanation/audit trail
    include_explain: bool = Field(
        default=True,
        description="Include explanation of how verdict was determined"
    )
    
    # Limits
    max_evidence_items: int = Field(default=100, ge=1, le=1000)
    max_violations: int = Field(default=50, ge=1, le=500)
    
    # Redaction
    redactions: RedactionConfig = Field(default_factory=RedactionConfig)
    
    # Report configuration
    report_format: Literal["text", "markdown", "json"] = Field(default="text")
    report_max_length: int = Field(default=2000, ge=100, le=10000)


# ===== MAIN EVALUATION SPEC =====

class EvaluationSpec(BaseModel):
    """
    Complete evaluation specification.
    
    This is the main schema that users provide to define custom evaluations.
    """
    # Schema metadata
    schema_version: str = Field(default=SCHEMA_VERSION)
    spec_id: Optional[str] = Field(default=None, max_length=100, description="User-provided spec identifier")
    spec_name: Optional[str] = Field(default=None, max_length=200)
    
    # Core definitions
    criteria: List[CriterionSpec] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Criteria to evaluate"
    )
    
    detectors: List[DetectorSpec] = Field(
        ...,
        min_length=1,
        max_length=15,
        description="Detectors to run"
    )
    
    # Routing: which detectors feed which criteria
    routing: List[RoutingSpec] = Field(
        default_factory=list,
        description="Explicit routing rules (auto-generated if empty)"
    )
    
    # Fusion configuration
    fusion: FusionSpec = Field(default_factory=FusionSpec)
    
    # Output configuration
    outputs: OutputSpec = Field(default_factory=OutputSpec)
    
    # Custom verdict levels (optional override of defaults)
    verdict_levels: List[str] = Field(
        default_factory=lambda: [v.value for v in VerdictLevel],
        description="Custom verdict levels (ordered from safest to most unsafe)"
    )
    
    @model_validator(mode='after')
    def validate_spec(self):
        """Validate cross-field constraints."""
        # Collect IDs
        criterion_ids = {c.id for c in self.criteria}
        detector_ids = {d.id for d in self.detectors}
        
        # Validate routing references
        for route in self.routing:
            if route.criterion_id not in criterion_ids:
                raise ValueError(f"Routing references unknown criterion: {route.criterion_id}")
            for source in route.sources:
                if source.detector_id not in detector_ids:
                    raise ValueError(f"Routing references unknown detector: {source.detector_id}")
        
        # Validate detector dependencies
        for detector in self.detectors:
            for dep in detector.depends_on:
                if dep not in detector_ids:
                    raise ValueError(f"Detector '{detector.id}' depends on unknown detector: {dep}")
                if dep == detector.id:
                    raise ValueError(f"Detector '{detector.id}' cannot depend on itself")
        
        # Validate fusion weights reference valid criteria
        for crit_id in self.fusion.criterion_weights:
            if crit_id not in criterion_ids:
                raise ValueError(f"Fusion weights reference unknown criterion: {crit_id}")
        
        return self
    
    @field_validator('schema_version')
    @classmethod
    def validate_schema_version(cls, v: str) -> str:
        if v != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema version: {v}. "
                f"Expected: {SCHEMA_VERSION}"
            )
        return v
    
    def get_enabled_criteria(self) -> List[CriterionSpec]:
        """Get list of enabled criteria."""
        return [c for c in self.criteria if c.enabled]
    
    def get_enabled_detectors(self) -> List[DetectorSpec]:
        """Get list of enabled detectors, sorted by priority."""
        enabled = [d for d in self.detectors if d.enabled]
        return sorted(enabled, key=lambda d: d.priority)
    
    def get_routing_for_criterion(self, criterion_id: str) -> List[RoutingRule]:
        """Get routing rules for a specific criterion."""
        for route in self.routing:
            if route.criterion_id == criterion_id:
                return route.sources
        return []
    
    def auto_generate_routing(self) -> 'EvaluationSpec':
        """
        Auto-generate routing rules based on detector types and criterion IDs.
        
        This provides sensible defaults when explicit routing is not provided.
        """
        if self.routing:
            return self  # Already has routing
        
        # Default mappings based on detector type -> criterion
        default_mappings = {
            DetectorType.XCLIP_VIOLENCE: ["violence"],
            DetectorType.YOLO26: ["violence", "drugs", "weapons"],
            DetectorType.YOLOWORLD: ["violence", "drugs", "weapons", "objects"],
            DetectorType.WHISPER_ASR: ["profanity", "hate", "sexual", "drugs"],
            DetectorType.OCR: ["profanity", "hate", "sexual", "drugs"],
            DetectorType.TEXT_MODERATION: ["profanity", "hate", "sexual", "drugs", "violence"],
        }
        
        criterion_ids = {c.id for c in self.criteria}
        generated_routing = {}
        
        for detector in self.detectors:
            if not detector.enabled:
                continue
                
            target_criteria = default_mappings.get(detector.type, [])
            
            for crit_id in target_criteria:
                if crit_id in criterion_ids:
                    if crit_id not in generated_routing:
                        generated_routing[crit_id] = []
                    generated_routing[crit_id].append(
                        RoutingRule(detector_id=detector.id, weight=1.0)
                    )
        
        self.routing = [
            RoutingSpec(criterion_id=crit_id, sources=sources)
            for crit_id, sources in generated_routing.items()
        ]
        
        return self


def validate_evaluation_spec(spec_dict: Dict[str, Any]) -> EvaluationSpec:
    """
    Validate and parse an evaluation spec dictionary.
    
    Raises ValidationError with detailed messages on failure.
    """
    return EvaluationSpec.model_validate(spec_dict)
