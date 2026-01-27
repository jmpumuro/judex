"""
API schemas using Pydantic.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class VideoEvaluationRequest(BaseModel):
    """Request schema for video evaluation."""
    policy: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional policy configuration overrides"
    )


class CriterionResult(BaseModel):
    """Result for a single criterion."""
    score: float = Field(ge=0.0, le=1.0)
    status: str = Field(description="ok, caution, or violation")


class Violation(BaseModel):
    """A detected violation."""
    criterion: str
    severity: str
    score: float
    timestamp_ranges: List[List[float]] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)


class EvaluationMetadata(BaseModel):
    """Metadata about the evaluation."""
    video_id: str
    duration: float
    frames_analyzed: int
    segments_analyzed: int


class TimingSummary(BaseModel):
    """Timing information."""
    total_seconds: float
    operations: Dict[str, float] = Field(default_factory=dict)


class VideoEvaluationResponse(BaseModel):
    """Response schema for video evaluation."""
    verdict: str = Field(description="SAFE, CAUTION, UNSAFE, or NEEDS_REVIEW")
    criteria: Dict[str, CriterionResult]
    violations: List[Violation] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    report: str
    metadata: Optional[EvaluationMetadata] = None
    timings: Optional[TimingSummary] = None
    error: Optional[str] = None
    video_id: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    models_loaded: bool = False


class ModelInfo(BaseModel):
    """Information about a model."""
    model_id: str
    model_type: str
    cached: bool
    status: str


class ModelsListResponse(BaseModel):
    """Response for models list endpoint."""
    models: List[ModelInfo]


class BatchVideoItem(BaseModel):
    """Single video in a batch."""
    video_id: str
    filename: str
    status: str  # queued, processing, completed, failed
    verdict: Optional[str] = None
    progress: int = 0  # 0-100
    error: Optional[str] = None
    result: Optional[VideoEvaluationResponse] = None


class BatchEvaluationResponse(BaseModel):
    """Response for batch evaluation."""
    batch_id: str
    total_videos: int
    videos: List[BatchVideoItem]
    status: str  # queued, processing, completed
    
    
class BatchStatusResponse(BaseModel):
    """Status of a batch evaluation."""
    batch_id: str
    status: str
    completed: int
    total: int
    videos: List[BatchVideoItem]


class StorageImportRequest(BaseModel):
    """Request schema for importing from cloud storage."""
    provider: str = Field(description="s3, gcs, or azure")
    bucket: str = Field(description="Bucket or container name")
    path: Optional[str] = Field(default="", description="Path/prefix within bucket")
    credentials: Optional[str] = Field(default=None, description="Access credentials")


class DatabaseImportRequest(BaseModel):
    """Request schema for importing from database."""
    database_type: str = Field(description="postgres, mysql, or mongodb")
    connection_string: str = Field(description="Database connection string")
    query: str = Field(description="SQL query or MongoDB query")


class UrlImportRequest(BaseModel):
    """Request schema for importing from URLs."""
    urls: List[str] = Field(description="List of video URLs to import")


class ImportVideoInfo(BaseModel):
    """Information about an imported video."""
    video_id: str
    filename: str
    source: str  # storage, database, url


class ImportResponse(BaseModel):
    """Response for import endpoints."""
    success: bool
    message: str
    videos: List[ImportVideoInfo] = Field(default_factory=list)

