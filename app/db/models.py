"""
SQLAlchemy database models for Judex.

Evaluation-centric schema:
- Evaluation: Primary entity - represents an evaluation request
- EvaluationItem: Videos being evaluated (many-to-one with Evaluation)
- EvaluationResult: Analysis results for an item
- EvaluationEvidence: Detection evidence (many-to-one with EvaluationResult)
- Criteria: Saved criteria configurations
- LiveEvent: Real-time detection events from live feeds
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, 
    ForeignKey, JSON, Enum, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship, declarative_base
import enum
import uuid

Base = declarative_base()


def generate_uuid() -> str:
    """Generate a short UUID."""
    return str(uuid.uuid4())[:8]


class EvaluationStatus(str, enum.Enum):
    """Evaluation processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Verdict(str, enum.Enum):
    """Analysis verdict."""
    SAFE = "SAFE"
    CAUTION = "CAUTION"
    UNSAFE = "UNSAFE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class EvidenceType(str, enum.Enum):
    """Type of evidence."""
    VISION = "vision"
    YOLOWORLD = "yoloworld"
    VIOLENCE = "violence"
    TRANSCRIPT = "transcript"
    OCR = "ocr"
    MODERATION = "moderation"


# =============================================================================
# EVALUATION-CENTRIC MODELS
# =============================================================================

class Evaluation(Base):
    """
    Primary entity - represents an evaluation request.
    
    An evaluation can process one or more videos with a specific criteria configuration.
    Results are automatically persisted.
    """
    __tablename__ = "evaluations"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    
    # Criteria used for this evaluation (references Criteria table - presets are seeded on startup)
    criteria_id = Column(String(64), ForeignKey("criteria.id", ondelete="SET NULL"), nullable=True, index=True)
    criteria_snapshot = Column(JSON, nullable=True)  # Snapshot of criteria at evaluation time
    
    # Processing info
    status = Column(Enum(EvaluationStatus), default=EvaluationStatus.PENDING, index=True)
    progress = Column(Integer, default=0)  # 0-100
    current_stage = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Async processing
    is_async = Column(Boolean, default=True)
    
    # Aggregate results (computed from items)
    overall_verdict = Column(Enum(Verdict), nullable=True)
    items_total = Column(Integer, default=0)
    items_completed = Column(Integer, default=0)
    items_failed = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    items = relationship("EvaluationItem", back_populates="evaluation", cascade="all, delete-orphan")
    criteria_ref = relationship("Criteria", foreign_keys=[criteria_id])
    
    __table_args__ = (
        Index('ix_evaluations_status_created', 'status', 'created_at'),
    )
    
    def to_dict(self, include_items: bool = False) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "status": self.status.value if self.status else None,
            "progress": self.progress,
            "current_stage": self.current_stage,
            "overall_verdict": self.overall_verdict.value if self.overall_verdict else None,
            "items_total": self.items_total,
            "items_completed": self.items_completed,
            "items_failed": self.items_failed,
            "criteria_id": self.criteria_id,
            "is_async": self.is_async,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
        if include_items and self.items:
            result["items"] = [item.to_dict() for item in self.items]
        return result


class EvaluationItem(Base):
    """
    A single video/item being evaluated within an Evaluation.
    """
    __tablename__ = "evaluation_items"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    evaluation_id = Column(String(36), ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False)
    
    # Source info
    source_type = Column(String(20), default="upload")  # upload, url, storage
    source_path = Column(Text, nullable=True)  # Original path/URL
    filename = Column(String(255), nullable=True)
    
    # Video metadata
    duration = Column(Float, nullable=True)
    fps = Column(Float, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    has_audio = Column(Boolean, default=False)
    file_size = Column(Integer, nullable=True)
    
    # Processing status
    status = Column(Enum(EvaluationStatus), default=EvaluationStatus.PENDING, index=True)
    progress = Column(Integer, default=0)
    current_stage = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Stage tracking (internal)
    stage_states = Column(JSON, default=dict)
    stage_outputs = Column(JSON, default=dict)
    
    # Artifacts (MinIO paths)
    uploaded_video_path = Column(String(512), nullable=True)
    labeled_video_path = Column(String(512), nullable=True)
    thumbnail_path = Column(String(512), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    evaluation = relationship("Evaluation", back_populates="items")
    result = relationship("EvaluationResult", back_populates="item", uselist=False, cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_eval_items_eval_status', 'evaluation_id', 'status'),
    )
    
    def to_dict(self, include_result: bool = True) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "evaluation_id": self.evaluation_id,
            "filename": self.filename,
            "source_type": self.source_type,
            "status": self.status.value if self.status else None,
            "progress": self.progress,
            "current_stage": self.current_stage,
            "duration": self.duration,
            "width": self.width,
            "height": self.height,
            "has_audio": self.has_audio,
            "error_message": self.error_message,
            "artifacts": {
                "uploaded_video": self.uploaded_video_path,
                "labeled_video": self.labeled_video_path,
                "thumbnail": self.thumbnail_path,
            },
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
        if include_result and self.result:
            data["result"] = self.result.to_dict()
        return data


class EvaluationResult(Base):
    """Analysis results for an evaluation item."""
    __tablename__ = "evaluation_results"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(String(36), ForeignKey("evaluation_items.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Verdict
    verdict = Column(Enum(Verdict), nullable=False, index=True)
    confidence = Column(Float, default=0.0)
    
    # Criterion scores (unified format JSON)
    criteria_scores = Column(JSON, default=dict)
    
    # Violations
    violations = Column(JSON, default=list)
    
    # Processing metadata
    processing_time = Column(Float, nullable=True)
    
    # Additional outputs
    transcript = Column(JSON, nullable=True)
    report = Column(Text, nullable=True)
    
    # Evidence reference count (for quick access)
    evidence_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    item = relationship("EvaluationItem", back_populates="result")
    evidence = relationship("EvaluationEvidence", back_populates="result", cascade="all, delete-orphan")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "verdict": self.verdict.value if self.verdict else None,
            "confidence": self.confidence,
            "criteria": self.criteria_scores,
            "violations": self.violations,
            "processing_time": self.processing_time,
            "transcript": self.transcript,
            "report": self.report,
            "evidence_count": self.evidence_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class EvaluationEvidence(Base):
    """Evidence items linked to evaluation results."""
    __tablename__ = "evaluation_evidence"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    result_id = Column(Integer, ForeignKey("evaluation_results.id", ondelete="CASCADE"), nullable=False)
    
    evidence_type = Column(Enum(EvidenceType), nullable=False, index=True)
    
    # Timing
    timestamp = Column(Float, nullable=True)
    start_time = Column(Float, nullable=True)
    end_time = Column(Float, nullable=True)
    
    # Detection data
    label = Column(String(100), nullable=True)
    category = Column(String(50), nullable=True)
    confidence = Column(Float, nullable=True)
    
    # Bounding box
    bbox_x1 = Column(Float, nullable=True)
    bbox_y1 = Column(Float, nullable=True)
    bbox_x2 = Column(Float, nullable=True)
    bbox_y2 = Column(Float, nullable=True)
    
    # Text content
    text_content = Column(Text, nullable=True)
    
    # Additional data
    extra_data = Column(JSON, nullable=True)
    
    # Relationship
    result = relationship("EvaluationResult", back_populates="evidence")
    
    __table_args__ = (
        Index('ix_eval_evidence_type_timestamp', 'evidence_type', 'timestamp'),
    )


class Criteria(Base):
    """Saved criteria configurations."""
    __tablename__ = "criteria"
    
    id = Column(String(64), primary_key=True)  # e.g., "child-safety", "custom-abc123"
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    
    # Is this a built-in preset?
    is_preset = Column(Boolean, default=False)
    
    # The full criteria configuration
    config = Column(JSON, nullable=False)
    
    # Metadata
    version = Column(String(20), default="1.0")
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_preset": self.is_preset,
            "config": self.config,
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ExternalStageConfig(Base):
    """
    External stage configurations stored as YAML.
    
    Users can define custom pipeline stages via YAML that call
    external HTTP endpoints. These are dynamically loaded at runtime.
    """
    __tablename__ = "external_stage_configs"
    
    id = Column(String(64), primary_key=True)  # e.g., "customer_policy_v1"
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    
    # The raw YAML content
    yaml_content = Column(Text, nullable=False)
    
    # Parsed stage IDs (comma-separated for quick lookup)
    stage_ids = Column(String(500), nullable=True)
    
    # Status
    enabled = Column(Boolean, default=True)
    validated = Column(Boolean, default=False)
    validation_error = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "yaml_content": self.yaml_content,
            "stage_ids": self.stage_ids.split(",") if self.stage_ids else [],
            "enabled": self.enabled,
            "validated": self.validated,
            "validation_error": self.validation_error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class StageSettings(Base):
    """
    Persisted settings for pipeline stages (both builtin and external).
    
    This enables auditable enable/disable of stages without modifying
    the stage registry or graph structure.
    """
    __tablename__ = "stage_settings"
    
    id = Column(String(64), primary_key=True)  # Stage type ID (e.g., "yolo26", "custom_policy")
    
    # Enable/disable
    enabled = Column(Boolean, default=True)
    
    # Impact level (critical/supporting/advisory)
    impact = Column(String(20), default="supporting")
    
    # If true, cannot be disabled via UI
    required = Column(Boolean, default=False)
    
    # Stage metadata (cached for fast access)
    display_name = Column(String(100), nullable=True)
    is_builtin = Column(Boolean, default=False)
    is_external = Column(Boolean, default=False)
    
    # Audit trail
    last_toggled_by = Column(String(100), nullable=True)  # Future: user tracking
    last_toggled_at = Column(DateTime, nullable=True)
    toggle_reason = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "enabled": self.enabled,
            "impact": self.impact,
            "required": self.required,
            "display_name": self.display_name,
            "is_builtin": self.is_builtin,
            "is_external": self.is_external,
            "last_toggled_at": self.last_toggled_at.isoformat() if self.last_toggled_at else None,
            "toggle_reason": self.toggle_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class LiveEvent(Base):
    """Live feed detection events."""
    __tablename__ = "live_events"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    frame_id = Column(String(64), unique=True, nullable=False)
    stream_id = Column(String(64), nullable=False, index=True)
    
    # Detection results
    violence_score = Column(Float, default=0.0)
    objects_detected = Column(JSON, default=list)  # List of detections
    
    # Thumbnail (base64 or path)
    thumbnail_path = Column(Text, nullable=True)
    
    # Review status
    reviewed = Column(Boolean, default=False)
    manual_verdict = Column(Enum(Verdict), nullable=True)
    reviewer_notes = Column(Text, nullable=True)
    
    # Timestamps
    captured_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    
    # Composite indexes
    __table_args__ = (
        Index('ix_live_events_stream_captured', 'stream_id', 'captured_at'),
        Index('ix_live_events_reviewed_captured', 'reviewed', 'captured_at'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "stream_id": self.stream_id,
            "violence_score": self.violence_score,
            "objects": self.objects_detected,
            "reviewed": self.reviewed,
            "manual_verdict": self.manual_verdict.value if self.manual_verdict else None,
            "captured_at": self.captured_at.isoformat() if self.captured_at else None,
        }


# =============================================================================
# Criteria Configuration with Versioning
# =============================================================================

class CriteriaConfig(Base):
    """
    Custom criteria configuration with fusion settings and stage overrides.
    
    Industry Standard: Configuration versioning for audit trail and rollback.
    """
    __tablename__ = "criteria_configs"
    
    id = Column(String(64), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Base criteria (the criteria definitions)
    criteria_data = Column(JSON, nullable=False, default=dict)
    options_data = Column(JSON, nullable=True)
    
    # Fusion settings (verdict strategy, weights, thresholds)
    fusion_settings = Column(JSON, nullable=True)
    
    # Stage-specific knob overrides
    stage_overrides = Column(JSON, nullable=True)
    
    # Version tracking
    current_version = Column(String(64), nullable=True)
    
    # Metadata
    is_active = Column(Boolean, default=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    versions = relationship("CriteriaVersion", back_populates="config", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_criteria_configs_name', 'name'),
        Index('ix_criteria_configs_active', 'is_active'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "criteria_data": self.criteria_data,
            "options_data": self.options_data,
            "fusion_settings": self.fusion_settings,
            "stage_overrides": self.stage_overrides,
            "current_version": self.current_version,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CriteriaVersion(Base):
    """
    Version history for criteria configurations.
    
    Every config change creates a new version for audit and rollback.
    """
    __tablename__ = "criteria_versions"
    
    id = Column(String(64), primary_key=True, default=generate_uuid)
    criteria_id = Column(String(64), ForeignKey("criteria_configs.id", ondelete="CASCADE"), nullable=False)
    
    # Snapshot of the config at this version
    version_data = Column(JSON, nullable=False)
    
    # Change metadata
    change_summary = Column(Text, nullable=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    config = relationship("CriteriaConfig", back_populates="versions")
    
    __table_args__ = (
        Index('ix_criteria_versions_criteria_id', 'criteria_id'),
        Index('ix_criteria_versions_created_at', 'created_at'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "criteria_id": self.criteria_id,
            "version_data": self.version_data,
            "change_summary": self.change_summary,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# Chat/Conversation Models (ReportChat Agent)
# =============================================================================

class ChatThread(Base):
    """
    A chat conversation thread for discussing an evaluation.
    
    Industry Standard: Scoped to evaluation + user for access control.
    """
    __tablename__ = "chat_threads"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    evaluation_id = Column(String(36), ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(255), nullable=True)  # Optional user scoping
    
    # Thread metadata
    title = Column(String(255), nullable=True)  # Optional thread title
    
    # Memory management
    summary = Column(Text, nullable=True)  # Summarized older messages
    summarized_up_to = Column(Integer, default=0)  # Index of last summarized message
    message_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    messages = relationship("ChatMessage", back_populates="thread", cascade="all, delete-orphan")
    evaluation = relationship("Evaluation", foreign_keys=[evaluation_id])
    
    __table_args__ = (
        Index('ix_chat_threads_evaluation_id', 'evaluation_id'),
        Index('ix_chat_threads_user_id', 'user_id'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "evaluation_id": self.evaluation_id,
            "user_id": self.user_id,
            "title": self.title,
            "message_count": self.message_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ChatMessage(Base):
    """
    A single message in a chat thread.
    
    Stores role, content, tool calls, and metadata.
    """
    __tablename__ = "chat_messages"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    thread_id = Column(String(36), ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False)
    
    # Message content
    role = Column(String(20), nullable=False)  # user, assistant, system, tool
    content = Column(Text, nullable=False)
    
    # Tool calls (for tracing/audit)
    tool_calls = Column(JSON, nullable=True)  # List of tool call records
    
    # Additional message metadata (named message_meta to avoid SQLAlchemy reserved name)
    message_meta = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    thread = relationship("ChatThread", back_populates="messages")
    
    __table_args__ = (
        Index('ix_chat_messages_thread_id', 'thread_id'),
        Index('ix_chat_messages_created_at', 'created_at'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "role": self.role,
            "content": self.content,
            "tool_calls": self.tool_calls,
            "metadata": self.message_meta,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
