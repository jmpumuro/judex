"""
Evaluation presets - pre-configured EvaluationSpecs for common use cases.

The child_safety preset provides backward compatibility with the original SafeVid API.
"""
from typing import Dict, Optional
from app.evaluation.spec import (
    EvaluationSpec,
    CriterionSpec,
    DetectorSpec,
    DetectorType,
    FusionSpec,
    FusionStrategy,
    AggregationRule,
    OutputSpec,
    RoutingSpec,
    RoutingRule,
    VerdictThresholds,
    EvidenceRequirement,
    SeverityLevel
)


class PresetNotFoundError(Exception):
    """Raised when a preset is not found."""
    pass


# ===== CHILD SAFETY PRESET =====
# This provides backward compatibility with the original SafeVid API

CHILD_SAFETY_CRITERIA = [
    CriterionSpec(
        id="violence",
        label="Violence",
        description="Physical violence, weapons, blood, fighting, assault",
        severity_weight=1.5,
        severity_level=SeverityLevel.HIGH,
        thresholds=VerdictThresholds(
            safe_below=0.40,
            caution_below=0.75,
            unsafe_above=0.75
        ),
        evidence_requirements=EvidenceRequirement(
            min_confidence=0.5,
            min_occurrences=1,
            require_multi_signal=True  # Require confirmation for UNSAFE
        ),
        custom_keywords=["assault", "attack", "fight", "hit", "punch", "stab", "shoot", "kill"]
    ),
    CriterionSpec(
        id="profanity",
        label="Profanity",
        description="Explicit language, curse words, vulgar content",
        severity_weight=0.8,
        severity_level=SeverityLevel.MEDIUM,
        thresholds=VerdictThresholds(
            safe_below=0.40,
            caution_below=0.60,
            unsafe_above=0.75
        ),
        evidence_requirements=EvidenceRequirement(
            min_confidence=0.4,
            min_occurrences=1,
            require_multi_signal=False
        )
    ),
    CriterionSpec(
        id="sexual",
        label="Sexual Content",
        description="Explicit sexual content, nudity, adult themes",
        severity_weight=1.2,
        severity_level=SeverityLevel.HIGH,
        thresholds=VerdictThresholds(
            safe_below=0.30,
            caution_below=0.60,
            unsafe_above=0.60
        ),
        evidence_requirements=EvidenceRequirement(
            min_confidence=0.5,
            min_occurrences=1,
            require_multi_signal=True
        )
    ),
    CriterionSpec(
        id="drugs",
        label="Drugs/Substances",
        description="Drug use, drug paraphernalia, substance abuse",
        severity_weight=1.0,
        severity_level=SeverityLevel.HIGH,
        thresholds=VerdictThresholds(
            safe_below=0.40,
            caution_below=0.70,
            unsafe_above=0.70
        ),
        evidence_requirements=EvidenceRequirement(
            min_confidence=0.5,
            min_occurrences=1,
            require_multi_signal=False
        )
    ),
    CriterionSpec(
        id="hate",
        label="Hate Speech",
        description="Hate speech, discrimination, harassment, slurs",
        severity_weight=1.3,
        severity_level=SeverityLevel.HIGH,
        thresholds=VerdictThresholds(
            safe_below=0.30,
            caution_below=0.60,
            unsafe_above=0.60
        ),
        evidence_requirements=EvidenceRequirement(
            min_confidence=0.4,
            min_occurrences=1,
            require_multi_signal=True
        )
    )
]

CHILD_SAFETY_DETECTORS = [
    DetectorSpec(
        id="yolo26_vision",
        type=DetectorType.YOLO26,
        enabled=True,
        priority=10,
        params={
            "confidence_threshold": 0.5,
            "safety_categories": ["weapon", "substance", "dangerous"]
        },
        outputs=["detections", "safety_signals"]
    ),
    DetectorSpec(
        id="yoloworld_vision",
        type=DetectorType.YOLOWORLD,
        enabled=True,
        priority=15,
        depends_on=["yolo26_vision"],
        params={
            "confidence_threshold": 0.3,
            "prompts": ["weapon", "knife", "gun", "blood", "drugs", "alcohol"]
        },
        outputs=["detections", "prompt_matches"]
    ),
    DetectorSpec(
        id="xclip_violence",
        type=DetectorType.XCLIP_VIOLENCE,
        enabled=True,
        priority=20,
        params={
            "segment_duration": 4.0,
            "violence_threshold": 0.4
        },
        outputs=["violence_segments", "violence_scores"]
    ),
    DetectorSpec(
        id="whisper_asr",
        type=DetectorType.WHISPER_ASR,
        enabled=True,
        priority=30,
        params={
            "model_size": "small"
        },
        outputs=["transcript", "chunks"]
    ),
    DetectorSpec(
        id="ocr",
        type=DetectorType.OCR,
        enabled=True,
        priority=40,
        depends_on=["yolo26_vision"],  # Uses sampled frames
        params={
            "sample_interval": 1.0
        },
        outputs=["ocr_results", "text_detections"]
    ),
    DetectorSpec(
        id="text_moderation",
        type=DetectorType.TEXT_MODERATION,
        enabled=True,
        priority=50,
        depends_on=["whisper_asr", "ocr"],
        params={
            "categories": ["profanity", "sexual", "drugs", "hate", "violence"]
        },
        outputs=["transcript_moderation", "ocr_moderation"]
    )
]

CHILD_SAFETY_ROUTING = [
    RoutingSpec(
        criterion_id="violence",
        sources=[
            RoutingRule(detector_id="xclip_violence", output_field="violence_scores", weight=0.6),
            RoutingRule(detector_id="yolo26_vision", output_field="safety_signals", weight=0.3),
            RoutingRule(detector_id="text_moderation", output_field="transcript_moderation", weight=0.1)
        ]
    ),
    RoutingSpec(
        criterion_id="profanity",
        sources=[
            RoutingRule(detector_id="text_moderation", output_field="transcript_moderation", weight=0.7),
            RoutingRule(detector_id="text_moderation", output_field="ocr_moderation", weight=0.3)
        ]
    ),
    RoutingSpec(
        criterion_id="sexual",
        sources=[
            RoutingRule(detector_id="text_moderation", output_field="transcript_moderation", weight=0.7),
            RoutingRule(detector_id="text_moderation", output_field="ocr_moderation", weight=0.2),
            RoutingRule(detector_id="yolo26_vision", output_field="safety_signals", weight=0.1)
        ]
    ),
    RoutingSpec(
        criterion_id="drugs",
        sources=[
            RoutingRule(detector_id="yolo26_vision", output_field="safety_signals", weight=0.4),
            RoutingRule(detector_id="text_moderation", output_field="transcript_moderation", weight=0.5),
            RoutingRule(detector_id="text_moderation", output_field="ocr_moderation", weight=0.1)
        ]
    ),
    RoutingSpec(
        criterion_id="hate",
        sources=[
            RoutingRule(detector_id="text_moderation", output_field="transcript_moderation", weight=0.7),
            RoutingRule(detector_id="text_moderation", output_field="ocr_moderation", weight=0.3)
        ]
    )
]

CHILD_SAFETY_FUSION = FusionSpec(
    criterion_strategy=FusionStrategy.WEIGHTED_SUM,
    verdict_aggregation=AggregationRule.ANY_UNSAFE,
    require_confirmation=True,
    confirmation_threshold=2,
    criterion_weights={
        "violence": 1.5,
        "profanity": 0.8,
        "sexual": 1.2,
        "drugs": 1.0,
        "hate": 1.3
    }
)

CHILD_SAFETY_OUTPUTS = OutputSpec(
    include_labeled_video=True,
    include_raw_evidence=True,
    include_report=True,
    include_timestamps=True,
    include_confidence_scores=True,
    include_model_versions=True,
    include_timing=True,
    include_explain=True,
    max_evidence_items=100,
    max_violations=50,
    report_format="text"
)

CHILD_SAFETY_PRESET = EvaluationSpec(
    spec_id="child_safety",
    spec_name="Child Safety Evaluation",
    criteria=CHILD_SAFETY_CRITERIA,
    detectors=CHILD_SAFETY_DETECTORS,
    routing=CHILD_SAFETY_ROUTING,
    fusion=CHILD_SAFETY_FUSION,
    outputs=CHILD_SAFETY_OUTPUTS
)

# Default preset is child safety (backward compatibility)
DEFAULT_PRESET = CHILD_SAFETY_PRESET


# ===== BRAND SAFETY PRESET =====
# Example of another preset for different use case

BRAND_SAFETY_CRITERIA = [
    CriterionSpec(
        id="violence",
        label="Violence",
        description="Any violent content",
        severity_weight=1.5,
        thresholds=VerdictThresholds(safe_below=0.3, caution_below=0.5, unsafe_above=0.5)
    ),
    CriterionSpec(
        id="adult",
        label="Adult Content",
        description="Sexual or mature content",
        severity_weight=2.0,
        thresholds=VerdictThresholds(safe_below=0.2, caution_below=0.4, unsafe_above=0.4)
    ),
    CriterionSpec(
        id="controversial",
        label="Controversial",
        description="Politically sensitive or controversial topics",
        severity_weight=1.0,
        thresholds=VerdictThresholds(safe_below=0.4, caution_below=0.6, unsafe_above=0.7)
    ),
    CriterionSpec(
        id="competitor_mention",
        label="Competitor Mentions",
        description="References to competitor brands",
        severity_weight=0.5,
        thresholds=VerdictThresholds(safe_below=0.5, caution_below=0.7, unsafe_above=0.8),
        custom_keywords=[]  # Would be populated per-client
    )
]

BRAND_SAFETY_PRESET = EvaluationSpec(
    spec_id="brand_safety",
    spec_name="Brand Safety Evaluation",
    criteria=BRAND_SAFETY_CRITERIA,
    detectors=[
        DetectorSpec(id="yolo26_vision", type=DetectorType.YOLO26, enabled=True, priority=10),
        DetectorSpec(id="xclip_violence", type=DetectorType.XCLIP_VIOLENCE, enabled=True, priority=20),
        DetectorSpec(id="whisper_asr", type=DetectorType.WHISPER_ASR, enabled=True, priority=30),
        DetectorSpec(id="ocr", type=DetectorType.OCR, enabled=True, priority=40),
        DetectorSpec(id="text_moderation", type=DetectorType.TEXT_MODERATION, enabled=True, priority=50)
    ],
    routing=[],  # Auto-generate
    fusion=FusionSpec(
        criterion_strategy=FusionStrategy.MAX,
        verdict_aggregation=AggregationRule.ANY_UNSAFE,
        require_confirmation=False  # Stricter for brand safety
    ),
    outputs=OutputSpec(
        include_labeled_video=False,  # Usually not needed for brand safety
        include_raw_evidence=True,
        include_report=True
    )
).auto_generate_routing()


# ===== PRESET REGISTRY =====

_PRESETS: Dict[str, EvaluationSpec] = {
    "child_safety": CHILD_SAFETY_PRESET,
    "brand_safety": BRAND_SAFETY_PRESET,
    "default": DEFAULT_PRESET
}


def get_preset(preset_id: str) -> EvaluationSpec:
    """
    Get a preset by ID.
    
    Args:
        preset_id: Preset identifier (e.g., "child_safety", "brand_safety")
        
    Returns:
        EvaluationSpec for the preset
        
    Raises:
        PresetNotFoundError: If preset doesn't exist
    """
    if preset_id not in _PRESETS:
        available = list(_PRESETS.keys())
        raise PresetNotFoundError(
            f"Preset '{preset_id}' not found. Available: {available}"
        )
    return _PRESETS[preset_id]


def list_presets() -> Dict[str, str]:
    """
    List available presets.
    
    Returns:
        Dict mapping preset_id -> spec_name
    """
    return {
        preset_id: spec.spec_name or preset_id
        for preset_id, spec in _PRESETS.items()
    }


def register_preset(preset_id: str, spec: EvaluationSpec) -> None:
    """
    Register a custom preset.
    
    Args:
        preset_id: Unique identifier for the preset
        spec: EvaluationSpec to register
    """
    if preset_id in _PRESETS:
        raise ValueError(f"Preset '{preset_id}' already exists")
    _PRESETS[preset_id] = spec


def get_or_create_spec(
    evaluation_spec: Optional[Dict] = None,
    preset_id: Optional[str] = None
) -> EvaluationSpec:
    """
    Get or create an EvaluationSpec from either a spec dict or preset ID.
    
    Args:
        evaluation_spec: User-provided spec dictionary
        preset_id: ID of preset to use (ignored if evaluation_spec provided)
        
    Returns:
        EvaluationSpec instance
        
    If neither is provided, returns the default preset.
    """
    if evaluation_spec:
        from app.evaluation.spec import validate_evaluation_spec
        spec = validate_evaluation_spec(evaluation_spec)
        # Auto-generate routing if not provided
        if not spec.routing:
            spec = spec.auto_generate_routing()
        return spec
    
    if preset_id:
        return get_preset(preset_id)
    
    return DEFAULT_PRESET
