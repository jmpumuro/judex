"""
Video segmentation node - create time windows and frame sampling plan.

Optimized for VideoMAE's 16-frame architecture with overlapping segments.
Saves keyframes and thumbnails for UI display.

Industry Standard: Uses LangGraph config for callbacks (not state).
"""
import cv2
from pathlib import Path
from typing import Optional
from langchain_core.runnables import RunnableConfig

from app.pipeline.state import PipelineState
from app.pipeline.callbacks import send_progress
from app.core.logging import get_logger
from app.utils.ffmpeg import extract_frames, extract_segment_frames
from app.utils.progress import save_stage_output, format_stage_output
from app.utils.storage import get_storage_service

logger = get_logger("node.segment")

# Thumbnail settings for filmstrip display
THUMB_WIDTH = 120
THUMB_HEIGHT = 68  # 16:9 aspect ratio
KEYFRAME_INTERVAL = 1  # Save a keyframe every N sampled frames


def _load_cached_stage_output(video_id: str, stage_name: str) -> dict:
    """Load cached stage output from database."""
    try:
        from app.db.connection import get_session
        from app.db.models import EvaluationItem
        
        with get_session() as session:
            item = session.query(EvaluationItem).filter(
                EvaluationItem.id == video_id
            ).first()
            
            if item and item.stage_outputs:
                output = (
                    item.stage_outputs.get(stage_name) or
                    item.stage_outputs.get(f"{stage_name}_video") or
                    {}
                )
                logger.info(f"Loaded cached {stage_name} output for {video_id}")
                return output
                
    except Exception as e:
        logger.warning(f"Failed to load cached {stage_name} output: {e}")
    
    return {}


def segment_video_impl(state: PipelineState, config: Optional[RunnableConfig] = None) -> PipelineState:
    """
    Segment media into time windows and sample frames.
    
    Supports both VIDEO and IMAGE:
    - VIDEO: Create overlapping segments for VideoMAE (16 frames per window)
    - IMAGE: Single frame, no segmentation needed
    
    Industry Standard: Receives config parameter for callbacks.
    Progress is sent via config["callbacks"], not stored in state.
    """
    logger.info("=== Segment Media Node ===")
    
    video_id = state.get("video_id")
    is_reprocessing = state.get("is_reprocessing", False)
    media_type = state.get("media_type", "video")
    
    # Handle IMAGE - no segmentation needed
    if media_type == "image":
        return _segment_image(state, config)
    
    # === VIDEO PROCESSING ===
    
    # Check if already processed (resuming from checkpoint)
    # For reprocessing, always re-extract frames since work_dir is new
    sampled_frames = state.get("sampled_frames", [])
    segments = state.get("segments", [])
    
    # Check if frames actually exist on disk
    frames_exist_on_disk = False
    if sampled_frames and len(sampled_frames) > 0:
        if isinstance(sampled_frames[0], dict) and "path" in sampled_frames[0]:
            first_frame_path = sampled_frames[0].get("path", "")
            frames_exist_on_disk = first_frame_path and Path(first_frame_path).exists()
    
    if not is_reprocessing and sampled_frames and len(sampled_frames) > 0 and frames_exist_on_disk:
        if isinstance(sampled_frames[0], dict) and "path" in sampled_frames[0]:
            logger.info(f"Segment already complete (from checkpoint), {len(sampled_frames)} frames cached, skipping")
            send_progress(config, "segment_video", "Using cached result", 100)
            
            if video_id:
                cached_output = _load_cached_stage_output(video_id, "segment")
                
                storage = get_storage_service()
                stored_frames = []
                stored_thumbs = []
                try:
                    stored_frames = storage.list_frames(video_id)
                    stored_thumbs = storage.list_thumbnails(video_id)
                except Exception as e:
                    logger.warning(f"Could not list stored frames: {e}")
                
                save_stage_output(video_id, "segment", format_stage_output(
                    "segment",
                    status="cached",
                    cached=True,
                    cache_source="checkpoint",
                    frames_extracted=len(sampled_frames),
                    frames_stored=len(stored_frames),
                    thumbnails_stored=len(stored_thumbs),
                    segments_count=len(segments),
                    segments=segments[:5] if segments else [],
                    duration=state.get("duration"),
                    sampling_fps=cached_output.get("sampling_fps", 1.0),
                    original_processing_time=cached_output.get("processing_time"),
                ))
            return state
    
    if is_reprocessing:
        logger.info("Reprocessing mode: re-extracting frames")
    
    send_progress(config, "segment_video", "Preparing video segments", 20)
    
    video_path = state["video_path"]
    work_dir = state["work_dir"]
    duration = state["duration"]
    fps = state.get("fps", 30)
    policy_config = state.get("policy_config", {})
    
    yolo_sampling_fps = policy_config.get("yolo_sampling_fps", 1.0)
    videomae_segment_duration = policy_config.get("videomae_segment_duration", 2.0)
    videomae_stride = policy_config.get("videomae_stride", 1.0)
    
    frames_dir = Path(work_dir) / "frames"
    
    try:
        send_progress(config, "segment_video", "Extracting frames for vision analysis", 30)
        
        logger.info(f"Extracting frames at {yolo_sampling_fps} fps for YOLO")
        frame_paths = extract_frames(
            video_path,
            str(frames_dir),
            fps=yolo_sampling_fps
        )
        
        sampled_frames = []
        for i, frame_path in enumerate(frame_paths):
            timestamp = i / yolo_sampling_fps
            sampled_frames.append({
                "path": frame_path,
                "timestamp": timestamp,
                "frame_index": i,
                "tier": 1
            })
        
        state["sampled_frames"] = sampled_frames
        logger.info(f"Extracted {len(sampled_frames)} frames for vision analysis")
        
        video_id = state.get("video_id")
        if video_id:
            try:
                storage = get_storage_service()
                keyframe_count = 0
                thumbnail_count = 0
                
                send_progress(config, "segment_video", "Generating thumbnails for filmstrip", 40)
                
                for frame_info in sampled_frames:
                    frame_idx = frame_info["frame_index"]
                    
                    if frame_idx % KEYFRAME_INTERVAL == 0:
                        frame_path = frame_info["path"]
                        timestamp = frame_info["timestamp"]
                        
                        img = cv2.imread(frame_path)
                        if img is None:
                            continue
                        
                        with open(frame_path, 'rb') as f:
                            frame_data = f.read()
                        storage.upload_frame(frame_data, video_id, frame_idx, timestamp)
                        keyframe_count += 1
                        
                        thumb = cv2.resize(img, (THUMB_WIDTH, THUMB_HEIGHT), interpolation=cv2.INTER_AREA)
                        _, thumb_data = cv2.imencode('.jpg', thumb, [cv2.IMWRITE_JPEG_QUALITY, 70])
                        storage.upload_frame_thumbnail(thumb_data.tobytes(), video_id, frame_idx, timestamp)
                        thumbnail_count += 1
                
                state["frames_saved"] = keyframe_count
                state["thumbnails_saved"] = thumbnail_count
                logger.info(f"Saved {keyframe_count} keyframes and {thumbnail_count} thumbnails to storage")
                
            except Exception as e:
                logger.warning(f"Failed to save frames to storage: {e}")
        
    except Exception as e:
        logger.error(f"Frame extraction failed: {e}")
        state["errors"] = state.get("errors", []) + [f"Frame extraction failed: {e}"]
        return state
    
    send_progress(config, "segment_video", "Creating VideoMAE segments", 50)
    
    segments = []
    segments_dir = Path(work_dir) / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)
    
    current_time = 0.0
    segment_index = 0
    
    while current_time < duration:
        start_time = current_time
        end_time = min(start_time + videomae_segment_duration, duration)
        
        if (end_time - start_time) < 1.0:
            break
        
        try:
            segment_frames = extract_segment_frames(
                video_path,
                str(segments_dir / f"seg_{segment_index:04d}"),
                start_time,
                end_time - start_time,
                num_frames=16
            )
            
            segments.append({
                "index": segment_index,
                "start_time": start_time,
                "end_time": end_time,
                "frames": segment_frames,
                "tier": 1,
                "num_frames": 16
            })
            
            segment_index += 1
            
        except Exception as e:
            logger.warning(f"Failed to extract segment at {start_time:.2f}s: {e}")
        
        current_time += videomae_stride
    
    state["segments"] = segments
    state["videomae_config"] = {
        "segment_duration": videomae_segment_duration,
        "stride": videomae_stride,
        "frames_per_segment": 16,
        "total_segments": len(segments)
    }
    
    logger.info(f"Created {len(segments)} VideoMAE segments ({videomae_segment_duration}s window, {videomae_stride}s stride)")
    
    save_stage_output(state.get("video_id"), "segment", format_stage_output(
        "segment",
        frames_extracted=len(sampled_frames),
        segments_created=len(segments),
        sampling_fps=yolo_sampling_fps,
        videomae_config=state.get("videomae_config"),
        segment_overlap_percent=round((videomae_segment_duration - videomae_stride) / videomae_segment_duration * 100, 1)
    ))
    
    return state


def _segment_image(state: PipelineState, config: Optional[RunnableConfig]) -> PipelineState:
    """
    Handle image "segmentation" - just prepare the single frame.
    
    For images, we already have the frame from ingest, so this stage
    mainly uploads it to storage and prepares thumbnail.
    
    Args:
        state: Pipeline state with image metadata
        config: LangGraph config for callbacks
        
    Returns:
        Updated state with sampled_frames containing the single image
    """
    from PIL import Image
    import io
    
    video_id = state.get("video_id")
    work_dir = state.get("work_dir")
    
    send_progress(config, "segment_video", "Preparing image for analysis", 30)
    
    # The image is already in sampled_frames from ingest
    sampled_frames = state.get("sampled_frames", [])
    
    if not sampled_frames:
        # Fallback: use video_path as the frame
        media_path = state.get("media_path") or state.get("video_path")
        sampled_frames = [{
            "path": media_path,
            "timestamp": 0,
            "frame_index": 0,
            "tier": 1,
        }]
        state["sampled_frames"] = sampled_frames
    
    # Ensure frame path exists
    frame_path = sampled_frames[0].get("path") if sampled_frames else None
    if not frame_path or not Path(frame_path).exists():
        logger.error(f"Image frame not found: {frame_path}")
        state["errors"] = state.get("errors", []) + ["Image frame not found"]
        return state
    
    send_progress(config, "segment_video", "Uploading image to storage", 50)
    
    # Upload frame to storage
    storage = get_storage_service()
    frames_uploaded = 0
    
    try:
        # Upload the single frame
        frame_name = f"frame_0000_0{Path(frame_path).suffix}"
        storage.upload_frame(video_id, frame_name, frame_path)
        frames_uploaded = 1
        logger.info(f"Uploaded image frame to storage")
    except Exception as e:
        logger.warning(f"Failed to upload image to storage: {e}")
    
    send_progress(config, "segment_video", "Creating thumbnail", 70)
    
    # Create and upload thumbnail
    try:
        with Image.open(frame_path) as img:
            # Create thumbnail
            thumb = img.copy()
            thumb.thumbnail((THUMB_WIDTH, THUMB_HEIGHT), Image.Resampling.LANCZOS)
            
            # Save thumbnail
            thumb_dir = Path(work_dir) / "thumbnails"
            thumb_dir.mkdir(exist_ok=True)
            thumb_path = thumb_dir / "thumb_0000.jpg"
            
            # Convert to RGB if necessary (for PNG with alpha)
            if thumb.mode in ('RGBA', 'P'):
                thumb = thumb.convert('RGB')
            thumb.save(thumb_path, "JPEG", quality=85)
            
            # Upload thumbnail
            storage.upload_thumbnail(video_id, "thumb_0000.jpg", str(thumb_path))
            logger.info(f"Uploaded image thumbnail to storage")
            
    except Exception as e:
        logger.warning(f"Failed to create/upload thumbnail: {e}")
    
    # No segments for images (no temporal data)
    state["segments"] = []
    
    # No VideoMAE config for images
    state["videomae_config"] = {
        "segment_duration": 0,
        "stride": 0,
        "frames_per_segment": 1,
        "total_segments": 0,
        "media_type": "image"
    }
    
    send_progress(config, "segment_video", "Image ready", 100)
    
    logger.info(f"Image segmentation complete: 1 frame prepared")
    
    # Save stage output
    save_stage_output(video_id, "segment", format_stage_output(
        "segment",
        media_type="image",
        frames_extracted=1,
        frames_stored=frames_uploaded,
        thumbnails_stored=1,
        segments_created=0,
        sampling_fps=0,
        note="Single image - no temporal segmentation"
    ))
    
    return state


# Legacy wrapper for backward compatibility
def segment_video(state: PipelineState) -> PipelineState:
    """Legacy wrapper - calls impl without config."""
    return segment_video_impl(state, None)
