"""
SQLAlchemy database models for SafeVid.

Industry-standard schema with proper relationships:
- Video: Main entity, represents uploaded videos
- VideoResult: Analysis results (one-to-one with Video)
- Evidence: Detection evidence (many-to-one with VideoResult)
- Checkpoint: Processing checkpoints for resumable processing
- ArchivedCheckpoint: Archived checkpoints for completed videos
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

Base = declarative_base()


class VideoStatus(str, enum.Enum):
    """Video processing status."""
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


class Video(Base):
    """Main video entity."""
    __tablename__ = "videos"
    
    id = Column(String(64), primary_key=True)  # UUID
    filename = Column(String(255), nullable=False)
    original_path = Column(Text, nullable=True)  # Original upload path (local)
    
    # MinIO object storage paths
    uploaded_video_path = Column(String(512), nullable=True)  # MinIO path for original video
    labeled_video_path = Column(String(512), nullable=True)   # MinIO path for labeled video
    thumbnail_path = Column(String(512), nullable=True)       # MinIO path for thumbnail
    
    # Video metadata
    duration = Column(Float, nullable=True)
    fps = Column(Float, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    has_audio = Column(Boolean, default=False)
    file_size = Column(Integer, nullable=True)  # bytes
    
    # Processing info
    status = Column(Enum(VideoStatus), default=VideoStatus.PENDING, index=True)
    batch_id = Column(String(64), nullable=True, index=True)
    source = Column(String(50), default="upload")  # upload, url, storage, database
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    
    # Relationships
    result = relationship("VideoResult", back_populates="video", uselist=False, cascade="all, delete-orphan")
    checkpoint = relationship("Checkpoint", back_populates="video", uselist=False, cascade="all, delete-orphan")
    archived_checkpoint = relationship("ArchivedCheckpoint", back_populates="video", uselist=False, cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('ix_videos_status_created', 'status', 'created_at'),
        Index('ix_videos_batch_status', 'batch_id', 'status'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "duration": self.duration,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "has_audio": self.has_audio,
            "status": self.status.value if self.status else None,
            "batch_id": self.batch_id,
            "source": self.source,
            "uploaded_video_path": self.uploaded_video_path,
            "labeled_video_path": self.labeled_video_path,
            "thumbnail_path": self.thumbnail_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }


class VideoResult(Base):
    """Analysis results for a video."""
    __tablename__ = "video_results"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(64), ForeignKey("videos.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Verdict
    verdict = Column(Enum(Verdict), nullable=False, index=True)
    
    # Criterion scores (0-1)
    violence_score = Column(Float, default=0.0)
    profanity_score = Column(Float, default=0.0)
    sexual_score = Column(Float, default=0.0)
    drugs_score = Column(Float, default=0.0)
    hate_score = Column(Float, default=0.0)
    
    # Processing metadata
    processing_time = Column(Float, nullable=True)  # seconds
    models_used = Column(JSON, default=list)  # List of model IDs used
    policy_config = Column(JSON, nullable=True)  # Policy config used
    
    # Full result data (JSON blob for flexibility)
    violations = Column(JSON, default=list)
    transcript = Column(JSON, nullable=True)
    report = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    video = relationship("Video", back_populates="result")
    evidence = relationship("Evidence", back_populates="result", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('ix_results_verdict_created', 'verdict', 'created_at'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_id": self.video_id,
            "verdict": self.verdict.value if self.verdict else None,
            "criteria": {
                "violence": self.violence_score,
                "profanity": self.profanity_score,
                "sexual": self.sexual_score,
                "drugs": self.drugs_score,
                "hate": self.hate_score,
            },
            "processing_time": self.processing_time,
            "violations": self.violations,
            "report": self.report,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Evidence(Base):
    """Evidence items linked to video results."""
    __tablename__ = "evidence"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    result_id = Column(Integer, ForeignKey("video_results.id", ondelete="CASCADE"), nullable=False)
    
    evidence_type = Column(Enum(EvidenceType), nullable=False, index=True)
    
    # Timing
    timestamp = Column(Float, nullable=True)  # seconds into video
    start_time = Column(Float, nullable=True)
    end_time = Column(Float, nullable=True)
    
    # Detection data
    label = Column(String(100), nullable=True)
    category = Column(String(50), nullable=True)  # weapon, substance, person, etc.
    confidence = Column(Float, nullable=True)
    
    # Bounding box (for vision evidence)
    bbox_x1 = Column(Float, nullable=True)
    bbox_y1 = Column(Float, nullable=True)
    bbox_x2 = Column(Float, nullable=True)
    bbox_y2 = Column(Float, nullable=True)
    
    # Text content (for transcript/OCR)
    text_content = Column(Text, nullable=True)
    
    # Additional data (JSON for flexibility)
    extra_data = Column(JSON, nullable=True)
    
    # Relationship
    result = relationship("VideoResult", back_populates="evidence")
    
    # Indexes
    __table_args__ = (
        Index('ix_evidence_type_timestamp', 'evidence_type', 'timestamp'),
    )


class Checkpoint(Base):
    """Processing checkpoint for resumable video processing."""
    __tablename__ = "checkpoints"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(64), ForeignKey("videos.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Current stage
    current_stage = Column(String(50), nullable=False)
    progress = Column(Integer, default=0)  # 0-100
    
    # Stage states (JSON blob) - tracking progress per stage
    stage_states = Column(JSON, default=dict)
    
    # Stage outputs (JSON blob) - actual output data from each completed stage
    # This allows fetching intermediate results as stages complete
    stage_outputs = Column(JSON, default=dict)
    
    # Partial results
    partial_results = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    video = relationship("Video", back_populates="checkpoint")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_id": self.video_id,
            "current_stage": self.current_stage,
            "progress": self.progress,
            "stage_states": self.stage_states,
            "stage_outputs": self.stage_outputs,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ArchivedCheckpoint(Base):
    """Archived checkpoint for completed videos (audit trail)."""
    __tablename__ = "archived_checkpoints"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(64), ForeignKey("videos.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Final state
    final_stage = Column(String(50), nullable=False)
    total_processing_time = Column(Float, nullable=True)  # seconds
    
    # Complete stage history
    stage_history = Column(JSON, default=list)  # List of {stage, start_time, end_time, status}
    
    # Final results snapshot
    final_results = Column(JSON, nullable=True)
    
    # Timestamps
    completed_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    video = relationship("Video", back_populates="archived_checkpoint")


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
    
    # Composite indexes (single-column indexes are implicit via index=True on Column)
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
