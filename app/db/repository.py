"""
Database repository for SafeVid CRUD operations.

Industry-standard repository pattern for data access.
Uses MinIO for file storage and PostgreSQL for metadata.
"""
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import desc, and_

from app.db.models import (
    Video, VideoResult, Evidence, Checkpoint, 
    ArchivedCheckpoint, LiveEvent, VideoStatus, Verdict, EvidenceType
)
from app.core.logging import get_logger
from app.utils.storage import get_storage_service

logger = get_logger("db.repository")


# ============== VIDEO REPOSITORY ==============

class VideoRepository:
    """Repository for Video CRUD operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, video_id: str, filename: str, **kwargs) -> Video:
        """Create a new video record."""
        video = Video(
            id=video_id,
            filename=filename,
            **kwargs
        )
        self.db.add(video)
        self.db.commit()
        self.db.refresh(video)
        logger.info(f"Created video: {video_id}")
        return video
    
    def get(self, video_id: str) -> Optional[Video]:
        """Get video by ID."""
        return self.db.query(Video).filter(Video.id == video_id).first()
    
    def get_by_batch(self, batch_id: str) -> List[Video]:
        """Get all videos in a batch."""
        return self.db.query(Video).filter(Video.batch_id == batch_id).all()
    
    def list(self, skip: int = 0, limit: int = 100, status: Optional[VideoStatus] = None) -> List[Video]:
        """List videos with optional filtering."""
        query = self.db.query(Video)
        if status:
            query = query.filter(Video.status == status)
        return query.order_by(desc(Video.created_at)).offset(skip).limit(limit).all()
    
    def update(self, video_id: str, **kwargs) -> Optional[Video]:
        """Update video record."""
        video = self.get(video_id)
        if not video:
            return None
        
        for key, value in kwargs.items():
            if hasattr(video, key):
                setattr(video, key, value)
        
        video.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(video)
        return video
    
    def update_status(self, video_id: str, status: VideoStatus) -> Optional[Video]:
        """Update video status."""
        return self.update(video_id, status=status)
    
    def delete(self, video_id: str) -> bool:
        """Delete video and all related records (cascade)."""
        video = self.get(video_id)
        if not video:
            return False
        
        self.db.delete(video)
        self.db.commit()
        logger.info(f"Deleted video: {video_id}")
        return True
    
    def delete_all(self) -> int:
        """Delete all videos."""
        count = self.db.query(Video).delete()
        self.db.commit()
        logger.info(f"Deleted all videos: {count}")
        return count


# ============== RESULT REPOSITORY ==============

class ResultRepository:
    """Repository for VideoResult CRUD operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, video_id: str, verdict: Verdict, **kwargs) -> VideoResult:
        """Create a new result record."""
        result = VideoResult(
            video_id=video_id,
            verdict=verdict,
            **kwargs
        )
        self.db.add(result)
        self.db.commit()
        self.db.refresh(result)
        logger.info(f"Created result for video: {video_id}, verdict: {verdict}")
        return result
    
    def get(self, video_id: str) -> Optional[VideoResult]:
        """Get result by video ID."""
        return self.db.query(VideoResult).filter(VideoResult.video_id == video_id).first()
    
    def get_by_verdict(self, verdict: Verdict, limit: int = 100) -> List[VideoResult]:
        """Get results by verdict."""
        return self.db.query(VideoResult).filter(
            VideoResult.verdict == verdict
        ).order_by(desc(VideoResult.created_at)).limit(limit).all()
    
    def get_all(self, limit: int = 100) -> List[VideoResult]:
        """Get all results, ordered by most recent first."""
        return self.db.query(VideoResult).order_by(
            desc(VideoResult.created_at)
        ).limit(limit).all()
    
    def upsert(self, video_id: str, verdict: Verdict, **kwargs) -> VideoResult:
        """Create or update result."""
        existing = self.get(video_id)
        if existing:
            for key, value in kwargs.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.verdict = verdict
            self.db.commit()
            self.db.refresh(existing)
            return existing
        return self.create(video_id, verdict, **kwargs)
    
    def add_evidence(self, result_id: int, evidence_type: EvidenceType, **kwargs) -> Evidence:
        """Add evidence to a result."""
        evidence = Evidence(
            result_id=result_id,
            evidence_type=evidence_type,
            **kwargs
        )
        self.db.add(evidence)
        self.db.commit()
        return evidence
    
    def get_evidence(self, result_id: int, evidence_type: Optional[EvidenceType] = None) -> List[Evidence]:
        """Get evidence for a result."""
        query = self.db.query(Evidence).filter(Evidence.result_id == result_id)
        if evidence_type:
            query = query.filter(Evidence.evidence_type == evidence_type)
        return query.order_by(Evidence.timestamp).all()
    
    def delete(self, video_id: str) -> bool:
        """Delete a result and its evidence by video ID."""
        result = self.get(video_id)
        if not result:
            return False
        
        # Delete associated evidence first
        self.db.query(Evidence).filter(Evidence.result_id == result.id).delete()
        
        # Delete the result
        self.db.delete(result)
        self.db.commit()
        logger.info(f"Deleted result for video: {video_id}")
        return True
    
    def delete_all(self) -> int:
        """Delete all results and evidence."""
        # Delete all evidence first
        evidence_count = self.db.query(Evidence).delete()
        
        # Delete all results
        result_count = self.db.query(VideoResult).delete()
        
        self.db.commit()
        logger.info(f"Deleted all results: {result_count} results, {evidence_count} evidence items")
        return result_count


# ============== CHECKPOINT REPOSITORY ==============

class CheckpointRepository:
    """Repository for Checkpoint CRUD operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def _video_exists(self, video_id: str) -> bool:
        """Check if video record exists (for foreign key constraint)."""
        return self.db.query(Video).filter(Video.id == video_id).first() is not None
    
    def create(self, video_id: str, current_stage: str, progress: int = 0,
               stage_states: Dict = None, partial_results: Dict = None,
               stage_outputs: Dict = None) -> Optional[Checkpoint]:
        """Create a new checkpoint. Returns None if video doesn't exist."""
        # Check if video exists (foreign key constraint)
        if not self._video_exists(video_id):
            logger.debug(f"Cannot create checkpoint: video {video_id} doesn't exist in DB")
            return None
        
        checkpoint = Checkpoint(
            video_id=video_id,
            current_stage=current_stage,
            progress=progress,
            stage_states=stage_states or {},
            partial_results=partial_results,
            stage_outputs=stage_outputs or {}
        )
        self.db.add(checkpoint)
        self.db.commit()
        self.db.refresh(checkpoint)
        return checkpoint
    
    def get(self, video_id: str) -> Optional[Checkpoint]:
        """Get checkpoint by video ID."""
        return self.db.query(Checkpoint).filter(Checkpoint.video_id == video_id).first()
    
    def list(self) -> List[Checkpoint]:
        """List all active checkpoints."""
        return self.db.query(Checkpoint).order_by(desc(Checkpoint.updated_at)).all()
    
    def upsert(self, video_id: str, current_stage: str, progress: int = 0, 
               stage_states: Dict = None, partial_results: Dict = None,
               stage_outputs: Dict = None) -> Optional[Checkpoint]:
        """Create or update checkpoint. Returns None if video doesn't exist."""
        existing = self.get(video_id)
        if existing:
            existing.current_stage = current_stage
            existing.progress = progress
            if stage_states:
                existing.stage_states = stage_states
            if partial_results:
                existing.partial_results = partial_results
            if stage_outputs:
                # Merge new stage outputs with existing ones
                current_outputs = existing.stage_outputs or {}
                current_outputs.update(stage_outputs)
                existing.stage_outputs = current_outputs
            existing.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(existing)
            return existing
        return self.create(
            video_id=video_id,
            current_stage=current_stage,
            progress=progress,
            stage_states=stage_states or {},
            partial_results=partial_results,
            stage_outputs=stage_outputs or {}
        )
    
    def save_stage_output(self, video_id: str, stage_name: str, output: Dict) -> Optional[Checkpoint]:
        """
        Save output for a specific stage. 
        This is called after each stage completes to store its results.
        Returns None if video doesn't exist in database.
        """
        existing = self.get(video_id)
        if not existing:
            # Create checkpoint if it doesn't exist
            existing = self.create(
                video_id=video_id,
                current_stage=stage_name,
                progress=0,
                stage_outputs={stage_name: output}
            )
            # If create returned None (video doesn't exist), bail out
            if existing is None:
                return None
        else:
            # Update existing checkpoint with new stage output
            current_outputs = existing.stage_outputs or {}
            current_outputs[stage_name] = output
            existing.stage_outputs = current_outputs
            existing.current_stage = stage_name
            existing.updated_at = datetime.utcnow()
            # Flag JSON field as modified so SQLAlchemy detects the change
            flag_modified(existing, 'stage_outputs')
            self.db.commit()
            self.db.refresh(existing)
        
        return existing
    
    def get_stage_output(self, video_id: str, stage_name: str) -> Optional[Dict]:
        """Get output for a specific stage."""
        checkpoint = self.get(video_id)
        if not checkpoint or not checkpoint.stage_outputs:
            return None
        return checkpoint.stage_outputs.get(stage_name)
    
    def get_all_stage_outputs(self, video_id: str) -> Dict[str, Dict]:
        """Get all stage outputs for a video."""
        checkpoint = self.get(video_id)
        if not checkpoint:
            return {}
        return checkpoint.stage_outputs or {}
    
    def delete(self, video_id: str) -> bool:
        """Delete checkpoint."""
        checkpoint = self.get(video_id)
        if not checkpoint:
            return False
        self.db.delete(checkpoint)
        self.db.commit()
        return True
    
    def delete_all(self) -> int:
        """Delete all checkpoints."""
        count = self.db.query(Checkpoint).delete()
        self.db.commit()
        logger.info(f"Deleted all checkpoints: {count}")
        return count
    
    def archive(self, video_id: str, final_results: Dict = None) -> Optional[ArchivedCheckpoint]:
        """Archive checkpoint for completed video."""
        checkpoint = self.get(video_id)
        if not checkpoint:
            return None
        
        # Calculate total processing time from stage history
        stage_history = []
        total_time = 0
        if checkpoint.stage_states:
            for stage, state in checkpoint.stage_states.items():
                if isinstance(state, dict):
                    stage_history.append({
                        "stage": stage,
                        "progress": state.get("progress", 100),
                        "status": "completed"
                    })
        
        # Create archived checkpoint
        archived = ArchivedCheckpoint(
            video_id=video_id,
            final_stage=checkpoint.current_stage,
            total_processing_time=total_time,
            stage_history=stage_history,
            final_results=final_results or checkpoint.partial_results,
            completed_at=datetime.utcnow()
        )
        self.db.add(archived)
        
        # Delete active checkpoint
        self.db.delete(checkpoint)
        self.db.commit()
        
        logger.info(f"Archived checkpoint for video: {video_id}")
        return archived


# ============== LIVE EVENT REPOSITORY ==============

class LiveEventRepository:
    """Repository for LiveEvent CRUD operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, frame_id: str, stream_id: str, **kwargs) -> LiveEvent:
        """Create a new live event."""
        event = LiveEvent(
            frame_id=frame_id,
            stream_id=stream_id,
            **kwargs
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event
    
    def get(self, frame_id: str) -> Optional[LiveEvent]:
        """Get event by frame ID."""
        return self.db.query(LiveEvent).filter(LiveEvent.frame_id == frame_id).first()
    
    def list(self, stream_id: Optional[str] = None, reviewed: Optional[bool] = None, 
             limit: int = 100) -> List[LiveEvent]:
        """List events with optional filtering."""
        query = self.db.query(LiveEvent)
        if stream_id:
            query = query.filter(LiveEvent.stream_id == stream_id)
        if reviewed is not None:
            query = query.filter(LiveEvent.reviewed == reviewed)
        return query.order_by(desc(LiveEvent.captured_at)).limit(limit).all()
    
    def mark_reviewed(self, frame_id: str, verdict: Verdict, notes: str = None) -> Optional[LiveEvent]:
        """Mark event as reviewed."""
        event = self.get(frame_id)
        if not event:
            return None
        
        event.reviewed = True
        event.manual_verdict = verdict
        event.reviewer_notes = notes
        event.reviewed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(event)
        return event
    
    def delete(self, frame_id: str) -> bool:
        """Delete event."""
        event = self.get(frame_id)
        if not event:
            return False
        self.db.delete(event)
        self.db.commit()
        return True
    
    def clear_stream(self, stream_id: str) -> int:
        """Delete all events for a stream."""
        count = self.db.query(LiveEvent).filter(LiveEvent.stream_id == stream_id).delete()
        self.db.commit()
        return count


# ============== CONVENIENCE FUNCTIONS ==============

def save_video_result(
    db: Session, 
    video_id: str, 
    result: Dict[str, Any],
    uploaded_video_path: Optional[str] = None,
    labeled_video_path: Optional[str] = None
) -> VideoResult:
    """
    Save complete video result to database and upload files to MinIO.
    
    This is the main function to call after pipeline completion.
    It creates/updates video, result, evidence records and uploads files.
    
    Args:
        db: Database session
        video_id: Video identifier
        result: Pipeline result dictionary
        uploaded_video_path: Local path to original uploaded video
        labeled_video_path: Local path to labeled/processed video
    """
    video_repo = VideoRepository(db)
    result_repo = ResultRepository(db)
    checkpoint_repo = CheckpointRepository(db)
    storage = get_storage_service()
    
    # Upload files to MinIO
    uploaded_object_path = None
    labeled_object_path = None
    
    try:
        if uploaded_video_path and Path(uploaded_video_path).exists():
            uploaded_object_path = storage.upload_video(uploaded_video_path, video_id)
            logger.info(f"Uploaded original video to MinIO: {uploaded_object_path}")
        
        if labeled_video_path and Path(labeled_video_path).exists():
            labeled_object_path = storage.upload_labeled_video(labeled_video_path, video_id)
            logger.info(f"Uploaded labeled video to MinIO: {labeled_object_path}")
    except Exception as e:
        logger.error(f"Failed to upload video files to MinIO: {e}")
        # Continue without file uploads - files will be served from local if available
    
    # Update video status (metadata is nested in result["metadata"])
    video = video_repo.get(video_id)
    metadata = result.get("metadata", {})
    if video:
        video_repo.update(
            video_id,
            status=VideoStatus.COMPLETED,
            duration=metadata.get("duration") or result.get("duration"),
            fps=metadata.get("fps") or result.get("fps"),
            width=metadata.get("width") or result.get("width"),
            height=metadata.get("height") or result.get("height"),
            has_audio=metadata.get("has_audio") or result.get("has_audio", False),
            processed_at=datetime.utcnow(),
            uploaded_video_path=uploaded_object_path,
            labeled_video_path=labeled_object_path
        )
    
    # Get criterion scores (criteria has format: {"violence": {"score": 0.5, "status": "..."}, ...})
    criteria = result.get("criteria", {})
    
    def get_score(name):
        val = criteria.get(name, {})
        if isinstance(val, dict):
            # Try both "score" and "value" for backwards compatibility
            return val.get("score") or val.get("value") or 0.0
        return float(val) if val else 0.0
    
    # Create/update result
    db_result = result_repo.upsert(
        video_id=video_id,
        verdict=Verdict(result.get("verdict", "NEEDS_REVIEW")),
        violence_score=get_score("violence"),
        profanity_score=get_score("profanity"),
        sexual_score=get_score("sexual"),
        drugs_score=get_score("drugs"),
        hate_score=get_score("hate"),
        processing_time=result.get("processing_time_sec") or result.get("processing_time"),
        violations=result.get("violations", []),
        transcript=result.get("transcript"),
        report=result.get("report")
    )
    
    # Save evidence
    evidence = result.get("evidence", {})
    
    # Vision evidence
    for det in evidence.get("vision", []):
        bbox = det.get("bbox", {})
        result_repo.add_evidence(
            db_result.id,
            EvidenceType.VISION,
            timestamp=det.get("timestamp"),
            label=det.get("label"),
            category=det.get("category"),
            confidence=det.get("confidence"),
            bbox_x1=bbox.get("x1"),
            bbox_y1=bbox.get("y1"),
            bbox_x2=bbox.get("x2"),
            bbox_y2=bbox.get("y2")
        )
    
    # Violence segments
    for seg in evidence.get("violence_segments", []):
        result_repo.add_evidence(
            db_result.id,
            EvidenceType.VIOLENCE,
            start_time=seg.get("start_time"),
            end_time=seg.get("end_time"),
            confidence=seg.get("violence_score"),
            label=seg.get("label"),
            extra_data={"all_predictions": seg.get("all_predictions")}
        )
    
    # Transcript
    for chunk in evidence.get("transcript", {}).get("chunks", []):
        result_repo.add_evidence(
            db_result.id,
            EvidenceType.TRANSCRIPT,
            start_time=chunk.get("start_time"),
            end_time=chunk.get("end_time"),
            text_content=chunk.get("text")
        )
    
    # YOLOWORLD detections
    for det in evidence.get("yoloworld", []):
        bbox = det.get("bbox", {})
        result_repo.add_evidence(
            db_result.id,
            EvidenceType.YOLOWORLD,
            timestamp=det.get("timestamp"),
            label=det.get("label") or det.get("prompt_match"),
            category=det.get("category"),
            confidence=det.get("confidence"),
            bbox_x1=bbox.get("x1"),
            bbox_y1=bbox.get("y1"),
            bbox_x2=bbox.get("x2"),
            bbox_y2=bbox.get("y2")
        )
    
    # OCR detections
    for ocr in evidence.get("ocr", []):
        result_repo.add_evidence(
            db_result.id,
            EvidenceType.OCR,
            text_content=ocr.get("text"),
            timestamp=ocr.get("timestamp"),
            confidence=ocr.get("confidence"),
            extra_data={"frame_index": ocr.get("frame_index")}
        )
    
    # Text moderation results
    for mod in evidence.get("transcript_moderation", []):
        result_repo.add_evidence(
            db_result.id,
            EvidenceType.MODERATION,
            start_time=mod.get("start_time"),
            end_time=mod.get("end_time"),
            text_content=mod.get("text"),
            extra_data={
                "profanity_score": mod.get("profanity_score"),
                "violence_score": mod.get("violence_score"),
                "sexual_score": mod.get("sexual_score"),
                "hate_score": mod.get("hate_score"),
                "drugs_score": mod.get("drugs_score"),
                "profanity_words": mod.get("profanity_words", [])
            }
        )
    
    # Archive checkpoint
    checkpoint_repo.archive(video_id, result)
    
    logger.info(f"Saved complete result for video: {video_id}")
    return db_result


def delete_video_complete(db: Session, video_id: str) -> bool:
    """
    Delete video, result, evidence, and files from MinIO.
    
    Args:
        db: Database session
        video_id: Video identifier
        
    Returns:
        True if deleted
    """
    video_repo = VideoRepository(db)
    storage = get_storage_service()
    
    # Delete files from MinIO
    try:
        storage.delete_video_files(video_id)
        logger.info(f"Deleted video files from MinIO: {video_id}")
    except Exception as e:
        logger.error(f"Failed to delete video files from MinIO: {e}")
    
    # Delete from database (cascades to results, evidence)
    return video_repo.delete(video_id)


def get_video_url(db: Session, video_id: str, labeled: bool = False) -> Optional[str]:
    """
    Get presigned URL for video access.
    
    Args:
        db: Database session
        video_id: Video identifier
        labeled: If True, get labeled video; otherwise original
        
    Returns:
        Presigned URL or None
    """
    storage = get_storage_service()
    
    if labeled:
        return storage.get_labeled_video_url(video_id)
    return storage.get_video_url(video_id)
