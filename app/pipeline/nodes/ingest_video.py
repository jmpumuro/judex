"""
Media ingestion node - validate, normalize, and extract metadata.

Supports both VIDEO and IMAGE inputs with unified processing:

VIDEO:
- Constant FPS (30fps)
- Stable resolution (720p, preserving aspect ratio)
- Extract audio to mono 16kHz WAV for ASR
- Upload original video to storage for immediate viewing

IMAGE:
- Validate image format and integrity
- Extract image metadata (resolution, format)
- Prepare single-frame processing path
- Upload to storage for viewing

Industry Standard: Uses LangGraph config for callbacks (not state).
"""
import uuid
import shutil
from pathlib import Path
from typing import Optional
from langchain_core.runnables import RunnableConfig

from app.pipeline.state import PipelineState
from app.pipeline.callbacks import send_progress
from app.core.config import settings
from app.core.logging import get_logger
from app.utils.video import validate_video_file, create_working_directory
from app.utils.ffmpeg import get_video_metadata, normalize_video
from app.utils.progress import save_stage_output, format_stage_output
from app.utils.storage import get_storage_service
from app.utils.media import (
    MediaType, detect_media_type, is_image, is_video,
    get_image_metadata, validate_media_file
)

logger = get_logger("node.ingest")


def _load_cached_stage_output(video_id: str, stage_name: str) -> dict:
    """
    Load cached stage output from database.
    
    Industry standard: Retrieve previous run data to display in UI
    when reprocessing with cached stages.
    """
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


def ingest_video_impl(state: PipelineState, config: Optional[RunnableConfig] = None) -> PipelineState:
    """
    Ingest video: validate, normalize format, extract metadata.
    
    Industry Standard: Receives config parameter for callbacks.
    Progress is sent via config["callbacks"], not stored in state.
    
    Normalization ensures consistent inputs for all downstream models:
    - VideoMAE expects consistent frame timing
    - Whisper likes clean 16kHz mono audio
    - YOLO performs better on normalized resolution
    """
    logger.info("=== Ingest Video Node ===")
    
    video_id = state.get("video_id")
    is_reprocessing = state.get("is_reprocessing", False)
    
    # Check if already processed (resuming from checkpoint)
    # For reprocessing, only skip if work_dir actually exists on disk
    work_dir_exists = state.get("work_dir") and Path(state.get("work_dir")).exists()
    has_metadata = state.get("duration") and state.get("fps")
    
    if has_metadata and work_dir_exists and not is_reprocessing:
        logger.info("Ingest already complete (from checkpoint), skipping")
        send_progress(config, "ingest_video", "Using cached result", 100)
        
        if video_id:
            # Load cached stage output from DB for UI display
            cached_output = _load_cached_stage_output(video_id, "ingest")
            
            # Save stage output with cached data for UI
            save_stage_output(video_id, "ingest", format_stage_output(
                "ingest",
                status="cached",
                cached=True,
                cache_source="checkpoint",
                duration=state.get("duration"),
                fps=state.get("fps"),
                width=state.get("width"),
                height=state.get("height"),
                has_audio=state.get("has_audio"),
                original_metadata=state.get("original_metadata") or cached_output.get("original_metadata"),
                video_path=str(state.get("video_path", "")),
                work_dir=str(state.get("work_dir", "")),
                uploaded_video_path=state.get("uploaded_video_path"),
                original_processing_time=cached_output.get("processing_time"),
            ))
        return state
    
    # For reprocessing with existing metadata, preserve it but recreate work_dir
    if is_reprocessing and has_metadata:
        logger.info("Reprocessing mode: preserving metadata, recreating work directory")
        send_progress(config, "ingest_video", "Using cached metadata (reprocessing)", 50)
        
        video_path = state["video_path"]
        
        # Create working directory
        video_id = state.get("video_id") or str(uuid.uuid4())
        state["video_id"] = video_id
        work_dir = create_working_directory(settings.temp_dir, video_id)
        state["work_dir"] = work_dir
        
        # Normalize video for frame extraction (needed for analysis stages)
        try:
            normalized_path = str(Path(work_dir) / "normalized.mp4")
            audio_path = str(Path(work_dir) / "audio.wav")
            
            send_progress(config, "ingest_video", "Normalizing video (reprocessing)", 70)
            
            success = normalize_video(
                input_path=video_path,
                output_path=normalized_path,
                audio_path=audio_path,
                target_fps=30,
                target_height=720
            )
            
            if success:
                state["video_path"] = normalized_path
                state["audio_path"] = audio_path if Path(audio_path).exists() else None
                logger.info("Video normalized for reprocessing")
            else:
                state["audio_path"] = None
                logger.warning("Normalization failed, using original video")
                
        except Exception as e:
            logger.error(f"Failed to normalize video during reprocessing: {e}")
            state["audio_path"] = None
        
        # Initialize/clear collections for fresh analysis
        state["segments"] = []
        state["sampled_frames"] = []
        state["vision_detections"] = []
        state["yoloworld_detections"] = []
        state["violence_segments"] = []
        state["ocr_results"] = []
        state["transcript_moderation"] = []
        state["ocr_moderation"] = []
        state["errors"] = state.get("errors", [])
        
        # Save stage output
        save_stage_output(video_id, "ingest", format_stage_output(
            "ingest",
            status="reprocessed",
            cached=False,
            reprocessing=True,
            duration=state.get("duration"),
            fps=state.get("fps"),
            width=state.get("width"),
            height=state.get("height"),
            has_audio=state.get("has_audio"),
            video_path=str(state.get("video_path")),
            work_dir=str(work_dir),
            uploaded_video_path=state.get("uploaded_video_path")
        ))
        
        send_progress(config, "ingest_video", "Metadata preserved (reprocessing)", 100)
        return state
    
    # Send progress via config (industry standard)
    send_progress(config, "ingest_video", "Validating media file", 10)
    
    # Support both video_path and media_path (unified)
    media_path = state.get("media_path") or state.get("video_path")
    state["video_path"] = media_path  # Maintain backward compatibility
    state["media_path"] = media_path
    
    # Detect media type (video or image)
    media_type = detect_media_type(media_path)
    state["media_type"] = media_type.value
    logger.info(f"Detected media type: {media_type.value} for {media_path}")
    
    # Branch based on media type
    if media_type == MediaType.IMAGE:
        return _ingest_image(state, config, video_id)
    
    # === VIDEO PROCESSING ===
    # Validate video file
    if not validate_video_file(media_path):
        state["errors"] = state.get("errors", []) + ["Invalid video file"]
        return state
    
    # Use existing video_id from state (passed from API) or generate new one
    if not video_id:
        video_id = str(uuid.uuid4())
    state["video_id"] = video_id
    
    # Upload original video to storage immediately for early viewing
    if not state.get("uploaded_video_path"):
        try:
            send_progress(config, "ingest_video", "Uploading original video", 15)
            
            storage = get_storage_service()
            uploaded_path = storage.upload_video(media_path, video_id)
            state["uploaded_video_path"] = uploaded_path
            logger.info(f"Original video uploaded to storage: {uploaded_path}")
            
            # INDUSTRY STANDARD: Persist artifact path directly to database
            try:
                from app.api.evaluations import EvaluationRepository
                EvaluationRepository.update_item(video_id, uploaded_video_path=uploaded_path)
                logger.info(f"Uploaded video path persisted to DB: {uploaded_path}")
            except Exception as db_err:
                logger.warning(f"Failed to persist uploaded_video_path to DB: {db_err}")
            
        except Exception as e:
            logger.warning(f"Failed to upload original video to storage: {e}")
    else:
        logger.info(f"Original video already uploaded: {state['uploaded_video_path']}")
    
    # Create working directory using the video_id
    work_dir = create_working_directory(settings.temp_dir, video_id)
    state["work_dir"] = work_dir
    
    # Extract original video metadata
    try:
        send_progress(config, "ingest_video", "Extracting video metadata", 30)
        
        original_metadata = get_video_metadata(media_path)
        logger.info(f"Original video metadata: {original_metadata}")
        state["original_metadata"] = original_metadata
        
    except Exception as e:
        logger.error(f"Failed to extract metadata: {e}")
        state["errors"] = state.get("errors", []) + [f"Metadata extraction failed: {e}"]
        return state
    
    # Normalize video for consistent downstream processing
    try:
        send_progress(config, "ingest_video", "Normalizing video format", 60)
        
        normalized_path = str(Path(work_dir) / "normalized.mp4")
        audio_path = str(Path(work_dir) / "audio.wav")
        
        success = normalize_video(
            input_path=media_path,
            output_path=normalized_path,
            audio_path=audio_path,
            target_fps=30,
            target_height=720
        )
        
        if not success:
            logger.warning("Video normalization failed, using original video")
            state["video_path"] = media_path
            state["audio_path"] = None
        else:
            logger.info("Video normalized successfully")
            state["video_path"] = normalized_path
            state["audio_path"] = audio_path if Path(audio_path).exists() else None
            
            # Get metadata from normalized video
            normalized_metadata = get_video_metadata(normalized_path)
            state["duration"] = normalized_metadata["duration"]
            state["fps"] = normalized_metadata["fps"]
            state["width"] = normalized_metadata["width"]
            state["height"] = normalized_metadata["height"]
            
            # Use original metadata for has_audio
            state["has_audio"] = original_metadata["has_audio"]
            
            logger.info(f"Normalized video metadata: {normalized_metadata}")
            logger.info(f"Audio track: {'present' if state['has_audio'] else 'not present'}")
        
    except Exception as e:
        logger.error(f"Failed to normalize video: {e}")
        state["video_path"] = media_path
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
    
    # Persist video metadata to database
    try:
        from app.api.evaluations import EvaluationRepository
        EvaluationRepository.update_item(
            video_id,
            duration=state.get("duration"),
            fps=state.get("fps"),
            width=state.get("width"),
            height=state.get("height"),
            has_audio=state.get("has_audio")
        )
        logger.info(f"Video metadata persisted to DB")
    except Exception as db_err:
        logger.warning(f"Failed to persist video metadata to DB: {db_err}")
    
    # Save stage output for real-time retrieval
    save_stage_output(video_id, "ingest", format_stage_output(
        "ingest",
        duration=state.get("duration"),
        fps=state.get("fps"),
        width=state.get("width"),
        height=state.get("height"),
        has_audio=state.get("has_audio"),
        original_metadata=state.get("original_metadata"),
        video_path=str(state.get("video_path")),
        work_dir=str(state.get("work_dir")),
        uploaded_video_path=state.get("uploaded_video_path")
    ))
    
    return state


def _ingest_image(state: PipelineState, config: Optional[RunnableConfig], video_id: Optional[str]) -> PipelineState:
    """
    Ingest an image file for analysis.
    
    Images are treated as single-frame media - detection models work directly
    on the image without temporal processing.
    
    Args:
        state: Pipeline state with media_path/video_path
        config: LangGraph config for callbacks
        video_id: Optional pre-assigned ID
        
    Returns:
        Updated state with image metadata
    """
    from app.pipeline.callbacks import send_progress
    
    media_path = state.get("media_path") or state.get("video_path")
    
    send_progress(config, "ingest_video", "Validating image file", 20)
    
    # Validate image
    is_valid, error = validate_media_file(media_path)
    if not is_valid:
        state["errors"] = state.get("errors", []) + [error or "Invalid image file"]
        return state
    
    # Generate or use provided ID
    if not video_id:
        video_id = str(uuid.uuid4())
    state["video_id"] = video_id
    
    # Create working directory
    work_dir = create_working_directory(settings.temp_dir, video_id)
    state["work_dir"] = work_dir
    
    send_progress(config, "ingest_video", "Extracting image metadata", 40)
    
    # Get image metadata
    try:
        metadata = get_image_metadata(media_path)
        state["width"] = metadata["width"]
        state["height"] = metadata["height"]
        state["duration"] = 0  # Images have no duration
        state["fps"] = 1  # Treat as single frame
        state["has_audio"] = False
        state["original_metadata"] = metadata
        
        logger.info(f"Image metadata: {metadata['width']}x{metadata['height']}, format: {metadata.get('format')}")
        
    except Exception as e:
        logger.error(f"Failed to get image metadata: {e}")
        state["errors"] = state.get("errors", []) + [f"Image metadata extraction failed: {e}"]
        return state
    
    send_progress(config, "ingest_video", "Uploading image to storage", 60)
    
    # Upload image to storage
    if not state.get("uploaded_video_path"):
        try:
            storage = get_storage_service()
            # Use image upload (same method, different extension handling)
            uploaded_path = storage.upload_video(media_path, video_id)
            state["uploaded_video_path"] = uploaded_path
            logger.info(f"Image uploaded to storage: {uploaded_path}")
            
            # Persist to database
            try:
                from app.api.evaluations import EvaluationRepository
                EvaluationRepository.update_item(video_id, uploaded_video_path=uploaded_path)
            except Exception as db_err:
                logger.warning(f"Failed to persist uploaded_video_path to DB: {db_err}")
                
        except Exception as e:
            logger.warning(f"Failed to upload image to storage: {e}")
    
    send_progress(config, "ingest_video", "Preparing image for analysis", 80)
    
    # Copy image to work directory for processing
    image_ext = Path(media_path).suffix
    processed_path = str(Path(work_dir) / f"frame_0000_0{image_ext}")
    try:
        shutil.copy2(media_path, processed_path)
        state["video_path"] = processed_path  # Point to copied image
        state["media_path"] = processed_path
    except Exception as e:
        logger.warning(f"Failed to copy image: {e}, using original path")
        state["video_path"] = media_path
    
    # Initialize collections (image has no audio/violence temporal data)
    state["segments"] = []
    state["sampled_frames"] = [{
        "path": processed_path,
        "timestamp": 0,
        "frame_index": 0,
    }]
    state["vision_detections"] = []
    state["yoloworld_detections"] = []
    state["violence_segments"] = []  # Will be empty for images
    state["transcript"] = {"full_text": "", "chunks": []}  # No audio
    state["ocr_results"] = []
    state["transcript_moderation"] = []
    state["ocr_moderation"] = []
    state["audio_path"] = None
    state["errors"] = state.get("errors", [])
    
    logger.info(f"Image ingested: {video_id}, resolution: {state['width']}x{state['height']}")
    
    # Persist metadata to database
    try:
        from app.api.evaluations import EvaluationRepository
        EvaluationRepository.update_item(
            video_id,
            duration=0,
            fps=1,
            width=state.get("width"),
            height=state.get("height"),
            has_audio=False
        )
    except Exception as db_err:
        logger.warning(f"Failed to persist image metadata to DB: {db_err}")
    
    # Save stage output
    save_stage_output(video_id, "ingest", format_stage_output(
        "ingest",
        media_type="image",
        duration=0,
        fps=1,
        width=state.get("width"),
        height=state.get("height"),
        has_audio=False,
        original_metadata=state.get("original_metadata"),
        video_path=str(state.get("video_path")),
        work_dir=str(work_dir),
        uploaded_video_path=state.get("uploaded_video_path"),
    ))
    
    send_progress(config, "ingest_video", "Image ready for analysis", 100)
    
    return state


# Legacy wrapper for backward compatibility
def ingest_video(state: PipelineState) -> PipelineState:
    """Legacy wrapper - calls impl without config."""
    return ingest_video_impl(state, None)
