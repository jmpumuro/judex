"""
YOLO-World detection node for batch video pipeline.

Uses YOLO-World open-vocabulary detection for context-aware
object detection based on policy requirements.
"""
from pathlib import Path
from typing import List, Dict, Any
from app.pipeline.state import PipelineState
from app.models import get_yoloworld_detector
from app.core.logging import get_logger
from app.utils.progress import send_progress

logger = get_logger("pipeline.yoloworld")


def run_yoloworld_vision(state: PipelineState) -> PipelineState:
    """
    Run YOLO-World open-vocabulary object detection.
    
    CONTEXT-AWARE DETECTION:
    - Uses policy-defined prompts for specific scenario detection
    - Can detect custom objects (e.g., "unattended bag", "suspicious package")
    - Batch processing for efficiency
    - Complements standard YOLO detection
    
    Args:
        state: Current pipeline state
        
    Returns:
        Updated state with YOLO-World detections
    """
    send_progress(state.get("progress_callback"), "yoloworld_vision", "Starting YOLO-World detection", 25)
    
    try:
        # Get detector from model registry (singleton)
        detector = get_yoloworld_detector()
        
        # Get sampled frames
        sampled_frames = state.get("sampled_frames", [])
        if not sampled_frames:
            logger.warning("No sampled frames available for YOLO-World detection")
            state["yoloworld_detections"] = []
            return state
        
        logger.info(f"Running YOLO-World on {len(sampled_frames)} frames")
        
        # Extract policy-based prompts if available
        policy_config = state.get("policy_config", {})
        custom_prompts = policy_config.get("yoloworld_prompts")
        
        if custom_prompts:
            logger.info(f"Using policy-defined prompts: {custom_prompts}")
            detector.set_prompts(custom_prompts)
        
        # Batch detection for efficiency
        frame_paths = [f["path"] for f in sampled_frames]
        timestamps = [f["timestamp"] for f in sampled_frames]
        
        send_progress(state.get("progress_callback"), "yoloworld_vision", 
                     f"Analyzing {len(frame_paths)} frames", 30)
        
        # Run batch detection
        all_detections = detector.detect_batch(frame_paths, timestamps)
        
        # Store detections
        state["yoloworld_detections"] = all_detections
        
        # Get safety signals
        signals = detector.get_safety_signals(all_detections)
        
        # Log results
        logger.info(
            f"YOLO-World detection complete: {len(all_detections)} detections, "
            f"Weapons: {signals['weapon_count']}, "
            f"Violence indicators: {signals['violence_indicators']}, "
            f"Matched prompts: {signals['matched_prompts']}"
        )
        
        # Merge with existing vision detections (if any)
        existing_detections = state.get("vision_detections", [])
        state["vision_detections"] = existing_detections + all_detections
        
        send_progress(state.get("progress_callback"), "yoloworld_vision", 
                     "YOLO-World detection complete", 35)
        state["current_stage"] = "yoloworld_vision_complete"
        
        return state
        
    except Exception as e:
        logger.error(f"YOLO-World detection failed: {e}", exc_info=True)
        state.setdefault("errors", []).append(f"YOLO-World detection error: {str(e)}")
        state["yoloworld_detections"] = []
        return state
