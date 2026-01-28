"""
Base detector class and result structure.

All detector implementations inherit from BaseDetector.
"""
from typing import Dict, List, Any, Optional
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pydantic import BaseModel
from app.evaluation.evidence import EvidenceItem, EvidenceCollection
from app.evaluation.spec import DetectorSpec


@dataclass
class DetectorResult:
    """
    Standardized result from a detector run.
    """
    # Detector identification
    detector_id: str
    detector_type: str
    
    # Evidence items produced
    evidence: EvidenceCollection = field(default_factory=EvidenceCollection)
    
    # Raw outputs (detector-specific, for backward compatibility)
    raw_outputs: Dict[str, Any] = field(default_factory=dict)
    
    # Timing
    duration_seconds: float = 0.0
    
    # Model info
    model_version: Optional[str] = None
    model_id: Optional[str] = None
    
    # Errors (non-fatal)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "detector_id": self.detector_id,
            "detector_type": self.detector_type,
            "evidence_count": len(self.evidence),
            "raw_outputs": self.raw_outputs,
            "duration_seconds": self.duration_seconds,
            "model_version": self.model_version,
            "model_id": self.model_id,
            "warnings": self.warnings
        }


class DetectorContext(BaseModel):
    """
    Context passed to detectors during execution.
    Contains shared resources and intermediate results.
    """
    # Video info
    video_path: str
    video_id: str
    work_dir: str
    
    # Video metadata
    duration: float = 0.0
    fps: float = 30.0
    width: int = 0
    height: int = 0
    has_audio: bool = False
    
    # Paths to extracted resources
    audio_path: Optional[str] = None
    
    # Sampled frames (from segmentation)
    sampled_frames: List[Dict[str, Any]] = []
    
    # Segments
    segments: List[Dict[str, Any]] = []
    
    # Results from other detectors (for dependencies)
    detector_outputs: Dict[str, DetectorResult] = {}
    
    # Progress callback
    progress_callback: Optional[Any] = None
    
    class Config:
        arbitrary_types_allowed = True


class BaseDetector(ABC):
    """
    Abstract base class for all detectors.
    
    Subclasses must implement:
    - detect(): Main detection logic
    - detector_type: Class attribute with DetectorType
    """
    
    # Subclasses should set this
    detector_type: str = "base"
    
    def __init__(self, spec: DetectorSpec):
        """
        Initialize detector with specification.
        
        Args:
            spec: DetectorSpec containing id, params, etc.
        """
        self.spec = spec
        self.detector_id = spec.id
        self.params = spec.params
        self._model = None
        self._model_version: Optional[str] = None
    
    @abstractmethod
    def detect(self, context: DetectorContext) -> DetectorResult:
        """
        Run detection on the given context.
        
        Args:
            context: DetectorContext with video info and shared resources
            
        Returns:
            DetectorResult with evidence items and raw outputs
        """
        pass
    
    def load_model(self) -> None:
        """
        Load the ML model (optional override).
        
        Detectors can lazy-load models on first use.
        """
        pass
    
    def unload_model(self) -> None:
        """
        Unload the ML model to free memory (optional override).
        """
        self._model = None
    
    def get_model_version(self) -> Optional[str]:
        """Get the model version string."""
        return self._model_version
    
    def _create_result(
        self,
        evidence: Optional[EvidenceCollection] = None,
        raw_outputs: Optional[Dict[str, Any]] = None,
        duration: float = 0.0,
        warnings: Optional[List[str]] = None
    ) -> DetectorResult:
        """
        Helper to create a DetectorResult.
        """
        return DetectorResult(
            detector_id=self.detector_id,
            detector_type=self.detector_type,
            evidence=evidence or EvidenceCollection(),
            raw_outputs=raw_outputs or {},
            duration_seconds=duration,
            model_version=self._model_version,
            model_id=self.spec.model_id,
            warnings=warnings or []
        )
    
    def _send_progress(
        self,
        context: DetectorContext,
        message: str,
        progress: int
    ) -> None:
        """Helper to send progress updates."""
        if context.progress_callback:
            try:
                import asyncio
                asyncio.get_event_loop().run_until_complete(
                    context.progress_callback(self.detector_id, message, progress)
                )
            except RuntimeError:
                # No event loop, skip progress
                pass
