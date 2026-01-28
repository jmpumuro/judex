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
    def save_stage_output(item_id: str, stage_name: str, output: Dict) -> bool:
        """
        Save stage output for an evaluation item.
        This is called after each stage completes to store its results.
        
        Args:
            item_id: Evaluation item ID
            stage_name: Name of the completed stage
            output: Dictionary with stage output data
            
        Returns:
            True if saved successfully, False otherwise
        """
        from sqlalchemy.orm.attributes import flag_modified
        
        with get_session() as session:
            item = session.query(EvaluationItem).filter(EvaluationItem.id == item_id).first()
            if not item:
                logger.warning(f"Cannot save stage output: item {item_id} not found")
                return False
            
            # Initialize stage_outputs if None
            if item.stage_outputs is None:
                item.stage_outputs = {}
            
            # Merge new stage output
            current_outputs = item.stage_outputs or {}
            current_outputs[stage_name] = output
            item.stage_outputs = current_outputs
            
            # Flag JSON field as modified so SQLAlchemy detects the change
            flag_modified(item, 'stage_outputs')
            
            session.commit()
            logger.debug(f"Saved stage output '{stage_name}' for item {item_id}")
            return True
    
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
    criteria: EvaluationCriteria
) -> None:
    """Process a single evaluation item."""
    from app.pipeline.generic_graph import run_generic_pipeline
    from app.api.sse import broadcast_progress
    
    logger.info(f"Processing item {item_id} for evaluation {evaluation_id}")
    
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
        result = await run_generic_pipeline(
            video_path=video_path,
            criteria=criteria,
            video_id=item_id,
            progress_callback=progress_callback
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
        
        # Upload labeled video to MinIO and update artifacts
        if result.get("labeled_video_path"):
            local_labeled_path = result["labeled_video_path"]
            if Path(local_labeled_path).exists():
                try:
                    storage = get_storage_service()
                    minio_path = storage.upload_labeled_video(local_labeled_path, item_id)
                    EvaluationRepository.update_item(
                        item_id,
                        labeled_video_path=minio_path
                    )
                    logger.info(f"Uploaded labeled video to MinIO: {minio_path}")
                except Exception as e:
                    logger.warning(f"Failed to upload labeled video to MinIO: {e}")
                    # Still save the local path as fallback
                    EvaluationRepository.update_item(
                        item_id,
                        labeled_video_path=local_labeled_path
                    )
        
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
            criteria=criteria
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
    
    if criteria:
        # Inline criteria provided
        import json
        try:
            criteria_snapshot = json.loads(criteria)
        except json.JSONDecodeError:
            import yaml
            criteria_snapshot = yaml.safe_load(criteria)
    elif criteria_id:
        # Load from database (presets are seeded on startup)
        with get_session() as session:
            saved = session.query(Criteria).filter(Criteria.id == criteria_id).first()
            if not saved:
                raise HTTPException(404, f"Criteria '{criteria_id}' not found")
            criteria_snapshot = saved.config
            resolved_criteria_id = criteria_id
    else:
        # Default to child_safety
        with get_session() as session:
            default = session.query(Criteria).filter(Criteria.id == "child_safety").first()
            if default:
                criteria_snapshot = default.config
                resolved_criteria_id = "child_safety"
    
    # Create evaluation
    evaluation_id = EvaluationRepository.create(
        criteria_id=resolved_criteria_id or criteria_id,
        criteria_snapshot=criteria_snapshot,
        is_async=async_mode
    )
    
    items_data = []
    
    # Handle file uploads
    storage = get_storage_service()
    
    if files:
        for file in files:
            if not file.filename:
                continue
            
            # Save to temp file
            temp_dir = Path(tempfile.mkdtemp())
            temp_path = temp_dir / file.filename
            with open(temp_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            
            # Generate item ID first
            item_id = str(uuid.uuid4())[:8]
            
            # Upload original video to MinIO
            uploaded_path = None
            try:
                uploaded_path = storage.upload_video(str(temp_path), item_id)
                logger.info(f"Uploaded video to MinIO: {uploaded_path}")
            except Exception as e:
                logger.warning(f"Failed to upload video to MinIO: {e}")
            
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
                "video_path": str(temp_path)
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


@router.get("/evaluations/{evaluation_id}/artifacts/{artifact_type}", response_model=ArtifactDTO)
async def get_evaluation_artifact(
    evaluation_id: str,
    artifact_type: str,
    item_id: Optional[str] = None
):
    """
    Get evaluation artifacts (videos, thumbnails, reports).
    
    Returns presigned URL or redirect to storage.
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
    
    # Get artifact path
    path = None
    if artifact_type == "labeled_video":
        path = item.labeled_video_path
    elif artifact_type == "uploaded_video":
        path = item.uploaded_video_path
    elif artifact_type == "thumbnail":
        path = item.thumbnail_path
    elif artifact_type == "report" and item.result:
        return Response(
            content=item.result.report or "No report generated",
            media_type="text/plain"
        )
    
    if not path:
        raise HTTPException(404, f"Artifact {artifact_type} not found")
    
    # Get presigned URL
    try:
        url = get_storage_service().get_presigned_url(path)
        return ArtifactDTO(url=url, artifact_type=artifact_type, item_id=item.id)
    except Exception as e:
        raise HTTPException(500, f"Failed to get artifact: {e}")


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
