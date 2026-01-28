"""
Base interface for pipeline stage plugins.

StagePlugin provides a standard interface that all pipeline stages must implement.
This allows both builtin stages (wrapping existing nodes) and future external
stages to be executed uniformly by the PipelineRunner.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum


class StageStatus(str, Enum):
    """Status of a stage execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageSpec:
    """
    Specification for a stage to be executed.
    
    This is the configuration passed to a stage, typically derived from
    the evaluation criteria or an explicit pipeline definition.
    """
    type: str  # Stage type (registry key)
    id: str = ""  # Unique ID for this stage instance (auto-generated if empty)
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)  # Stage-specific config
    
    def __post_init__(self):
        if not self.id:
            self.id = self.type


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
