"""
API Schemas (DTOs) - Single source of truth for API data structures.

These Pydantic models serve as Data Transfer Objects between:
- Database models ↔ API endpoints
- Backend ↔ Frontend

All API responses should use these schemas for consistency.
"""
from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


# ============================================================================
# Enums (shared between backend and can be used to generate frontend types)
# ============================================================================

class EvaluationStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Verdict(str, Enum):
    SAFE = "SAFE"
    CAUTION = "CAUTION"
    UNSAFE = "UNSAFE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ============================================================================
# Criteria DTOs
# ============================================================================

class CriterionSummaryDTO(BaseModel):
    """Summary of a single criterion."""
    id: str
    label: str
    severity: Severity
    enabled: bool = True


class CriteriaSummaryDTO(BaseModel):
    """Summary of a criteria configuration."""
    id: str
    name: str
    description: Optional[str] = None
    criteria_count: int
    is_preset: bool = False
    
    model_config = ConfigDict(from_attributes=True)


class CriteriaDetailDTO(CriteriaSummaryDTO):
    """Full criteria configuration."""
    version: str = "1.0"
    criteria: Dict[str, CriterionSummaryDTO] = Field(default_factory=dict)
    config_yaml: Optional[str] = None  # For export


# ============================================================================
# Evaluation Result DTOs
# ============================================================================

class ViolationDTO(BaseModel):
    """A single violation found during evaluation."""
    criterion: str
    label: str
    severity: Severity
    score: float = Field(ge=0.0, le=1.0)
    evidence: Optional[Dict[str, Any]] = None


class CriterionScoreDTO(BaseModel):
    """Score for a single criterion."""
    score: float = Field(ge=0.0, le=1.0)
    verdict: Verdict
    label: str
    severity: Severity


class EvaluationResultDTO(BaseModel):
    """Result of evaluating a single item."""
    item_id: str
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    criteria_scores: Dict[str, CriterionScoreDTO] = Field(default_factory=dict)
    violations: List[ViolationDTO] = Field(default_factory=list)
    report: Optional[str] = None
    transcript: Optional[Dict[str, Any]] = None
    processing_time_sec: Optional[float] = None


# ============================================================================
# Evaluation Item DTOs
# ============================================================================

class EvaluationItemDTO(BaseModel):
    """A single video/item within an evaluation."""
    id: str
    evaluation_id: str
    filename: str
    source_type: str = "upload"
    status: EvaluationStatus
    progress: int = Field(ge=0, le=100, default=0)
    current_stage: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    # Artifacts
    labeled_video_path: Optional[str] = None
    uploaded_video_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    
    # Stage outputs (intermediate results)
    stage_outputs: Dict[str, Any] = Field(default_factory=dict)
    
    # Result (if completed)
    result: Optional[EvaluationResultDTO] = None
    
    model_config = ConfigDict(from_attributes=True)
    
    @classmethod
    def from_db(cls, item: "EvaluationItem") -> "EvaluationItemDTO":
        """Create DTO from database model while in session."""
        result_dto = None
        if item.result:
            result_dto = EvaluationResultDTO(
                item_id=item.id,
                verdict=Verdict(item.result.verdict.value) if item.result.verdict else Verdict.NEEDS_REVIEW,
                confidence=item.result.confidence or 0.0,
                criteria_scores={
                    k: CriterionScoreDTO(**v) if isinstance(v, dict) else CriterionScoreDTO(score=0, verdict=Verdict.SAFE, label=k, severity=Severity.LOW)
                    for k, v in (item.result.criteria_scores or {}).items()
                },
                violations=[ViolationDTO(**v) for v in (item.result.violations or [])],
                report=item.result.report,
                processing_time_sec=item.result.processing_time
            )
        
        return cls(
            id=item.id,
            evaluation_id=item.evaluation_id,
            filename=item.filename,
            source_type=item.source_type or "upload",
            status=EvaluationStatus(item.status.value) if item.status else EvaluationStatus.PENDING,
            progress=item.progress or 0,
            current_stage=item.current_stage,
            error_message=item.error_message,
            created_at=item.created_at,
            completed_at=item.completed_at,
            labeled_video_path=item.labeled_video_path,
            uploaded_video_path=item.uploaded_video_path,
            thumbnail_path=item.thumbnail_path,
            stage_outputs=item.stage_outputs or {},
            result=result_dto
        )


# ============================================================================
# Evaluation DTOs
# ============================================================================

class EvaluationSummaryDTO(BaseModel):
    """Summary of an evaluation (for list views)."""
    id: str
    status: EvaluationStatus
    progress: int = Field(ge=0, le=100, default=0)
    overall_verdict: Optional[Verdict] = None
    items_total: int = 0
    items_completed: int = 0
    items_failed: int = 0
    criteria_id: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)
    
    @classmethod
    def from_db(cls, evaluation: "Evaluation") -> "EvaluationSummaryDTO":
        """Create DTO from database model while in session."""
        return cls(
            id=evaluation.id,
            status=EvaluationStatus(evaluation.status.value) if evaluation.status else EvaluationStatus.PENDING,
            progress=evaluation.progress or 0,
            overall_verdict=Verdict(evaluation.overall_verdict.value) if evaluation.overall_verdict else None,
            items_total=evaluation.items_total or 0,
            items_completed=evaluation.items_completed or 0,
            items_failed=evaluation.items_failed or 0,
            criteria_id=evaluation.criteria_id,
            created_at=evaluation.created_at,
            completed_at=evaluation.completed_at
        )


class EvaluationDTO(EvaluationSummaryDTO):
    """Full evaluation with items."""
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    items: List[EvaluationItemDTO] = Field(default_factory=list)
    
    @classmethod
    def from_db(cls, evaluation: "Evaluation", include_items: bool = True) -> "EvaluationDTO":
        """Create DTO from database model while in session."""
        items = []
        if include_items:
            items = [EvaluationItemDTO.from_db(item) for item in evaluation.items]
        
        return cls(
            id=evaluation.id,
            status=EvaluationStatus(evaluation.status.value) if evaluation.status else EvaluationStatus.PENDING,
            progress=evaluation.progress or 0,
            overall_verdict=Verdict(evaluation.overall_verdict.value) if evaluation.overall_verdict else None,
            items_total=evaluation.items_total or 0,
            items_completed=evaluation.items_completed or 0,
            items_failed=evaluation.items_failed or 0,
            criteria_id=evaluation.criteria_id,
            error_message=evaluation.error_message,
            created_at=evaluation.created_at,
            started_at=evaluation.started_at,
            completed_at=evaluation.completed_at,
            items=items
        )


# ============================================================================
# API Request/Response DTOs
# ============================================================================

class EvaluationCreateRequest(BaseModel):
    """Request to create a new evaluation."""
    criteria_id: Optional[str] = None
    criteria_yaml: Optional[str] = None
    criteria_json: Optional[str] = None
    is_async: bool = True
    urls: Optional[List[str]] = None  # For URL-based imports


class EvaluationCreateResponse(BaseModel):
    """Response after creating an evaluation."""
    id: str
    status: EvaluationStatus
    items_total: int
    criteria_id: Optional[str] = None
    is_async: bool = True


class EvaluationListResponse(BaseModel):
    """Response for listing evaluations."""
    evaluations: List[EvaluationSummaryDTO]
    total: int


class ProgressEventDTO(BaseModel):
    """SSE progress event."""
    stage: str
    message: str
    progress: int = Field(ge=0, le=100)
    item_id: Optional[str] = None
    evaluation_complete: bool = False


class StageOutputDTO(BaseModel):
    """Output from a pipeline stage."""
    evaluation_id: str
    item_id: Optional[str] = None
    stage: str
    output: Dict[str, Any]


class ArtifactDTO(BaseModel):
    """Reference to an artifact (video, thumbnail, etc.)."""
    url: str
    artifact_type: str
    item_id: str
    expires_at: Optional[datetime] = None


# ============================================================================
# Health/Status DTOs
# ============================================================================

class HealthDTO(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str
    models_loaded: bool = False


# Type hints for ORM models (avoid circular imports)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.db.models import Evaluation, EvaluationItem


# ============================================================================
# Legacy Schemas (Backward Compatibility for deprecated endpoints)
# ============================================================================

class VideoEvaluationResponse(BaseModel):
    """Legacy response for single video evaluation."""
    video_id: str
    verdict: str
    confidence: float = 0.0
    criteria: Dict[str, Any] = Field(default_factory=dict)
    violations: List[Dict[str, Any]] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    report: Optional[str] = None
    transcript: Optional[Dict[str, Any]] = None
    processing_time_sec: Optional[float] = None
    labeled_video_path: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str
    models_loaded: bool = False


class ModelInfo(BaseModel):
    """Information about a loaded model."""
    model_id: str
    model_type: str  # vision, violence_xclip, violence_videomae, pose_heuristics, asr, moderation, llm
    cached: bool = False
    status: str = "unknown"  # ready, loading, error, disabled
    device: Optional[str] = None
    
    # Alias for backward compatibility
    @property
    def name(self) -> str:
        return self.model_id
    
    @property
    def loaded(self) -> bool:
        return self.status == "ready"


class ModelsListResponse(BaseModel):
    """List of available models."""
    models: List[ModelInfo] = Field(default_factory=list)


class BatchVideoItem(BaseModel):
    """Single video in a batch."""
    video_id: str
    filename: str
    status: str = "pending"
    progress: int = 0
    verdict: Optional[str] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


class BatchEvaluationResponse(BaseModel):
    """Response for batch upload."""
    batch_id: str
    status: str = "pending"
    videos: List[BatchVideoItem] = Field(default_factory=list)


class BatchStatusResponse(BaseModel):
    """Status of a batch evaluation."""
    batch_id: str
    status: str
    total_videos: int = 0
    completed: int = 0
    failed: int = 0
    videos: Dict[str, BatchVideoItem] = Field(default_factory=dict)
