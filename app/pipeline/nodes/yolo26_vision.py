"""
YOLO26 vision detection node.
"""
from pathlib import Path
from app.pipeline.state import PipelineState
from app.core.logging import get_logger
from app.models import get_yolo26_detector
from app.utils.hashing import generate_vision_id
from app.utils.progress import send_progress
from app.utils.ffmpeg import create_labeled_video

logger = get_logger("node.yolo26")


def run_yolo26_vision(state: PipelineState) -> PipelineState:
    """Run YOLO26 object detection on sampled frames."""
    logger.info("=== YOLO26 Vision Node ===")
    
    send_progress(state.get("progress_callback"), "yolo26_vision", "Loading YOLO26 model", 30)
    
    sampled_frames = state.get("sampled_frames", [])
    
    if not sampled_frames:
        logger.warning("No sampled frames available")
        return state
    
    detector = get_yolo26_detector()
    
    send_progress(state.get("progress_callback"), "yolo26_vision", f"Detecting objects in {len(sampled_frames)} frames", 50)
    
    all_detections = []
    
    for frame_info in sampled_frames:
        frame_path = frame_info["path"]
        timestamp = frame_info["timestamp"]
        frame_index = frame_info["frame_index"]
        
        detections = detector.detect(frame_path, timestamp)
        
        # Add IDs to detections
        for det_idx, detection in enumerate(detections):
            detection["id"] = generate_vision_id(frame_index, det_idx)
            all_detections.append(detection)
    
    state["vision_detections"] = all_detections
    
    logger.info(f"YOLO26 detected {len(all_detections)} objects across {len(sampled_frames)} frames")
    
    # Log summary
    if all_detections:
        signals = detector.get_safety_signals(all_detections)
        logger.info(f"Safety signals: weapons={signals['weapon_count']}, substances={signals['substance_count']}")
    
    # Create labeled video with bounding boxes
    if all_detections:
        try:
            send_progress(state.get("progress_callback"), "yolo26_vision", "Creating labeled video", 80)
            
            video_path = state["video_path"]
            work_dir = state["work_dir"]
            fps = state.get("fps", 30.0)
            
            # Get violence segments if available (may not be available yet in pipeline order)
            violence_segments = state.get("violence_segments", None)
            
            labeled_video_path = str(Path(work_dir) / "labeled.mp4")
            create_labeled_video(video_path, labeled_video_path, all_detections, fps, violence_segments)
            
            state["labeled_video_path"] = labeled_video_path
            logger.info(f"Created labeled video: {labeled_video_path}")
            
        except Exception as e:
            logger.error(f"Failed to create labeled video: {e}")
            # Don't fail the pipeline if labeled video creation fails
    
    return state
