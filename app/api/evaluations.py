"""
Evaluation API - Consolidated evaluation endpoints.

This is the primary API for video evaluation:
- POST /v1/evaluate - Submit evaluation (single or batch)
- GET /v1/evaluations/{id} - Get evaluation status/results
- GET /v1/evaluations/{id}/events - SSE progress stream
- GET /v1/evaluations/{id}/stages - Stage outputs (debug)
- GET /v1/evaluations/{id}/artifacts/{type} - Get artifacts
"""
import os
import uuid
import asyncio
import tempfile
import shutil
from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse, FileResponse, Response

from app.core.logging import get_logger
from app.core.config import settings
from app.db.connection import get_db_session as get_session
from app.db.models import (
    Evaluation, EvaluationItem, EvaluationResult, EvaluationEvidence,
    EvaluationStatus as DBEvaluationStatus, Verdict as DBVerdict, Criteria
)
from app.evaluation.criteria import EvaluationCriteria, parse_criteria, CHILD_SAFETY_CRITERIA
from app.utils.storage import get_storage_service

# Import DTOs - single source of truth for API data structures
from app.api.schemas import (
    EvaluationDTO, EvaluationSummaryDTO, EvaluationItemDTO,
    EvaluationCreateResponse, EvaluationListResponse,
    EvaluationStatus, Verdict, ArtifactDTO, ProgressEventDTO
)

logger = get_logger("api.evaluations")

router = APIRouter(prefix="/v1", tags=["evaluations"])


# =============================================================================
# Evaluation Repository
# =============================================================================

class EvaluationRepository:
    """Repository for evaluation CRUD operations."""
    
    @staticmethod
    def create(
        criteria_id: Optional[str] = None,
        criteria_snapshot: Optional[Dict] = None,
        is_async: bool = True
    ) -> str:
        """Create a new evaluation. Returns evaluation ID."""
        eval_id = str(uuid.uuid4())[:8]
        with get_session() as session:
            evaluation = Evaluation(
                id=eval_id,
                criteria_id=criteria_id,
                criteria_snapshot=criteria_snapshot,
                is_async=is_async,
                status=EvaluationStatus.PENDING
            )
            session.add(evaluation)
            session.commit()
        return eval_id
    
    @staticmethod
    def get(evaluation_id: str) -> Optional[Evaluation]:
        """Get evaluation by ID."""
        with get_session() as session:
            return session.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
    
    @staticmethod
    def get_with_items(evaluation_id: str, include_items: bool = True) -> Optional[EvaluationDTO]:
        """Get evaluation with items as DTO (properly serialized while in session)."""
        with get_session() as session:
            evaluation = session.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
            if not evaluation:
                return None
            
            # Create DTO while still in session - this accesses all relationships
            return EvaluationDTO.from_db(evaluation, include_items=include_items)
    
    @staticmethod
    def update_status(
        evaluation_id: str,
        status: EvaluationStatus,
        progress: int = None,
        current_stage: str = None,
        error_message: str = None
    ) -> None:
        """Update evaluation status."""
        with get_session() as session:
            evaluation = session.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
            if evaluation:
                evaluation.status = status
                if progress is not None:
                    evaluation.progress = progress
                if current_stage:
                    evaluation.current_stage = current_stage
                if error_message:
                    evaluation.error_message = error_message
                if status == EvaluationStatus.PROCESSING and not evaluation.started_at:
                    evaluation.started_at = datetime.utcnow()
                if status in (EvaluationStatus.COMPLETED, EvaluationStatus.FAILED):
                    evaluation.completed_at = datetime.utcnow()
                session.commit()
    
    @staticmethod
    def add_item(
        evaluation_id: str,
        filename: str,
        source_type: str = "upload",
        source_path: str = None,
        item_id: str = None,
        uploaded_video_path: str = None
    ) -> str:
        """Add an item to an evaluation. Returns item ID."""
        if not item_id:
            item_id = str(uuid.uuid4())[:8]
        with get_session() as session:
            evaluation = session.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
            if not evaluation:
                raise ValueError(f"Evaluation {evaluation_id} not found")
            
            item = EvaluationItem(
                id=item_id,
                evaluation_id=evaluation_id,
                filename=filename,
                source_type=source_type,
                source_path=source_path,
                uploaded_video_path=uploaded_video_path,
                status=EvaluationStatus.PENDING
            )
            session.add(item)
            evaluation.items_total += 1
            session.commit()
        return item_id
    
    @staticmethod
    def update_item(
        item_id: str,
        **kwargs
    ) -> None:
        """Update an evaluation item."""
        with get_session() as session:
            item = session.query(EvaluationItem).filter(EvaluationItem.id == item_id).first()
            if item:
                for key, value in kwargs.items():
                    if hasattr(item, key):
                        setattr(item, key, value)
                session.commit()
    
    @staticmethod
    def update_item_stage(item_id: str, stage: str, progress: int) -> None:
        """Update item's current stage and progress."""
        with get_session() as session:
            item = session.query(EvaluationItem).filter(EvaluationItem.id == item_id).first()
            if item:
                item.current_stage = stage
                item.progress = progress
                session.commit()
    
    @staticmethod
    def update_evaluation_counts(evaluation_id: str) -> None:
        """Update evaluation's completed/failed item counts based on item statuses."""
        with get_session() as session:
            evaluation = session.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
            if not evaluation:
                return
            
            # Count items by status
            completed = 0
            failed = 0
            for item in evaluation.items:
                if item.status == EvaluationStatus.COMPLETED:
                    completed += 1
                elif item.status == EvaluationStatus.FAILED:
                    failed += 1
            
            evaluation.items_completed = completed
            evaluation.items_failed = failed
            
            # Update overall status if all items are done
            total = evaluation.items_total
            if total > 0 and (completed + failed) >= total:
                if failed > 0 and completed == 0:
                    evaluation.status = EvaluationStatus.FAILED
                elif failed > 0:
                    evaluation.status = EvaluationStatus.COMPLETED  # Partial success
                else:
                    evaluation.status = EvaluationStatus.COMPLETED
                evaluation.completed_at = datetime.utcnow()
                evaluation.progress = 100
            
            session.commit()
    
    @staticmethod
    def save_stage_output(item_id: str, stage_name: str, output: Dict) -> bool:
        """
        Save stage output for an evaluation item (PostgreSQL persistence).
        
        INDUSTRY STANDARD: Stage outputs are persisted immediately to PostgreSQL,
        not ephemeral storage like Redis. This ensures data survives container restarts.
        
        Args:
            item_id: Evaluation item ID
            stage_name: Name of the completed stage
            output: Dictionary with stage output data
            
        Returns:
            True if saved successfully, False otherwise
        """
        from sqlalchemy.orm.attributes import flag_modified
        
        if not item_id:
            logger.warning(f"save_stage_output called without item_id for stage {stage_name}")
            return False
        
        try:
            with get_session() as session:
                item = session.query(EvaluationItem).filter(EvaluationItem.id == item_id).first()
                if not item:
                    logger.warning(f"Cannot save stage output: item {item_id} not found")
                    return False
                
                # Initialize stage_outputs if None
                if item.stage_outputs is None:
                    item.stage_outputs = {}
                
                # Deep copy to ensure mutation is detected
                current_outputs = dict(item.stage_outputs) if item.stage_outputs else {}
                current_outputs[stage_name] = output
                item.stage_outputs = current_outputs
                
                # Flag JSON field as modified so SQLAlchemy detects the change
                flag_modified(item, 'stage_outputs')
                
                session.commit()
                logger.info(f"✓ Stage output '{stage_name}' persisted to PostgreSQL (item: {item_id})")
                return True
                
        except Exception as e:
            logger.error(f"Failed to save stage output for {item_id}/{stage_name}: {e}", exc_info=True)
            return False
    
    @staticmethod
    def get_stage_output(item_id: str, stage_name: str) -> Optional[Dict]:
        """Get output for a specific stage."""
        with get_session() as session:
            item = session.query(EvaluationItem).filter(EvaluationItem.id == item_id).first()
            if not item or not item.stage_outputs:
                return None
            return item.stage_outputs.get(stage_name)
    
    @staticmethod
    def get_all_stage_outputs(item_id: str) -> Dict[str, Dict]:
        """Get all stage outputs for an evaluation item."""
        with get_session() as session:
            item = session.query(EvaluationItem).filter(EvaluationItem.id == item_id).first()
            if not item:
                return {}
            return item.stage_outputs or {}
    
    @staticmethod
    def save_item_result(
        item_id: str,
        verdict: Verdict,
        confidence: float,
        criteria_scores: Dict,
        violations: List,
        processing_time: float = None,
        transcript: Dict = None,
        report: str = None
    ) -> EvaluationResult:
        """Save result for an evaluation item."""
        with get_session() as session:
            item = session.query(EvaluationItem).filter(EvaluationItem.id == item_id).first()
            if not item:
                raise ValueError(f"Item {item_id} not found")
            
            # Create or update result
            result = item.result
            if not result:
                result = EvaluationResult(item_id=item_id)
                session.add(result)
            
            result.verdict = verdict
            result.confidence = confidence
            result.criteria_scores = criteria_scores
            result.violations = violations
            result.processing_time = processing_time
            result.transcript = transcript
            result.report = report
            
            # Update item status
            item.status = EvaluationStatus.COMPLETED
            item.completed_at = datetime.utcnow()
            
            # Update evaluation counters
            evaluation = item.evaluation
            evaluation.items_completed += 1
            
            # Update overall verdict (worst case)
            if result.verdict == Verdict.UNSAFE:
                evaluation.overall_verdict = Verdict.UNSAFE
            elif result.verdict == Verdict.CAUTION and evaluation.overall_verdict != Verdict.UNSAFE:
                evaluation.overall_verdict = Verdict.CAUTION
            elif evaluation.overall_verdict is None:
                evaluation.overall_verdict = result.verdict
            
            # Check if evaluation is complete
            if evaluation.items_completed + evaluation.items_failed >= evaluation.items_total:
                evaluation.status = EvaluationStatus.COMPLETED
                evaluation.completed_at = datetime.utcnow()
                evaluation.progress = 100
            
            session.commit()
            session.refresh(result)
            return result
    
    @staticmethod
    def list_recent(limit: int = 50) -> List[EvaluationSummaryDTO]:
        """List recent evaluations as DTOs."""
        with get_session() as session:
            evaluations = session.query(Evaluation).order_by(
                Evaluation.created_at.desc()
            ).limit(limit).all()
            
            # Create DTOs while still in session
            return [EvaluationSummaryDTO.from_db(e) for e in evaluations]


# =============================================================================
# Background Processing
# =============================================================================

async def process_evaluation_item(
    evaluation_id: str,
    item_id: str,
    video_path: str,
    criteria: EvaluationCriteria,
    media_type: str = "video"  # "video" or "image"
) -> None:
    """Process a single evaluation item (video or image)."""
    from app.pipeline.graph import run_pipeline
    from app.api.sse import broadcast_progress
    
    logger.info(f"Processing {media_type} item {item_id} for evaluation {evaluation_id}")
    
    # Update item status
    EvaluationRepository.update_item(
        item_id,
        status=EvaluationStatus.PROCESSING,
        started_at=datetime.utcnow()
    )
    
    async def progress_callback(stage: str, message: str, progress: int):
        """Progress callback that updates DB and broadcasts SSE."""
        EvaluationRepository.update_item(item_id, current_stage=stage, progress=progress)
        # Broadcast to SSE using evaluation_id (not item_id)
        await broadcast_progress(
            evaluation_id,
            {"stage": stage, "message": message, "progress": progress, "item_id": item_id}
        )
    
    try:
        result = await run_pipeline(
            video_path=video_path,
            criteria=criteria,
            video_id=item_id,
            progress_callback=progress_callback,
            media_type=media_type,  # Pass media type to pipeline
        )
        
        # Save result - criteria comes directly from fusion node now
        EvaluationRepository.save_item_result(
            item_id=item_id,
            verdict=Verdict(result.get("verdict", "NEEDS_REVIEW")),
            confidence=result.get("confidence", 0.0),
            criteria_scores=result.get("criteria", {}),
            violations=result.get("violations", []),
            processing_time=result.get("timings", {}).get("total_seconds"),
            transcript=result.get("transcript"),
            report=result.get("report")
        )
        
        # Update labeled video path in database
        # Note: The labeled video is now uploaded during yolo26_vision stage for early access
        logger.info(f"Checking for labeled_video_path in result: {result.get('labeled_video_path')}")
        if result.get("labeled_video_path"):
            labeled_path = result["labeled_video_path"]
            storage = get_storage_service()
            
            # Check if already uploaded to MinIO (path starts with labeled/ prefix)
            if labeled_path.startswith(storage.LABELED_PREFIX):
                # Already in MinIO, just update the database
                EvaluationRepository.update_item(item_id, labeled_video_path=labeled_path)
                logger.info(f"Labeled video saved to DB: {labeled_path}")
            elif Path(labeled_path).exists():
                # Local path - upload to MinIO (fallback for older code paths)
                try:
                    minio_path = storage.upload_labeled_video(labeled_path, item_id)
                    EvaluationRepository.update_item(item_id, labeled_video_path=minio_path)
                    logger.info(f"Uploaded labeled video to MinIO: {minio_path}")
                except Exception as e:
                    logger.warning(f"Failed to upload labeled video to MinIO: {e}")
                    EvaluationRepository.update_item(item_id, labeled_video_path=labeled_path)
        
        # Send completion event
        asyncio.create_task(broadcast_progress(
            evaluation_id,
            {"stage": "complete", "message": "Analysis complete", "progress": 100, "item_id": item_id}
        ))
        
        logger.info(f"Item {item_id} completed: {result.get('verdict')}")
        
    except Exception as e:
        logger.error(f"Item {item_id} failed: {e}")
        EvaluationRepository.update_item(
            item_id,
            status=EvaluationStatus.FAILED,
            error_message=str(e)
        )
        # Update evaluation failed count
        with get_session() as session:
            evaluation = session.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
            if evaluation:
                evaluation.items_failed += 1
                if evaluation.items_completed + evaluation.items_failed >= evaluation.items_total:
                    evaluation.status = EvaluationStatus.COMPLETED
                    evaluation.completed_at = datetime.utcnow()
                session.commit()


async def process_evaluation(evaluation_id: str, items_data: List[Dict]) -> None:
    """Process all items in an evaluation."""
    logger.info(f"Starting evaluation {evaluation_id} with {len(items_data)} items")
    
    # Update evaluation status
    EvaluationRepository.update_status(evaluation_id, EvaluationStatus.PROCESSING)
    
    # Get criteria from evaluation snapshot (always stored on creation)
    with get_session() as session:
        evaluation = session.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
        criteria_config = evaluation.criteria_snapshot
        
        # Fallback: load from criteria_id if snapshot missing
        if not criteria_config and evaluation.criteria_id:
            db_criteria = session.query(Criteria).filter(Criteria.id == evaluation.criteria_id).first()
            if db_criteria:
                criteria_config = db_criteria.config
    
    if criteria_config:
        criteria = parse_criteria(criteria_config)
    else:
        # Last resort: use default
        criteria = CHILD_SAFETY_CRITERIA
        logger.warning(f"Using default criteria for evaluation {evaluation_id}")
    
    # Process items sequentially (to avoid OOM)
    for item_data in items_data:
        await process_evaluation_item(
            evaluation_id=evaluation_id,
            item_id=item_data["item_id"],
            video_path=item_data["video_path"],
            criteria=criteria,
            media_type=item_data.get("media_type", "video"),
        )
    
    logger.info(f"Evaluation {evaluation_id} complete")


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/evaluate", response_model=EvaluationDTO)
async def create_evaluation(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(None),
    criteria_id: Optional[str] = Form(None),
    criteria: Optional[str] = Form(None),
    async_mode: bool = Form(True, alias="async"),
    source_type: str = Form("upload"),
    urls: Optional[str] = Form(None),
):
    """
    Submit a video evaluation request.
    
    Supports:
    - Single or batch file uploads
    - URL-based imports
    - Custom or preset criteria
    - Sync or async processing
    
    Returns evaluation ID for tracking.
    """
    # Parse criteria
    criteria_snapshot = None
    resolved_criteria_id = None
    
    logger.info(f"Received evaluation request - criteria_id={criteria_id}, criteria={criteria is not None}")
    
    if criteria:
        # Inline criteria provided
        import json
        try:
            criteria_snapshot = json.loads(criteria)
        except json.JSONDecodeError:
            import yaml
            criteria_snapshot = yaml.safe_load(criteria)
        logger.info(f"Using inline criteria: {criteria_snapshot.get('name', 'unnamed')}")
    elif criteria_id:
        # Load from database (presets are seeded on startup)
        with get_session() as session:
            saved = session.query(Criteria).filter(Criteria.id == criteria_id).first()
            if not saved:
                raise HTTPException(404, f"Criteria '{criteria_id}' not found")
            criteria_snapshot = saved.config
            resolved_criteria_id = criteria_id
            logger.info(f"Loaded criteria from DB: {criteria_id} -> {criteria_snapshot.get('name', 'unnamed')}")
    else:
        # Default to child_safety
        with get_session() as session:
            default = session.query(Criteria).filter(Criteria.id == "child_safety").first()
            if default:
                criteria_snapshot = default.config
                resolved_criteria_id = "child_safety"
        logger.info(f"No criteria specified, using default: child_safety")
    
    # Create evaluation
    evaluation_id = EvaluationRepository.create(
        criteria_id=resolved_criteria_id or criteria_id,
        criteria_snapshot=criteria_snapshot,
        is_async=async_mode
    )
    
    items_data = []
    
    # Handle file uploads (video and image)
    storage = get_storage_service()
    
    # Import media utilities
    from app.utils.media import detect_media_type, MediaType, get_all_supported_extensions
    
    if files:
        for file in files:
            if not file.filename:
                continue
            
            # Save to temp file
            temp_dir = Path(tempfile.mkdtemp())
            temp_path = temp_dir / file.filename
            with open(temp_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            
            # Detect media type (video or image)
            media_type = detect_media_type(str(temp_path))
            if media_type == MediaType.UNKNOWN:
                logger.warning(f"Unsupported file type: {file.filename}")
                continue
            
            # Generate item ID first
            item_id = str(uuid.uuid4())[:8]
            
            # Upload original media to MinIO
            uploaded_path = None
            try:
                uploaded_path = storage.upload_video(str(temp_path), item_id)
                logger.info(f"Uploaded {media_type.value} to MinIO: {uploaded_path}")
            except Exception as e:
                logger.warning(f"Failed to upload {media_type.value} to MinIO: {e}")
            
            # Add item with uploaded path
            EvaluationRepository.add_item(
                evaluation_id=evaluation_id,
                item_id=item_id,
                filename=file.filename,
                source_type="upload",
                uploaded_video_path=uploaded_path
            )
            
            items_data.append({
                "item_id": item_id,
                "video_path": str(temp_path),  # Legacy name for backward compatibility
                "media_path": str(temp_path),  # New unified name
                "media_type": media_type.value,
            })
    
    # Handle URL imports
    elif urls:
        url_list = urls.split(",") if "," in urls else [urls]
        for url in url_list:
            url = url.strip()
            if not url:
                continue
            
            filename = url.split("/")[-1].split("?")[0] or "video.mp4"
            item_id = EvaluationRepository.add_item(
                evaluation_id=evaluation_id,
                filename=filename,
                source_type="url",
                source_path=url
            )
            
            items_data.append({
                "item_id": item_id,
                "video_path": url  # Pipeline handles URL download
            })
    
    if not items_data:
        raise HTTPException(400, "No files or URLs provided")
    
    # Start processing
    if async_mode:
        background_tasks.add_task(process_evaluation, evaluation_id, items_data)
    else:
        # Sync mode - process and return results
        await process_evaluation(evaluation_id, items_data)
    
    # Load evaluation for response (DTO properly serialized)
    # Always include items so frontend can map SSE updates to queue items
    evaluation = EvaluationRepository.get_with_items(evaluation_id, include_items=True)
    if not evaluation:
        raise HTTPException(500, "Failed to load created evaluation")
    
    return evaluation


# =============================================================================
# Recovery Endpoints - MUST be before parameterized routes!
# =============================================================================

@router.get("/evaluations/stuck")
async def list_stuck_evaluations():
    """
    List all evaluations that appear stuck (PROCESSING status for too long).
    
    Useful for monitoring. Use POST /evaluations/{id}/reprocess to resume.
    """
    from datetime import datetime, timedelta
    
    stuck_threshold = timedelta(minutes=10)  # Industry standard: catch stuck faster
    cutoff = datetime.utcnow() - stuck_threshold
    
    with get_session() as session:
        stuck = session.query(Evaluation).filter(
            Evaluation.status == DBEvaluationStatus.PROCESSING,
            Evaluation.started_at < cutoff
        ).all()
        
        return {
            "stuck_count": len(stuck),
            "stuck_evaluations": [
                {
                    "id": e.id,
                    "status": e.status.value,
                    "started_at": e.started_at.isoformat() if e.started_at else None,
                    "current_stage": e.current_stage,
                    "items_completed": e.items_completed,
                    "items_total": e.items_total,
                    "error_message": e.error_message,
                    "recovery_hint": f"POST /v1/evaluations/{e.id}/reprocess"
                }
                for e in stuck
            ]
        }


@router.post("/evaluations/recover-all")
async def recover_all_stuck_evaluations_endpoint(background_tasks: BackgroundTasks):
    """
    Trigger recovery for ALL stuck evaluations.
    
    This is equivalent to what happens automatically on container restart.
    Uses existing reprocess infrastructure (no redundant code).
    """
    from app.pipeline.recovery import recover_all_stuck_evaluations
    
    async def do_recovery():
        try:
            result = await recover_all_stuck_evaluations()
            logger.info(f"Bulk recovery complete: {result}")
        except Exception as e:
            logger.error(f"Bulk recovery failed: {e}")
    
    background_tasks.add_task(do_recovery)
    
    return {
        "status": "recovery_started",
        "message": "Recovery of all stuck evaluations initiated in background"
    }


# =============================================================================
# Parameterized routes (MUST be after static routes like /stuck)
# =============================================================================

@router.get("/evaluations/{evaluation_id}", response_model=EvaluationDTO)
async def get_evaluation(evaluation_id: str, include_items: bool = Query(True)):
    """
    Get evaluation status and results.
    """
    evaluation = EvaluationRepository.get_with_items(evaluation_id, include_items=include_items)
    if not evaluation:
        raise HTTPException(404, f"Evaluation {evaluation_id} not found")
    
    return evaluation


@router.get("/evaluations/{evaluation_id}/events")
async def evaluation_events(evaluation_id: str):
    """
    SSE stream for evaluation progress events.
    """
    from app.api.sse import create_sse_response
    
    evaluation = EvaluationRepository.get(evaluation_id)
    if not evaluation:
        raise HTTPException(404, f"Evaluation {evaluation_id} not found")
    
    return create_sse_response(evaluation_id)


@router.get("/evaluations/{evaluation_id}/stages")
async def get_evaluation_stages(evaluation_id: str, item_id: Optional[str] = None):
    """
    Get stage outputs for debugging.
    """
    evaluation = EvaluationRepository.get_with_items(evaluation_id)
    if not evaluation:
        raise HTTPException(404, f"Evaluation {evaluation_id} not found")
    
    stages = {}
    for item in evaluation.items:
        if item_id and item.id != item_id:
            continue
        stages[item.id] = {
            "filename": item.filename,
            "status": item.status.value,
            "stage_outputs": item.stage_outputs or {}
        }
    
    return {"evaluation_id": evaluation_id, "items": stages}


@router.get("/evaluations/{evaluation_id}/stages/{stage_name}")
async def get_evaluation_stage(evaluation_id: str, stage_name: str, item_id: Optional[str] = None):
    """
    Get specific stage output.
    """
    evaluation = EvaluationRepository.get_with_items(evaluation_id)
    if not evaluation:
        raise HTTPException(404, f"Evaluation {evaluation_id} not found")
    
    results = {}
    for item in evaluation.items:
        if item_id and item.id != item_id:
            continue
        outputs = item.stage_outputs or {}
        if stage_name in outputs:
            results[item.id] = outputs[stage_name]
    
    if not results:
        raise HTTPException(404, f"Stage {stage_name} not found")
    
    return {"evaluation_id": evaluation_id, "stage": stage_name, "outputs": results}


@router.get("/evaluations/{evaluation_id}/artifacts/{artifact_type}")
async def get_evaluation_artifact(
    evaluation_id: str,
    artifact_type: str,
    item_id: Optional[str] = None,
    stream: bool = Query(False, description="Stream content directly instead of returning URL")
):
    """
    Get evaluation artifacts (videos, thumbnails, reports).
    
    - If stream=false (default): Returns presigned URL metadata
    - If stream=true: Streams the content directly (recommended for browsers)
    """
    evaluation = EvaluationRepository.get_with_items(evaluation_id)
    if not evaluation:
        raise HTTPException(404, f"Evaluation {evaluation_id} not found")
    
    # Find item - evaluation.items is now List[EvaluationItemDTO]
    item: Optional[EvaluationItemDTO] = None
    if item_id:
        item = next((i for i in evaluation.items if i.id == item_id), None)
    elif len(evaluation.items) == 1:
        item = evaluation.items[0]
    
    if not item:
        raise HTTPException(400, "item_id required for multi-item evaluations")
    
    # Get artifact path and determine content type
    path = None
    content_type = "application/octet-stream"
    
    # Helper to detect content type from path
    def get_content_type(file_path: str) -> str:
        ext = Path(file_path).suffix.lower()
        content_types = {
            ".mp4": "video/mp4", ".avi": "video/x-msvideo", ".mov": "video/quicktime",
            ".mkv": "video/x-matroska", ".webm": "video/webm",
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
        }
        return content_types.get(ext, "application/octet-stream")
    
    if artifact_type == "labeled_video":
        path = item.labeled_video_path
        content_type = get_content_type(path) if path else "video/mp4"
    elif artifact_type == "uploaded_video":
        path = item.uploaded_video_path
        # Auto-detect content type (could be video or image)
        content_type = get_content_type(path) if path else "video/mp4"
    elif artifact_type == "thumbnail":
        path = item.thumbnail_path
        content_type = "image/jpeg"
    elif artifact_type == "report" and item.result:
        return Response(
            content=item.result.report or "No report generated",
            media_type="text/plain"
        )
    
    if not path:
        raise HTTPException(404, f"Artifact {artifact_type} not found")
    
    storage = get_storage_service()
    
    # Get file extension for Content-Disposition
    file_ext = Path(path).suffix or ".mp4"
    
    # Stream content directly (recommended for browsers)
    if stream:
        try:
            # Get content from MinIO and stream to client
            content = storage.get_bytes(path)
            return Response(
                content=content,
                media_type=content_type,
                headers={
                    "Content-Disposition": f'inline; filename="{artifact_type}_{item.id}{file_ext}"',
                    "Cache-Control": "max-age=3600"
                }
            )
        except Exception as e:
            raise HTTPException(500, f"Failed to stream artifact: {e}")
    
    # Return URL metadata (for backward compatibility)
    try:
        url = storage.get_presigned_url(path)
        return ArtifactDTO(url=url, artifact_type=artifact_type, item_id=item.id)
    except Exception as e:
        raise HTTPException(500, f"Failed to get artifact: {e}")


@router.get("/evaluations/{evaluation_id}/frames")
async def list_frames(
    evaluation_id: str,
    item_id: Optional[str] = None,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    thumbnails: bool = Query(True, description="Return thumbnail URLs (faster for filmstrip)")
):
    """
    List processed frames (keyframes extracted during segmentation).
    
    Industry standard pagination:
    - page: 1-indexed page number
    - page_size: max 200 items per page
    - thumbnails: if true, returns small thumbnail URLs; if false, returns full-size frame URLs
    
    Returns paginated frame metadata with URLs for streaming.
    """
    evaluation = EvaluationRepository.get_with_items(evaluation_id)
    if not evaluation:
        raise HTTPException(404, f"Evaluation {evaluation_id} not found")
    
    # Find item
    item: Optional[EvaluationItemDTO] = None
    if item_id:
        item = next((i for i in evaluation.items if i.id == item_id), None)
    elif len(evaluation.items) == 1:
        item = evaluation.items[0]
    
    if not item:
        raise HTTPException(400, "item_id required for multi-item evaluations")
    
    storage = get_storage_service()
    
    # List frames or thumbnails from storage
    try:
        if thumbnails:
            # Use thumbnails for filmstrip (faster, smaller)
            frame_objects = storage.list_frame_thumbnails(item.id)
            prefix = "thumb_"
            url_type = "thumbnails"
        else:
            # Use full-size keyframes
            frame_objects = storage.list_frames(item.id)
            prefix = "frame_"
            url_type = "frames"
        
        all_frames = []
        for obj_path in frame_objects:
            # Parse frame info from filename: frame_{index}_{timestamp_ms}.jpg or thumb_{index}_{timestamp_ms}.jpg
            filename = Path(obj_path).stem
            parts = filename.split('_')
            
            frame_index = int(parts[1]) if len(parts) > 1 else 0
            timestamp_ms = int(parts[2]) if len(parts) > 2 else 0
            timestamp = timestamp_ms / 1000.0
            
            all_frames.append({
                "id": filename,
                "index": frame_index,
                "timestamp": timestamp,
                "thumbnail_url": f"/v1/evaluations/{evaluation_id}/{url_type}/{filename}?item_id={item.id}&stream=true",
                # Also provide full-size URL for click-to-expand
                "full_url": f"/v1/evaluations/{evaluation_id}/frames/frame_{parts[1]}_{parts[2]}?item_id={item.id}&stream=true" if thumbnails else None,
            })
        
        # Sort by index
        all_frames.sort(key=lambda x: x["index"])
        total = len(all_frames)
        
        # Paginate
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_frames = all_frames[start_idx:end_idx]
        
        return {
            "evaluation_id": evaluation_id,
            "item_id": item.id,
            "frames": paginated_frames,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total > 0 else 1
        }
        
    except Exception as e:
        logger.error(f"Failed to list frames: {e}")
        return {"evaluation_id": evaluation_id, "item_id": item.id, "frames": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 1}


@router.get("/evaluations/{evaluation_id}/frames/{filename}")
async def get_frame(
    evaluation_id: str,
    filename: str,
    item_id: Optional[str] = None,
    stream: bool = Query(True, description="Stream content directly")
):
    """
    Get a specific frame image.
    
    - stream=true: Returns the image content directly (default, recommended)
    - stream=false: Returns presigned URL metadata
    """
    evaluation = EvaluationRepository.get_with_items(evaluation_id)
    if not evaluation:
        raise HTTPException(404, f"Evaluation {evaluation_id} not found")
    
    # Find item
    item: Optional[EvaluationItemDTO] = None
    if item_id:
        item = next((i for i in evaluation.items if i.id == item_id), None)
    elif len(evaluation.items) == 1:
        item = evaluation.items[0]
    
    if not item:
        raise HTTPException(400, "item_id required for multi-item evaluations")
    
    storage = get_storage_service()
    
    # Build object path
    object_path = f"{storage.FRAMES_PREFIX}{item.id}/{filename}.jpg"
    
    if not storage.object_exists(object_path):
        raise HTTPException(404, f"Frame not found: {filename}")
    
    if stream:
        try:
            content = storage.get_bytes(object_path)
            return Response(
                content=content,
                media_type="image/jpeg",
                headers={
                    "Content-Disposition": f'inline; filename="{filename}.jpg"',
                    "Cache-Control": "max-age=86400"  # Cache for 24 hours
                }
            )
        except Exception as e:
            raise HTTPException(500, f"Failed to stream frame: {e}")
    
    # Return URL metadata
    try:
        url = storage.get_presigned_url(object_path)
        return {"url": url, "filename": filename}
    except Exception as e:
        raise HTTPException(500, f"Failed to get frame URL: {e}")


@router.get("/evaluations/{evaluation_id}/thumbnails/{filename}")
async def get_thumbnail(
    evaluation_id: str,
    filename: str,
    item_id: Optional[str] = None,
    stream: bool = Query(True, description="Stream content directly")
):
    """
    Get a thumbnail image (small, optimized for filmstrip display).
    
    - stream=true: Returns the image content directly (default, recommended)
    - stream=false: Returns presigned URL metadata
    """
    evaluation = EvaluationRepository.get_with_items(evaluation_id)
    if not evaluation:
        raise HTTPException(404, f"Evaluation {evaluation_id} not found")
    
    # Find item
    item: Optional[EvaluationItemDTO] = None
    if item_id:
        item = next((i for i in evaluation.items if i.id == item_id), None)
    elif len(evaluation.items) == 1:
        item = evaluation.items[0]
    
    if not item:
        raise HTTPException(400, "item_id required for multi-item evaluations")
    
    storage = get_storage_service()
    
    # Build object path for thumbnail
    object_path = f"{storage.FRAME_THUMBS_PREFIX}{item.id}/{filename}.jpg"
    
    if not storage.object_exists(object_path):
        raise HTTPException(404, f"Thumbnail not found: {filename}")
    
    if stream:
        try:
            content = storage.get_bytes(object_path)
            return Response(
                content=content,
                media_type="image/jpeg",
                headers={
                    "Content-Disposition": f'inline; filename="{filename}.jpg"',
                    "Cache-Control": "max-age=86400"  # Cache for 24 hours (thumbnails rarely change)
                }
            )
        except Exception as e:
            raise HTTPException(500, f"Failed to stream thumbnail: {e}")
    
    # Return URL metadata
    try:
        url = storage.get_presigned_url(object_path)
        return {"url": url, "filename": filename}
    except Exception as e:
        raise HTTPException(500, f"Failed to get thumbnail URL: {e}")


@router.get("/evaluations", response_model=EvaluationListResponse)
async def list_evaluations(
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = None
):
    """
    List recent evaluations.
    """
    evaluations = EvaluationRepository.list_recent(limit)
    
    # Filter by status if provided
    if status:
        evaluations = [e for e in evaluations if e.status.value == status]
    
    return EvaluationListResponse(evaluations=evaluations, total=len(evaluations))


@router.delete("/evaluations/{evaluation_id}")
async def delete_evaluation(evaluation_id: str):
    """
    Delete an evaluation and all its data.
    """
    with get_session() as session:
        evaluation = session.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
        if not evaluation:
            raise HTTPException(404, f"Evaluation {evaluation_id} not found")
        
        # Delete artifacts from storage
        for item in evaluation.items:
            for path in [item.uploaded_video_path, item.labeled_video_path, item.thumbnail_path]:
                if path:
                    try:
                        get_storage_service().delete_object(path)
                    except Exception:
                        pass
        
        session.delete(evaluation)
        session.commit()
    
    return {"status": "deleted", "evaluation_id": evaluation_id}


@router.post("/evaluations/{evaluation_id}/reprocess")
async def reprocess_evaluation(
    evaluation_id: str,
    background_tasks: BackgroundTasks,
    skip_early_stages: bool = Query(True, description="Skip ingest/segment if data already exists"),
):
    """
    Reprocess an evaluation with current stage settings.
    
    This allows re-running the analysis pipeline after enabling/disabling stages.
    If skip_early_stages=True (default), skips ingest and segment stages if the
    video data and frames are already available.
    
    Returns updated evaluation status.
    """
    # Use raw DB query so we can access criteria_snapshot
    # Extract all needed data while in session to avoid DetachedInstanceError
    with get_session() as session:
        evaluation = session.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
        if not evaluation:
            raise HTTPException(404, f"Evaluation {evaluation_id} not found")
        
        if not evaluation.items:
            raise HTTPException(400, "Evaluation has no items to reprocess")
        
        # Capture criteria snapshot while in session
        criteria_snapshot = evaluation.criteria_snapshot
        
        # Extract item data as plain dicts while in session
        item_info_list = [
            {"id": item.id, "uploaded_video_path": item.uploaded_video_path}
            for item in evaluation.items
        ]
    
    # Reset evaluation status
    EvaluationRepository.update_status(
        evaluation_id,
        EvaluationStatus.PROCESSING,
        progress=0,
        current_stage="reprocessing"
    )
    
    # Prepare items for reprocessing
    items_data = []
    storage = get_storage_service()
    
    for item_info in item_info_list:
        item_id = item_info["id"]
        uploaded_path = item_info["uploaded_video_path"]
        
        # Reset item status and clear stage outputs for stages that will be rerun
        with get_session() as session:
            db_item = session.query(EvaluationItem).filter(EvaluationItem.id == item_id).first()
            if db_item:
                db_item.status = DBEvaluationStatus.PROCESSING
                db_item.progress = 0
                db_item.current_stage = "reprocessing"
                
                # Keep ingest and segment stage outputs, clear everything else
                existing_outputs = db_item.stage_outputs or {}
                preserved_outputs = {}
                for stage_key in ["ingest", "segment", "ingest_video", "segment_video"]:
                    if stage_key in existing_outputs:
                        preserved_outputs[stage_key] = existing_outputs[stage_key]
                db_item.stage_outputs = preserved_outputs
                
                # Clear result for re-scoring
                if db_item.result:
                    session.delete(db_item.result)
                session.commit()
                
                logger.info(f"Cleared stage outputs for reprocessing, preserved: {list(preserved_outputs.keys())}")
        
        # Get video path - try uploaded video from MinIO first
        video_path = None
        if uploaded_path:
            # Download from MinIO to temp file for reprocessing
            try:
                temp_dir = Path(tempfile.mkdtemp())
                temp_path = temp_dir / f"{item_id}.mp4"
                storage.download_file(uploaded_path, str(temp_path))
                video_path = str(temp_path)
                logger.info(f"Downloaded video from MinIO for reprocessing: {video_path}")
            except Exception as e:
                logger.warning(f"Could not download video from MinIO: {e}")
        
        if not video_path:
            raise HTTPException(400, f"Video file not available for item {item_id}")
        
        items_data.append({
            "item_id": item_id,
            "video_path": video_path,
            "resume_from_checkpoint": skip_early_stages,  # Use checkpoint if skipping early stages
        })
    
    # Start reprocessing in background
    async def reprocess_items():
        from app.evaluation.criteria import parse_criteria, CHILD_SAFETY_CRITERIA
        
        # Get criteria from captured snapshot
        if criteria_snapshot:
            criteria = parse_criteria(criteria_snapshot)
        else:
            criteria = CHILD_SAFETY_CRITERIA
        
        for item_data in items_data:
            await reprocess_evaluation_item(
                evaluation_id=evaluation_id,
                item_id=item_data["item_id"],
                video_path=item_data["video_path"],
                criteria=criteria,
                resume_from_checkpoint=item_data.get("resume_from_checkpoint", True),
            )
        
        logger.info(f"Reprocessing of evaluation {evaluation_id} complete")
    
    background_tasks.add_task(reprocess_items)
    
    return {
        "status": "reprocessing",
        "evaluation_id": evaluation_id,
        "items_count": len(items_data),
        "skip_early_stages": skip_early_stages,
    }


async def reprocess_evaluation_item(
    evaluation_id: str,
    item_id: str,
    video_path: str,
    criteria,
    resume_from_checkpoint: bool = True,
):
    """
    Reprocess a single evaluation item.
    
    Skips ingest and segment stages if data already exists,
    re-runs all analysis stages (yolo26, yoloworld, violence, whisper, ocr, etc.)
    """
    from app.pipeline.graph import run_pipeline
    from app.api.sse import sse_manager
    
    logger.info(f"Reprocessing item {item_id} (skip_early_stages={resume_from_checkpoint})")
    
    try:
        # Get existing item data to preserve ingest/segment outputs
        existing_state = {}
        with get_session() as session:
            db_item = session.query(EvaluationItem).filter(EvaluationItem.id == item_id).first()
            if db_item:
                # Load metadata from existing item
                existing_state = {
                    "duration": db_item.duration,
                    "fps": db_item.fps,
                    "width": db_item.width,
                    "height": db_item.height,
                    "has_audio": db_item.has_audio,
                    "uploaded_video_path": db_item.uploaded_video_path,
                    "labeled_video_path": db_item.labeled_video_path,
                    "thumbnail_path": db_item.thumbnail_path,
                }
                # Load preserved stage outputs (ingest/segment)
                if db_item.stage_outputs:
                    for key, value in db_item.stage_outputs.items():
                        existing_state[f"stage_output_{key}"] = value
                
                logger.info(f"Loaded existing item data: duration={db_item.duration}, fps={db_item.fps}, has_audio={db_item.has_audio}")
        
        # Progress callback
        async def progress_callback(stage: str, message: str, progress: int):
            EvaluationRepository.update_item_stage(item_id, stage, progress)
            await sse_manager.send_progress(evaluation_id, stage, message, progress)
        
        # Run pipeline - it will skip ingest/segment if data exists
        result = await run_pipeline(
            video_path=video_path,
            criteria=criteria,
            video_id=item_id,
            progress_callback=progress_callback,
            resume_from_checkpoint=resume_from_checkpoint,
            existing_state=existing_state,  # Pass existing data
        )
        
        # Save result
        verdict = result.get("verdict", "NEEDS_REVIEW")
        confidence = result.get("confidence", 0.0)
        
        with get_session() as session:
            item = session.query(EvaluationItem).filter(EvaluationItem.id == item_id).first()
            if item:
                item.status = DBEvaluationStatus.COMPLETED
                item.progress = 100
                item.current_stage = None
                # NOTE: Don't overwrite stage_outputs - they were saved incrementally during pipeline execution
                # item.stage_outputs = result.get("stage_outputs", {})  # REMOVED - was wiping saved outputs
                
                # Create new result
                db_result = EvaluationResult(
                    item_id=item_id,
                    verdict=DBVerdict(verdict),
                    confidence=confidence,
                    criteria_scores=result.get("criteria_scores", {}),
                    violations=result.get("violations", []),
                    processing_time=result.get("processing_time"),
                    transcript=result.get("transcript"),
                    report=result.get("report"),
                )
                session.add(db_result)
                session.commit()
        
        # Update evaluation status
        EvaluationRepository.update_evaluation_counts(evaluation_id)
        
        logger.info(f"Item {item_id} reprocessed: verdict={verdict}")
        
    except Exception as e:
        logger.error(f"Failed to reprocess item {item_id}: {e}", exc_info=True)
        
        with get_session() as session:
            item = session.query(EvaluationItem).filter(EvaluationItem.id == item_id).first()
            if item:
                item.status = DBEvaluationStatus.FAILED
                item.error_message = str(e)
                session.commit()
        
        EvaluationRepository.update_evaluation_counts(evaluation_id)


