"""
YOLO26 vision detection node.
Creates labeled video with bounding boxes and uploads to storage immediately.
"""
import os
from pathlib import Path
from app.pipeline.state import PipelineState
from app.core.logging import get_logger
from app.models import get_yolo26_detector
from app.utils.hashing import generate_vision_id
from app.utils.progress import send_progress, save_stage_output, format_stage_output
from app.utils.ffmpeg import create_labeled_video
from app.utils.storage import get_storage_service

logger = get_logger("node.yolo26")

# Enable labeled video creation via environment variable (default: enabled)
CREATE_LABELED_VIDEO = os.getenv("CREATE_LABELED_VIDEO", "true").lower() == "true"


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
    labeled_video_path = None
    if CREATE_LABELED_VIDEO and all_detections:
        try:
            send_progress(state.get("progress_callback"), "yolo26_vision", "Creating labeled video", 70)
            
            video_path = state.get("video_path")
            work_dir = state.get("work_dir")
            video_id = state.get("video_id")
            fps = state.get("fps", 30)
            violence_segments = state.get("violence_segments", [])
            
            if video_path and work_dir:
                output_path = str(Path(work_dir) / "labeled.mp4")
                
                labeled_video_path = create_labeled_video(
                    video_path=video_path,
                    output_path=output_path,
                    detections=all_detections,
                    fps=fps,
                    violence_segments=violence_segments
                )
                
                if labeled_video_path and Path(labeled_video_path).exists():
                    # Upload to storage
                    storage = get_storage_service()
                    stored_path = storage.upload_labeled_video(labeled_video_path, video_id)
                    state["labeled_video_path"] = stored_path
                    logger.info(f"Labeled video uploaded: {stored_path}")
                    
                    # INDUSTRY STANDARD: Persist directly to database immediately
                    # This ensures the path is saved even if pipeline fails later
                    if video_id:
                        try:
                            from app.api.evaluations import EvaluationRepository
                            EvaluationRepository.update_item(video_id, labeled_video_path=stored_path)
                            logger.info(f"Labeled video path persisted to DB: {stored_path}")
                        except Exception as db_err:
                            logger.warning(f"Failed to persist labeled_video_path to DB: {db_err}")
                else:
                    logger.warning("Labeled video was not created")
        except Exception as e:
            logger.error(f"Failed to create labeled video: {e}")
            # Non-fatal - continue without labeled video
    else:
        if not CREATE_LABELED_VIDEO:
            logger.info("Labeled video creation disabled via CREATE_LABELED_VIDEO=false")
        elif not all_detections:
            logger.info("No detections - skipping labeled video creation")
    
    # Save stage output for real-time retrieval
    signals = detector.get_safety_signals(all_detections) if all_detections else {}
    
    # Summarize detections by label
    detection_summary = {}
    for det in all_detections:
        label = det.get("label", "unknown")
        detection_summary[label] = detection_summary.get(label, 0) + 1
    
    save_stage_output(state.get("video_id"), "yolo26", format_stage_output(
        "yolo26",
        total_detections=len(all_detections),
        frames_analyzed=len(sampled_frames),
        detection_summary=detection_summary,
        safety_signals=signals,
        labeled_video_created=labeled_video_path is not None,
        labeled_video_path=state.get("labeled_video_path"),
        # Include top 20 detections for preview
        detections=all_detections[:20] if all_detections else []
    ))
    
    return state
