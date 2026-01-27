"""
Video ingestion node - validate, normalize, and extract metadata.
Normalizes video to consistent format for downstream models:
- Constant FPS (30fps)
- Stable resolution (720p, preserving aspect ratio)
- Extract audio to mono 16kHz WAV for ASR
"""
import uuid
from pathlib import Path
from app.pipeline.state import PipelineState
from app.core.config import settings
from app.core.logging import get_logger
from app.utils.video import validate_video_file, create_working_directory
from app.utils.ffmpeg import get_video_metadata, normalize_video
from app.utils.progress import send_progress

logger = get_logger("node.ingest")


def ingest_video(state: PipelineState) -> PipelineState:
    """
    Ingest video: validate, normalize format, extract metadata.
    
    Normalization ensures consistent inputs for all downstream models:
    - VideoMAE expects consistent frame timing
    - Whisper likes clean 16kHz mono audio
    - YOLO performs better on normalized resolution
    """
    logger.info("=== Ingest Video Node ===")
    
    # Send progress update
    send_progress(state.get("progress_callback"), "ingest_video", "Validating video file", 10)
    
    video_path = state["video_path"]
    
    # Validate video file
    if not validate_video_file(video_path):
        state["errors"] = state.get("errors", []) + ["Invalid video file"]
        return state
    
    # Use existing video_id from state (passed from API) or generate new one
    video_id = state.get("video_id") or str(uuid.uuid4())
    state["video_id"] = video_id
    
    # Create working directory using the video_id
    work_dir = create_working_directory(settings.temp_dir, video_id)
    state["work_dir"] = work_dir
    
    # Extract original video metadata
    try:
        send_progress(state.get("progress_callback"), "ingest_video", "Extracting video metadata", 30)
        
        original_metadata = get_video_metadata(video_path)
        logger.info(f"Original video metadata: {original_metadata}")
        
        # Store original metadata for reference
        state["original_metadata"] = original_metadata
        
    except Exception as e:
        logger.error(f"Failed to extract metadata: {e}")
        state["errors"] = state.get("errors", []) + [f"Metadata extraction failed: {e}"]
        return state
    
    # Normalize video for consistent downstream processing
    try:
        send_progress(state.get("progress_callback"), "ingest_video", "Normalizing video format", 60)
        
        normalized_path = str(Path(work_dir) / "normalized.mp4")
        audio_path = str(Path(work_dir) / "audio.wav")
        
        success = normalize_video(
            input_path=video_path,
            output_path=normalized_path,
            audio_path=audio_path,
            target_fps=30,
            target_height=720
        )
        
        if not success:
            logger.warning("Video normalization failed, using original video")
            state["video_path"] = video_path
            state["audio_path"] = None
        else:
            logger.info("Video normalized successfully")
            state["video_path"] = normalized_path  # Use normalized video for all downstream nodes
            state["audio_path"] = audio_path if Path(audio_path).exists() else None
            
            # Get metadata from normalized video
            normalized_metadata = get_video_metadata(normalized_path)
            state["duration"] = normalized_metadata["duration"]
            state["fps"] = normalized_metadata["fps"]
            state["width"] = normalized_metadata["width"]
            state["height"] = normalized_metadata["height"]
            
            # IMPORTANT: Use original metadata for has_audio since we stripped audio from normalized video
            state["has_audio"] = original_metadata["has_audio"]
            
            logger.info(f"Normalized video metadata: {normalized_metadata}")
            logger.info(f"Audio track: {'present' if state['has_audio'] else 'not present'}")
        
    except Exception as e:
        logger.error(f"Failed to normalize video: {e}")
        # Fall back to original video
        state["video_path"] = video_path
        state["audio_path"] = None
        state["duration"] = original_metadata["duration"]
        state["fps"] = original_metadata["fps"]
        state["width"] = original_metadata["width"]
        state["height"] = original_metadata["height"]
        state["has_audio"] = original_metadata["has_audio"]
    
    # Initialize collections
    state["segments"] = []
    state["sampled_frames"] = []
    state["vision_detections"] = []
    state["violence_segments"] = []
    state["ocr_results"] = []
    state["transcript_moderation"] = []
    state["ocr_moderation"] = []
    state["errors"] = state.get("errors", [])
    
    logger.info(f"Video ingested: {video_id}, duration: {state['duration']:.2f}s, fps: {state['fps']}, resolution: {state['width']}x{state['height']}")
    
    return state
