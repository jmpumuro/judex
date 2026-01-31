"""
Base interface for pipeline stage plugins.

StagePlugin provides a standard interface that all pipeline stages must implement.
This allows both builtin stages (wrapping existing nodes) and future external
stages to be executed uniformly by the PipelineRunner.

Supports both VIDEO and IMAGE media types with per-stage compatibility.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum


class MediaType(str, Enum):
    """Supported media types for pipeline processing."""
    VIDEO = "video"
    IMAGE = "image"


# Default: All stages support both media types unless overridden
ALL_MEDIA_TYPES = {MediaType.VIDEO, MediaType.IMAGE}
VIDEO_ONLY = {MediaType.VIDEO}


class StageStatus(str, Enum):
    """Status of a stage execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StageImpact(str, Enum):
    """
    Impact level of a stage on the final verdict.
    
    - CRITICAL: Cannot be disabled; pipeline fails if stage fails
    - SUPPORTING: Contributes significantly; warning if skipped
    - ADVISORY: Optional enhancement; safe to skip
    """
    CRITICAL = "critical"
    SUPPORTING = "supporting"
    ADVISORY = "advisory"


# Default impact levels for builtin stages
STAGE_IMPACT_DEFAULTS: Dict[str, StageImpact] = {
    # Core stages
    "yolo26": StageImpact.SUPPORTING,
    "yoloworld": StageImpact.ADVISORY,
    "xclip": StageImpact.SUPPORTING,  # violence/xclip
    "violence": StageImpact.SUPPORTING,  # alias for xclip
    "whisper": StageImpact.SUPPORTING,
    "ocr": StageImpact.ADVISORY,
    "text_moderation": StageImpact.SUPPORTING,
    # Enhanced violence detection stack
    "window_mining": StageImpact.ADVISORY,  # Preprocessing
    "pose_heuristics": StageImpact.SUPPORTING,
    "videomae_violence": StageImpact.SUPPORTING,
    # NSFW visual detection (sexual content confirmation)
    "nsfw_detection": StageImpact.SUPPORTING,
}


@dataclass
class StageSpec:
    """
    Specification for a stage to be executed.
    
    This is the configuration passed to a stage, typically derived from
    the evaluation criteria or an explicit pipeline definition.
    
    Attributes:
        type: Stage type (registry key)
        id: Unique ID for this stage instance
        enabled: Whether the stage should run
        impact: Impact level on final verdict (critical/supporting/advisory)
        required: If True, cannot be disabled via UI
        config: Stage-specific configuration
        skip_reason: If skipped, explains why
    """
    type: str  # Stage type (registry key)
    id: str = ""  # Unique ID for this stage instance (auto-generated if empty)
    enabled: bool = True
    impact: StageImpact = StageImpact.SUPPORTING
    required: bool = False  # If True, cannot be disabled
    config: Dict[str, Any] = field(default_factory=dict)  # Stage-specific config
    skip_reason: Optional[str] = None  # Populated if skipped
    
    def __post_init__(self):
        if not self.id:
            self.id = self.type
        # Apply default impact if not set
        if self.type in STAGE_IMPACT_DEFAULTS:
            self.impact = STAGE_IMPACT_DEFAULTS[self.type]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API/persistence."""
        return {
            "type": self.type,
            "id": self.id,
            "enabled": self.enabled,
            "impact": self.impact.value,
            "required": self.required,
            "skip_reason": self.skip_reason,
        }


class StagePlugin(ABC):
    """
    Base interface for all pipeline stage plugins.
    
    Stage plugins wrap detector/analysis logic and provide a uniform interface
    for the PipelineRunner. Builtin stages reuse existing node implementations.
    
    Subclasses must implement:
    - stage_type: The registry key for this stage
    - run(): Execute the stage logic
    
    Optional overrides:
    - input_keys: State keys this stage reads from
    - output_keys: State keys this stage writes to
    - validate_state(): Pre-execution validation
    """
    
    @property
    @abstractmethod
    def stage_type(self) -> str:
        """
        Unique identifier for this stage type.
        
        This is the key used in the registry and in pipeline definitions.
        Example: "yolo26", "whisper", "ocr"
        """
        pass
    
    @property
    def display_name(self) -> str:
        """Human-readable name for UI/logging."""
        return self.stage_type.replace("_", " ").title()
    
    @property
    def is_external(self) -> bool:
        """
        Whether this is an external stage (calls external HTTP endpoint).
        
        External stages need special handling for output persistence since
        they don't use the builtin save_stage_output in their node code.
        
        Default is False for builtin stages. External plugins override to True.
        """
        return False
    
    @property
    def supported_media_types(self) -> Set[MediaType]:
        """
        Media types this stage supports (video, image, or both).
        
        Stages that require temporal context (multiple frames) should return VIDEO_ONLY.
        Default is ALL_MEDIA_TYPES (both video and image).
        
        Override in subclasses for video-only stages like violence detection.
        """
        return ALL_MEDIA_TYPES
    
    def supports_media_type(self, media_type: str) -> bool:
        """Check if this stage supports a given media type."""
        try:
            mt = MediaType(media_type)
            return mt in self.supported_media_types
        except ValueError:
            return False
    
    @property
    def input_keys(self) -> Set[str]:
        """
        State keys this stage requires as input.
        
        Used for validation and dependency tracking.
        """
        return set()
    
    @property
    def output_keys(self) -> Set[str]:
        """
        State keys this stage produces as output.
        
        Used for validation and UI display.
        """
        return set()
    
    def validate_state(self, state: Dict[str, Any], spec: StageSpec) -> Optional[str]:
        """
        Validate state before execution.
        
        Args:
            state: Current pipeline state
            spec: Stage specification
            
        Returns:
            Error message if validation fails, None otherwise
        """
        # Check required input keys
        missing = self.input_keys - set(state.keys())
        if missing:
            return f"Missing required state keys: {missing}"
        return None
    
    @abstractmethod
    async def run(
        self, 
        state: Dict[str, Any], 
        spec: StageSpec
    ) -> Dict[str, Any]:
        """
        Execute the stage logic.
        
        Args:
            state: Current pipeline state (PipelineState dict)
            spec: Stage specification with config
            
        Returns:
            Updated state dict (or just the changed keys to merge)
        """
        pass
    
    def get_stage_output(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract stage-specific output for persistence/display.
        
        Override this to customize what gets saved as stage output.
        Default returns values for output_keys.
        """
        return {key: state.get(key) for key in self.output_keys if key in state}


class ExternalStagePlugin(StagePlugin):
    """
    Base class for external/callback stages (future extension).
    
    External stages call out to customer-provided endpoints.
    This is a placeholder interface - full implementation would require:
    - Authentication/authorization
    - Request signing
    - Timeout handling
    - Response validation
    """
    
    @property
    def stage_type(self) -> str:
        return "external"
    
    @property
    def callback_url(self) -> str:
        """URL to call for this stage."""
        raise NotImplementedError("External stages require callback_url")
    
    async def run(
        self, 
        state: Dict[str, Any], 
        spec: StageSpec
    ) -> Dict[str, Any]:
        """
        Execute by calling external endpoint.
        
        This is a stub - real implementation would:
        1. Build request payload from state
        2. Sign request
        3. Call endpoint with timeout
        4. Validate response
        5. Merge response into state
        """
        # Placeholder - external stages not yet implemented
        raise NotImplementedError(
            "External stage execution not yet implemented. "
            "This is a placeholder for future customer-pluggable stages."
        )
