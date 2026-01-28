"""
Progress callback helper for synchronous nodes.
"""
import asyncio
from typing import Callable, Optional, Dict, Any

from app.core.logging import get_logger

logger = get_logger("progress")


def send_progress(callback: Optional[Callable], stage: str, message: str, progress: int):
    """Send progress update from sync context."""
    if not callback:
        return
    
    try:
        # Try to get the current event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create a task in the running loop
            asyncio.create_task(callback(stage, message, progress))
        else:
            # Run in the loop
            loop.run_until_complete(callback(stage, message, progress))
    except RuntimeError:
        # No event loop available, try to run directly
        try:
            asyncio.run(callback(stage, message, progress))
        except:
            pass  # Skip if unable to send progress


def save_stage_output(video_id: str, stage_name: str, output: Dict[str, Any]):
    """
    Save stage output to database for real-time retrieval.
    
    This is called by each pipeline node after completing its work.
    The output is stored in PostgreSQL (EvaluationItem.stage_outputs) and can be fetched via API.
    
    Args:
        video_id: Evaluation item ID (not video_id - named for backward compatibility)
        stage_name: Name of the completed stage
        output: Dictionary with stage output data
    """
    if not video_id:
        logger.warning(f"save_stage_output called without item_id for stage {stage_name}")
        return
    
    logger.info(f"Saving stage output: {stage_name} for item {video_id}")
    
    try:
        # Use new EvaluationRepository architecture
        from app.api.evaluations import EvaluationRepository
        
        success = EvaluationRepository.save_stage_output(video_id, stage_name, output)
        
        if success:
            logger.info(f"✓ Saved output for stage '{stage_name}' (item: {video_id})")
        else:
            logger.warning(f"save_stage_output failed for {video_id}/{stage_name}")
        
    except Exception as e:
        logger.error(f"Failed to save stage output for {video_id}/{stage_name}: {e}", exc_info=True)


def format_stage_output(stage_name: str, **kwargs) -> Dict[str, Any]:
    """
    Format stage output in a consistent structure.
    
    Args:
        stage_name: Name of the stage
        **kwargs: Stage-specific output fields
        
    Returns:
        Formatted output dictionary
    """
    from datetime import datetime
    
    return {
        "stage": stage_name,
        "timestamp": datetime.utcnow().isoformat(),
        **kwargs
    }
