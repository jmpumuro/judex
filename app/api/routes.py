"""
FastAPI routes for SafeVid service.
"""
import json
import tempfile
import zipfile
import uuid
import asyncio
import shutil
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from app.api.schemas import (
    VideoEvaluationResponse,
    HealthResponse,
    ModelsListResponse,
    ModelInfo,
    BatchEvaluationResponse,
    BatchVideoItem,
    BatchStatusResponse
)
from app.api.websocket import manager
from app.api.sse import sse_manager, event_generator
from app.core.config import settings, get_policy_config, get_policy_presets, get_policy_config
from app.core.logging import get_logger
from app.pipeline.graph import run_pipeline
from app.utils.persistence import get_store
from app.utils.checkpoints import get_checkpoint_manager

logger = get_logger("api.routes")

router = APIRouter()

# In-memory storage for batch jobs (in production, use Redis/DB)
batch_jobs = {}
batch_results = {}

# Semaphore to limit concurrent video processing to ONE at a time
# This prevents OOM crashes when processing multiple videos
import asyncio
_processing_semaphore = asyncio.Semaphore(1)

# Persistent temp storage for uploaded videos (for checkpoint recovery)
UPLOADS_DIR = Path(settings.data_dir) / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/evaluate")
async def evaluate_video(
    video: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    policy: Optional[str] = Form(None)
):
    """
    Production-ready API: Evaluate a single video and return verdict with evidence.
    
    **Input:**
    - `video`: Video file upload (multipart/form-data)
    - `url`: Video URL (alternative to file upload)
    - `policy`: Optional JSON string with policy configuration
    
    **Returns:**
    - Complete evaluation result with verdict, scores, evidence, and timestamps
    
    **Example:**
    ```bash
    # Upload file
    curl -X POST http://localhost:8012/v1/evaluate \\
         -F "video=@video.mp4"
    
    # From URL
    curl -X POST http://localhost:8012/v1/evaluate \\
         -F "url=https://example.com/video.mp4"
    ```
    """
    logger.info("=== Video Evaluation API Request ===")
    
    # Validate input
    if not video and not url:
        raise HTTPException(
            status_code=400,
            detail="Either 'video' file or 'url' must be provided"
        )
    
    if video and url:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'video' file or 'url', not both"
        )
    
    video_path = None
    temp_file = None
    
    try:
        # Parse policy configuration
        policy_config = None
        if policy:
            try:
                policy_dict = json.loads(policy)
                policy_config = get_policy_config(policy_dict)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid policy JSON format")
        
        # Handle video file upload
        if video:
            logger.info(f"Processing uploaded video: {video.filename}")
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=Path(video.filename).suffix)
            content = await video.read()
            temp_file.write(content)
            temp_file.close()
            video_path = temp_file.name
        
        # Handle URL download
        elif url:
            logger.info(f"Processing video from URL: {url}")
            import aiohttp
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Failed to download video from URL: {response.status}"
                        )
                    content = await response.read()
                    temp_file.write(content)
                    temp_file.close()
                    video_path = temp_file.name
        
        # Run the complete pipeline
        logger.info(f"Running evaluation pipeline on: {video_path}")
        result = await run_pipeline(
            video_path=video_path,
            policy_config=policy_config,
            video_id=None  # No real-time updates needed for this API
        )
        
        # Extract key information for clean response
        verdict = result.get("verdict", "UNKNOWN")
        criteria = result.get("criteria", {})
        evidence = result.get("evidence", {})
        report = result.get("report", "")
        processing_time = result.get("processing_time_sec", 0)
        
        # Build clean response
        response = {
            "status": "success",
            "verdict": verdict,
            "confidence": result.get("confidence", 0.0),
            "processing_time_sec": processing_time,
            "scores": {
                "violence": float(criteria.get("violence", {}).get("value", 0) or 0),
                "sexual": float(criteria.get("sexual", {}).get("value", 0) or 0),
                "hate": float(criteria.get("hate", {}).get("value", 0) or 0),
                "drugs": float(criteria.get("drugs", {}).get("value", 0) or 0),
                "profanity": float(criteria.get("profanity", {}).get("value", 0) or 0)
            },
            "evidence": {
                "video_metadata": {
                    "duration": result.get("duration", 0),
                    "fps": result.get("fps", 0),
                    "resolution": f"{result.get('width', 0)}x{result.get('height', 0)}",
                    "has_audio": result.get("has_audio", False)
                },
                "object_detections": {
                    "total_frames_analyzed": len(evidence.get("object_detections", [])),
                    "detections": evidence.get("object_detections", [])[:10]  # First 10 for brevity
                },
                "violence_segments": evidence.get("violence_segments", []),
                "audio_transcript": evidence.get("audio_transcript", [])[:5] if evidence.get("audio_transcript") else [],  # First 5 chunks
                "ocr_results": evidence.get("ocr_results", [])[:10],  # First 10 OCR results
                "moderation_flags": evidence.get("moderation_results", [])[:10]  # First 10 flags
            },
            "summary": report,
            "model_versions": result.get("model_versions", {}),
            "policy_applied": {
                "thresholds": policy_config.get("thresholds") if policy_config else get_policy_config().get("thresholds")
            }
        }
        
        logger.info(f"Evaluation complete: {verdict} (confidence: {response['confidence']:.2%})")
        return response
        
    except Exception as e:
        logger.error(f"Evaluation failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")
    
    finally:
        # Cleanup temporary file
        if temp_file and Path(temp_file.name).exists():
            try:
                Path(temp_file.name).unlink()
                logger.info(f"Cleaned up temporary file: {temp_file.name}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file: {e}")


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version=settings.version,
        models_loaded=True
    )


@router.get("/models", response_model=ModelsListResponse)
async def list_models():
    """List configured models and their cache status."""
    models = [
        ModelInfo(
            model_id=settings.yolo26_model_id,
            model_type="vision",
            cached=True,
            status="ready"
        ),
        ModelInfo(
            model_id="yolov8n.pt",  # YOLOE
            model_type="vision_realtime",
            cached=True,
            status="ready"
        ),
        ModelInfo(
            model_id="yolov8s-worldv2.pt",  # YOLO-World
            model_type="vision_openworld",
            cached=True,
            status="ready"
        ),
        ModelInfo(
            model_id=settings.violence_model_id,
            model_type="violence",
            cached=True,
            status="ready"
        ),
        ModelInfo(
            model_id=settings.whisper_model_id,
            model_type="asr",
            cached=True,
            status="ready"
        ),
        ModelInfo(
            model_id=settings.profanity_model_id,
            model_type="moderation",
            cached=True,
            status="ready"
        ),
        ModelInfo(
            model_id=settings.nli_model_id,
            model_type="moderation",
            cached=True,
            status="ready"
        )
    ]
    
    return ModelsListResponse(models=models)


@router.websocket("/ws/{video_id}")
async def websocket_endpoint(websocket: WebSocket, video_id: str):
    """WebSocket endpoint for real-time progress updates (deprecated, use SSE instead)."""
    await manager.connect(websocket, video_id)
    try:
        # Keep connection alive
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, video_id)


@router.get("/sse/{video_id}")
async def sse_endpoint(video_id: str):
    """
    Server-Sent Events endpoint for real-time progress updates.
    
    SSE is simpler and more efficient than WebSocket for one-way updates:
    - HTTP-based (works through proxies/firewalls)
    - Auto-reconnects on connection loss
    - Built-in browser support
    - Lower overhead
    
    Returns:
        StreamingResponse with text/event-stream content type
    """
    return StreamingResponse(
        event_generator(video_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.post("/evaluate/single", response_model=VideoEvaluationResponse)
async def evaluate_video_with_tracking(
    file: UploadFile = File(..., description="Video file to analyze"),
    policy: Optional[str] = Form(None, description="Optional policy config as JSON string"),
    video_id: Optional[str] = Form(None, description="Optional video ID for WebSocket tracking")
):
    """
    Evaluate a video for child safety (with WebSocket tracking).
    
    DEPRECATED: Use `/v1/evaluate` instead for simpler, production-ready API.
    
    This endpoint is used internally by the UI for progress tracking.
    
    Args:
        file: Video file (multipart upload)
        policy: Optional policy configuration as JSON string
        video_id: Optional video ID for WebSocket progress tracking
    
    Returns:
        VideoEvaluationResponse with verdict, violations, evidence, and report
    """
    logger.info(f"Received video evaluation request: {file.filename}")
    
    # Parse policy config if provided
    policy_config = None
    if policy:
        try:
            policy_overrides = json.loads(policy)
            policy_config = get_policy_config(policy_overrides)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid policy JSON: {e}")
    else:
        policy_config = get_policy_config()
    
    # Save uploaded file to temporary location
    temp_dir = Path(tempfile.mkdtemp())
    temp_video_path = temp_dir / file.filename
    
    try:
        # Write uploaded file
        with open(temp_video_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        logger.info(f"Saved video to {temp_video_path}")
        
        # Use provided video_id or generate new one
        if not video_id:
            import uuid
            video_id = str(uuid.uuid4())
        
        logger.info(f"Processing video with ID: {video_id}")
        
        # Run pipeline with video ID for progress tracking
        result = await run_pipeline(str(temp_video_path), policy_config, video_id)
        
        # Convert to response model
        response = VideoEvaluationResponse(**result)
        response.video_id = video_id  # Add video_id to response
        
        return response
    
    except Exception as e:
        logger.error(f"Video evaluation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")
    
    finally:
        # Cleanup temporary file
        try:
            if temp_video_path.exists():
                temp_video_path.unlink()
            temp_dir.rmdir()
        except Exception as e:
            logger.warning(f"Failed to cleanup temp file: {e}")


async def process_video_in_batch(video_path: Path, video_id: str, batch_id: str, policy_config: dict):
    """Process a single video in a batch with semaphore protection."""
    # Acquire semaphore to ensure only ONE video processes at a time
    async with _processing_semaphore:
        logger.info(f"Semaphore acquired for video {video_id} - starting processing")
        
        try:
            # Safety check: ensure video exists in batch_jobs
            if batch_id not in batch_jobs:
                logger.error(f"Batch {batch_id} not found in batch_jobs")
                return
            
            if video_id not in batch_jobs[batch_id]["videos"]:
                logger.error(f"Video {video_id} not found in batch {batch_id}")
                return
            
            # Update status
            batch_jobs[batch_id]["videos"][video_id]["status"] = "processing"
            await manager.send_batch_update(batch_id, batch_jobs[batch_id])
            
            # Set video metadata for checkpoint saving
            video_data = batch_jobs[batch_id]["videos"][video_id]
            manager.set_video_metadata(video_id, {
                "batch_video_id": video_data.get("batch_video_id"),
                "filename": video_data.get("filename"),
                "duration": None  # Will be updated during processing
            })
            
            # Run pipeline (models already loaded at startup)
            result = await run_pipeline(str(video_path), policy_config, video_id)
            
            # Update with results
            batch_jobs[batch_id]["videos"][video_id]["status"] = "completed"
            batch_jobs[batch_id]["videos"][video_id]["verdict"] = result["verdict"]
            batch_jobs[batch_id]["videos"][video_id]["progress"] = 100
            batch_jobs[batch_id]["videos"][video_id]["result"] = result
            batch_jobs[batch_id]["completed"] += 1
            
            # Clear checkpoint on successful completion
            checkpoint_manager = get_checkpoint_manager()
            checkpoint_manager.delete_checkpoint(video_id)
            
            logger.info(f"Video {video_id} completed: verdict={result['verdict']}")
            
        except Exception as e:
            logger.error(f"Failed to process video {video_id}: {e}")
            # Safety check before updating
            if batch_id in batch_jobs and video_id in batch_jobs[batch_id]["videos"]:
                batch_jobs[batch_id]["videos"][video_id]["status"] = "failed"
                batch_jobs[batch_id]["videos"][video_id]["error"] = str(e)
                batch_jobs[batch_id]["videos"][video_id]["progress"] = 100
                batch_jobs[batch_id]["completed"] += 1
        
        finally:
            # Safety check before finalizing
            if batch_id in batch_jobs:
                # Check if batch is complete
                if batch_jobs[batch_id]["completed"] == batch_jobs[batch_id]["total"]:
                    batch_jobs[batch_id]["status"] = "completed"
                
                await manager.send_batch_update(batch_id, batch_jobs[batch_id])
            
            logger.info(f"Semaphore released for video {video_id}")


async def process_batch(batch_id: str, video_paths: List[Path], policy_config: dict):
    """
    Process all videos in a batch.
    
    Videos are queued concurrently but the semaphore ensures only ONE 
    processes at a time, preventing OOM crashes while keeping the API responsive.
    """
    logger.info(f"Processing batch {batch_id} with {len(video_paths)} videos (semaphore-protected)")
    
    # Build video_id mapping
    video_id_map = {}
    for video_id, video_data in batch_jobs[batch_id]["videos"].items():
        for video_path in video_paths:
            if video_path.name == video_data["filename"]:
                video_id_map[str(video_path)] = video_id
                break
    
    # Create all tasks - they'll queue up on the semaphore
    tasks = []
    for video_path in video_paths:
        video_id = video_id_map.get(str(video_path))
        if video_id:
            logger.info(f"Queuing video {video_id} ({video_path.name})")
            tasks.append(process_video_in_batch(video_path, video_id, batch_id, policy_config))
        else:
            logger.error(f"Could not find video_id for {video_path.name}")
    
    # Run all tasks - semaphore ensures sequential execution
    await asyncio.gather(*tasks)


@router.post("/evaluate/batch", response_model=BatchEvaluationResponse)
async def evaluate_batch(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(..., description="Multiple video files or a zip file"),
    policy: Optional[str] = Form(None, description="Optional policy config as JSON string")
):
    """
    Evaluate multiple videos in a batch.
    
    Args:
        files: Multiple video files or a single zip file
        policy: Optional policy configuration as JSON string
    
    Returns:
        BatchEvaluationResponse with batch ID and status
    """
    logger.info(f"Received batch evaluation request: {len(files)} file(s)")
    
    # Parse policy config
    policy_config = get_policy_config(json.loads(policy) if policy else None)
    
    # Generate batch ID
    batch_id = str(uuid.uuid4())
    
    # Extract video files
    temp_dir = Path(tempfile.mkdtemp())
    video_files = []
    uploaded_video_paths = {}  # Map video_id to persistent path
    
    try:
        for uploaded_file in files:
            if uploaded_file.filename.endswith('.zip'):
                # Extract zip file
                zip_path = temp_dir / uploaded_file.filename
                with open(zip_path, "wb") as f:
                    f.write(await uploaded_file.read())
                
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                # Find video files in extracted content
                for ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm']:
                    video_files.extend(temp_dir.rglob(f'*{ext}'))
            else:
                # Regular video file - save to temp_dir first
                video_path = temp_dir / uploaded_file.filename
                with open(video_path, "wb") as f:
                    f.write(await uploaded_file.read())
                video_files.append(video_path)
        
        # Initialize batch job
        batch_jobs[batch_id] = {
            "batch_id": batch_id,
            "status": "processing",
            "total": len(video_files),
            "completed": 0,
            "videos": {}
        }
        
        # Create video items
        videos_list = []
        for video_path in video_files:
            video_id = video_path.stem + "_" + str(uuid.uuid4())[:8]
            
            # Copy to persistent uploads directory for checkpoint recovery
            persistent_path = UPLOADS_DIR / f"{video_id}_{video_path.name}"
            shutil.copy2(video_path, persistent_path)
            uploaded_video_paths[video_id] = str(persistent_path)
            logger.info(f"Saved uploaded video to persistent storage: {persistent_path}")
            
            video_item = {
                "video_id": video_id,
                "filename": video_path.name,
                "status": "queued",
                "progress": 0,
                "verdict": None,
                "error": None,
                "result": None,
                "uploaded_path": str(persistent_path)  # Store persistent path
            }
            batch_jobs[batch_id]["videos"][video_id] = video_item
            videos_list.append(BatchVideoItem(**video_item))
        
        # Start background processing
        background_tasks.add_task(process_batch, batch_id, video_files, policy_config)
        
        return BatchEvaluationResponse(
            batch_id=batch_id,
            total_videos=len(video_files),
            videos=videos_list,
            status="processing"
        )
        
    except Exception as e:
        logger.error(f"Batch evaluation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch evaluation failed: {str(e)}")


@router.get("/evaluate/batch/{batch_id}", response_model=BatchStatusResponse)
async def get_batch_status(batch_id: str):
    """Get status of a batch evaluation."""
    if batch_id not in batch_jobs:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    batch = batch_jobs[batch_id]
    videos_list = [BatchVideoItem(**v) for v in batch["videos"].values()]
    
    return BatchStatusResponse(
        batch_id=batch_id,
        status=batch["status"],
        completed=batch["completed"],
        total=batch["total"],
        videos=videos_list
    )


@router.get("/video/labeled/{video_id}")
async def get_labeled_video(video_id: str):
    """Serve the labeled video with YOLO bounding boxes."""
    # Search for the labeled video in the working directory
    # This assumes the video_id is part of the work directory name
    temp_base = Path(settings.temp_dir)
    
    # Search for work directory containing this video_id
    for work_dir in temp_base.glob("*"):
        if work_dir.is_dir():
            labeled_path = work_dir / "labeled.mp4"
            if labeled_path.exists():
                # Check if this is the right video by checking the video_id in the directory name
                # The work directory is named with the video_id
                if video_id in str(work_dir):
                    return FileResponse(
                        labeled_path,
                        media_type="video/mp4",
                        filename=f"{video_id}_labeled.mp4"
                    )
    
    raise HTTPException(status_code=404, detail="Labeled video not found")


@router.get("/video/uploaded/{video_id}")
async def get_uploaded_video(video_id: str):
    """Serve the original uploaded video for checkpoint recovery."""
    # Search for uploaded video in persistent storage
    for video_file in UPLOADS_DIR.glob(f"{video_id}_*"):
        if video_file.is_file():
            return FileResponse(
                video_file,
                media_type="video/mp4",
                filename=video_file.name
            )
    
    raise HTTPException(status_code=404, detail="Uploaded video not found")


# ===== PERSISTENCE ENDPOINTS =====

@router.post("/results/save")
async def save_results(results: List[dict]):
    """Save batch results to persistent storage."""
    try:
        store = get_store()
        success = store.save_results(results)
        
        if success:
            return {"status": "success", "count": len(results)}
        else:
            raise HTTPException(status_code=500, detail="Failed to save results")
    
    except Exception as e:
        logger.error(f"Save results failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results/load")
async def load_results():
    """Load saved results from persistent storage."""
    try:
        store = get_store()
        results = store.load_results()
        return {"status": "success", "results": results, "count": len(results)}
    
    except Exception as e:
        logger.error(f"Load results failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/results/{video_id}")
async def delete_result(video_id: str):
    """Delete a specific result by video ID."""
    try:
        store = get_store()
        success = store.delete_result(video_id)
        
        if success:
            return {"status": "success", "video_id": video_id}
        else:
            raise HTTPException(status_code=404, detail="Video result not found")
    
    except Exception as e:
        logger.error(f"Delete result failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/results")
async def clear_all_results():
    """Delete all saved results."""
    try:
        store = get_store()
        success = store.clear_all()
        
        if success:
            return {"status": "success", "message": "All results cleared"}
        else:
            raise HTTPException(status_code=500, detail="Failed to clear results")
    
    except Exception as e:
        logger.error(f"Clear results failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== POLICY ENDPOINTS =====

@router.get("/policy/presets")
async def get_presets():
    """Get available policy presets."""
    try:
        presets = get_policy_presets()
        return {"status": "success", "presets": presets}
    except Exception as e:
        logger.error(f"Get presets failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/policy/current")
async def get_current_policy():
    """Get current policy configuration."""
    try:
        policy = get_policy_config()
        return {"status": "success", "policy": policy}
    except Exception as e:
        logger.error(f"Get policy failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/policy/validate")
async def validate_policy(policy: dict):
    """Validate a policy configuration."""
    try:
        # Basic validation
        if "thresholds" in policy:
            for level in ["unsafe", "caution"]:
                if level in policy["thresholds"]:
                    for criterion, value in policy["thresholds"][level].items():
                        if not (0.0 <= value <= 1.0):
                            raise ValueError(f"Threshold {criterion} must be between 0.0 and 1.0")
        
        return {"status": "success", "valid": True, "message": "Policy is valid"}
    except Exception as e:
        return {"status": "error", "valid": False, "message": str(e)}


# ===== Video Import Endpoints =====

@router.post("/import/storage")
async def import_from_storage(request: dict):
    """
    Import videos from cloud storage (S3, GCS, Azure).
    
    This is a placeholder implementation. In production, you would:
    1. Connect to the specified cloud storage
    2. List/download videos from the specified path
    3. Save them to temporary storage
    4. Return video IDs for processing
    """
    provider = request.get('provider')
    bucket = request.get('bucket')
    path = request.get('path', '')
    credentials = request.get('credentials')
    
    logger.info(f"Storage import request: {provider}/{bucket}/{path}")
    
    try:
        # TODO: Implement actual cloud storage integration
        # For now, return a mock response
        videos = []
        
        # Example implementation would use boto3 for S3, google-cloud-storage for GCS, etc.
        # if provider == 's3':
        #     import boto3
        #     s3 = boto3.client('s3', ...)
        #     objects = s3.list_objects_v2(Bucket=bucket, Prefix=path)
        #     for obj in objects.get('Contents', []):
        #         # Download and save video
        #         video_id = str(uuid.uuid4())
        #         videos.append({
        #             'video_id': video_id,
        #             'filename': obj['Key'],
        #             'source': 'storage'
        #         })
        
        return {
            "success": True,
            "message": f"Cloud storage import is not yet implemented. Please use local file upload.",
            "videos": videos
        }
    
    except Exception as e:
        logger.error(f"Storage import error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import/database")
async def import_from_database(request: dict):
    """
    Import videos from database.
    
    This is a placeholder implementation. In production, you would:
    1. Connect to the specified database
    2. Execute the query to get video paths/URLs
    3. Fetch the videos
    4. Save them to temporary storage
    5. Return video IDs for processing
    """
    database_type = request.get('database_type')
    connection_string = request.get('connection_string')
    query = request.get('query')
    
    logger.info(f"Database import request: {database_type}")
    
    try:
        # TODO: Implement actual database integration
        # For now, return a mock response
        videos = []
        
        # Example implementation would use psycopg2 for PostgreSQL, pymongo for MongoDB, etc.
        # if database_type == 'postgres':
        #     import psycopg2
        #     conn = psycopg2.connect(connection_string)
        #     cursor = conn.cursor()
        #     cursor.execute(query)
        #     for row in cursor.fetchall():
        #         video_path = row[0]  # Assuming first column is video path
        #         video_id = str(uuid.uuid4())
        #         videos.append({
        #             'video_id': video_id,
        #             'filename': Path(video_path).name,
        #             'source': 'database'
        #         })
        
        return {
            "success": True,
            "message": f"Database import is not yet implemented. Please use local file upload.",
            "videos": videos
        }
    
    except Exception as e:
        logger.error(f"Database import error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import/urls")
async def import_from_urls(request: dict):
    """
    Import videos from URLs.
    
    Downloads videos from provided URLs and prepares them for processing.
    """
    urls = request.get('urls', [])
    
    if not urls:
        raise HTTPException(status_code=400, detail="No URLs provided")
    
    logger.info(f"URL import request: {len(urls)} URL(s)")
    
    try:
        import aiohttp
        videos = []
        
        async with aiohttp.ClientSession() as session:
            for url in urls:
                try:
                    # Generate unique video ID
                    video_id = str(uuid.uuid4())
                    
                    # Extract filename from URL
                    filename = Path(url).name
                    if not filename or '.' not in filename:
                        filename = f"video_{video_id}.mp4"
                    
                    # Download video to temporary storage
                    video_path = UPLOADS_DIR / f"{video_id}_{filename}"
                    
                    logger.info(f"Downloading video from {url}")
                    async with session.get(url) as response:
                        if response.status != 200:
                            logger.error(f"Failed to download {url}: HTTP {response.status}")
                            continue
                        
                        # Save video file
                        with open(video_path, 'wb') as f:
                            while True:
                                chunk = await response.content.read(8192)
                                if not chunk:
                                    break
                                f.write(chunk)
                    
                    logger.info(f"Downloaded video to {video_path}")
                    
                    videos.append({
                        'video_id': video_id,
                        'filename': filename,
                        'source': 'url',
                        'path': str(video_path)
                    })
                    
                except Exception as e:
                    logger.error(f"Error downloading from {url}: {e}")
                    continue
        
        if not videos:
            raise HTTPException(status_code=400, detail="Failed to download any videos from the provided URLs")
        
        return {
            "success": True,
            "message": f"Successfully imported {len(videos)} video(s) from URLs",
            "videos": videos
        }
    
    except Exception as e:
        logger.error(f"URL import error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Checkpoint Management Endpoints =====

@router.post("/checkpoints/save")
async def save_checkpoint(checkpoint_data: dict):
    """
    Save checkpoint for a video.
    
    Request body:
    {
        "video_id": "uuid",
        "batch_video_id": "V_101_abc123",
        "filename": "video.mp4",
        "progress": 60,
        "stage": "audio_transcription",
        "status": "processing",
        "duration": 120.5
    }
    """
    video_id = checkpoint_data.get('video_id')
    if not video_id:
        raise HTTPException(status_code=400, detail="video_id is required")
    
    try:
        checkpoint_manager = get_checkpoint_manager()
        success = checkpoint_manager.save_checkpoint(video_id, checkpoint_data)
        
        if success:
            return {"status": "success", "message": f"Checkpoint saved for {video_id}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to save checkpoint")
    
    except Exception as e:
        logger.error(f"Save checkpoint failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/checkpoints/load/{video_id}")
async def load_checkpoint(video_id: str):
    """
    Load checkpoint for a specific video.
    """
    try:
        checkpoint_manager = get_checkpoint_manager()
        checkpoint = checkpoint_manager.load_checkpoint(video_id)
        
        if checkpoint:
            return {"status": "success", "checkpoint": checkpoint}
        else:
            raise HTTPException(status_code=404, detail="Checkpoint not found")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Load checkpoint failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/checkpoints/list")
async def list_checkpoints():
    """
    List all checkpoints (interrupted videos).
    """
    try:
        checkpoint_manager = get_checkpoint_manager()
        checkpoints = checkpoint_manager.get_interrupted_videos()
        
        return {
            "status": "success",
            "count": len(checkpoints),
            "checkpoints": checkpoints
        }
    
    except Exception as e:
        logger.error(f"List checkpoints failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/checkpoints/{video_id}")
async def delete_checkpoint(video_id: str):
    """
    Delete checkpoint for a specific video.
    """
    try:
        checkpoint_manager = get_checkpoint_manager()
        success = checkpoint_manager.delete_checkpoint(video_id)
        
        if success:
            return {"status": "success", "message": f"Checkpoint deleted for {video_id}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete checkpoint")
    
    except Exception as e:
        logger.error(f"Delete checkpoint failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/checkpoints")
async def clear_all_checkpoints():
    """
    Clear all checkpoints.
    """
    try:
        checkpoint_manager = get_checkpoint_manager()
        count = checkpoint_manager.clear_all_checkpoints()
        
        return {"status": "success", "message": f"Cleared {count} checkpoint(s)"}
    
    except Exception as e:
        logger.error(f"Clear checkpoints failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/checkpoints/cleanup")
async def cleanup_old_checkpoints(max_age_hours: int = 24):
    """
    Clean up old checkpoints.
    
    Query parameter:
        max_age_hours: Maximum age in hours (default: 24)
    """
    try:
        checkpoint_manager = get_checkpoint_manager()
        count = checkpoint_manager.cleanup_old_checkpoints(max_age_hours)
        
        return {"status": "success", "message": f"Cleaned up {count} old checkpoint(s)"}
    
    except Exception as e:
        logger.error(f"Cleanup checkpoints failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


