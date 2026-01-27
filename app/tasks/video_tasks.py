"""
Video processing Celery tasks.

These tasks run sequentially (one at a time) to prevent OOM crashes.
"""
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional

from app.celery_app import celery_app
from app.core.logging import get_logger
from app.core.config import get_policy_config
from app.pipeline.graph import run_pipeline
from app.api.sse import sse_manager
from app.utils.checkpoints import get_checkpoint_manager

logger = get_logger("tasks.video")


def run_async(coro):
    """Helper to run async code in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="process_video")
def process_video_task(
    self,
    video_path: str,
    video_id: str,
    batch_id: str,
    policy_config: Optional[Dict[str, Any]] = None,
    batch_video_id: Optional[str] = None,
    filename: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process a single video through the analysis pipeline.
    
    This task runs sequentially (worker_concurrency=1) to prevent
    multiple videos being processed simultaneously and causing OOM.
    
    Args:
        video_path: Path to the video file
        video_id: Unique ID for this video
        batch_id: Batch ID this video belongs to
        policy_config: Optional policy configuration
        batch_video_id: Video ID used for SSE/progress tracking
        filename: Original filename
    
    Returns:
        Pipeline result dictionary
    """
    logger.info(f"=== Celery Task: Processing video {video_id} ===")
    logger.info(f"Video path: {video_path}")
    logger.info(f"Batch ID: {batch_id}")
    
    try:
        # Update task state
        self.update_state(
            state="PROCESSING",
            meta={"video_id": video_id, "progress": 0, "stage": "starting"}
        )
        
        # Send SSE update if available
        if batch_video_id:
            run_async(sse_manager.send_progress(batch_video_id, {
                "stage": "starting",
                "message": "Starting video processing",
                "progress": 0
            }))
        
        # Run the pipeline
        policy = policy_config or get_policy_config()
        result = run_async(run_pipeline(video_path, policy, video_id))
        
        # Clear checkpoint on success
        checkpoint_manager = get_checkpoint_manager()
        checkpoint_manager.delete_checkpoint(video_id)
        
        logger.info(f"Video {video_id} processed successfully: verdict={result.get('verdict')}")
        
        return {
            "status": "completed",
            "video_id": video_id,
            "batch_id": batch_id,
            "verdict": result.get("verdict"),
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Video {video_id} processing failed: {e}", exc_info=True)
        
        # Send failure SSE
        if batch_video_id:
            run_async(sse_manager.send_progress(batch_video_id, {
                "stage": "error",
                "message": str(e),
                "progress": 0
            }))
        
        return {
            "status": "failed",
            "video_id": video_id,
            "batch_id": batch_id,
            "error": str(e)
        }
