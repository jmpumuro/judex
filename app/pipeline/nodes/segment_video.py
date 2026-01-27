"""
Video segmentation node - create time windows and frame sampling plan.
Optimized for VideoMAE's 16-frame architecture with overlapping segments.
"""
from pathlib import Path
from app.pipeline.state import PipelineState
from app.core.logging import get_logger
from app.utils.ffmpeg import extract_frames, extract_segment_frames
from app.utils.progress import send_progress

logger = get_logger("node.segment")


def segment_video(state: PipelineState) -> PipelineState:
    """
    Segment video into time windows and sample frames for VideoMAE.
    
    VideoMAE architecture:
    - Expects exactly 16 frames per inference
    - At 30fps (normalized), 16 frames = 0.53s (too short for violence context)
    - Solution: Sample to effective 8fps → 16 frames ≈ 2 seconds
    - Use overlapping segments (50% stride) to catch events at boundaries
    """
    logger.info("=== Segment Video Node ===")
    
    send_progress(state.get("progress_callback"), "segment_video", "Preparing video segments", 20)
    
    video_path = state["video_path"]
    work_dir = state["work_dir"]
    duration = state["duration"]
    fps = state.get("fps", 30)
    policy_config = state.get("policy_config", {})
    
    # Get sampling parameters
    # For YOLO: sparse sampling (1 fps is good)
    yolo_sampling_fps = policy_config.get("yolo_sampling_fps", 1.0)
    
    # For VideoMAE: 2-second segments with 50% overlap
    # This gives better context than 0.53s clips
    videomae_segment_duration = policy_config.get("videomae_segment_duration", 2.0)
    videomae_stride = policy_config.get("videomae_stride", 1.0)  # 50% overlap
    
    # Extract frames for YOLO analysis (Tier 1: sparse scan)
    frames_dir = Path(work_dir) / "frames"
    
    try:
        send_progress(state.get("progress_callback"), "segment_video", "Extracting frames for vision analysis", 30)
        
        logger.info(f"Extracting frames at {yolo_sampling_fps} fps for YOLO")
        frame_paths = extract_frames(
            video_path,
            str(frames_dir),
            fps=yolo_sampling_fps
        )
        
        # Calculate timestamps for frames
        sampled_frames = []
        for i, frame_path in enumerate(frame_paths):
            timestamp = i / yolo_sampling_fps
            sampled_frames.append({
                "path": frame_path,
                "timestamp": timestamp,
                "frame_index": i,
                "tier": 1  # Sparse scan tier
            })
        
        state["sampled_frames"] = sampled_frames
        logger.info(f"Extracted {len(sampled_frames)} frames for vision analysis")
        
    except Exception as e:
        logger.error(f"Frame extraction failed: {e}")
        state["errors"] = state.get("errors", []) + [f"Frame extraction failed: {e}"]
        return state
    
    # Create overlapping segments for VideoMAE violence detection
    send_progress(state.get("progress_callback"), "segment_video", "Creating VideoMAE segments", 50)
    
    segments = []
    segments_dir = Path(work_dir) / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)
    
    # Calculate segment start times with overlap
    current_time = 0.0
    segment_index = 0
    
    while current_time < duration:
        start_time = current_time
        end_time = min(start_time + videomae_segment_duration, duration)
        
        # Skip segments that are too short (less than 1 second)
        if (end_time - start_time) < 1.0:
            break
        
        # Extract exactly 16 frames for VideoMAE
        # Sample uniformly across the segment duration
        try:
            segment_frames = extract_segment_frames(
                video_path,
                str(segments_dir / f"seg_{segment_index:04d}"),
                start_time,
                end_time - start_time,
                num_frames=16  # VideoMAE requirement
            )
            
            segments.append({
                "index": segment_index,
                "start_time": start_time,
                "end_time": end_time,
                "frames": segment_frames,
                "tier": 1,  # Tier 1: sparse scan
                "num_frames": 16
            })
            
            segment_index += 1
            
        except Exception as e:
            logger.warning(f"Failed to extract segment at {start_time:.2f}s: {e}")
        
        # Move to next segment with stride (overlap)
        current_time += videomae_stride
    
    state["segments"] = segments
    state["videomae_config"] = {
        "segment_duration": videomae_segment_duration,
        "stride": videomae_stride,
        "frames_per_segment": 16,
        "total_segments": len(segments)
    }
    
    logger.info(f"Created {len(segments)} VideoMAE segments ({videomae_segment_duration}s window, {videomae_stride}s stride)")
    logger.info(f"Segment overlap: {((videomae_segment_duration - videomae_stride) / videomae_segment_duration * 100):.1f}%")
    
    return state
