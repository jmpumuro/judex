"""
Video ingestion node - validate, normalize, and extract metadata.

Normalizes video to consistent format for downstream models:
- Constant FPS (30fps)
- Stable resolution (720p, preserving aspect ratio)
- Extract audio to mono 16kHz WAV for ASR
- Upload original video to storage for immediate viewing

Industry Standard: Uses LangGraph config for callbacks (not state).
"""
import uuid
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
    
    # Check if already processed (resuming from checkpoint)
    if state.get("duration") and state.get("work_dir") and state.get("fps"):
        logger.info("Ingest already complete (from checkpoint), skipping")
        send_progress(config, "ingest_video", "Using cached result", 100)
        
        video_id = state.get("video_id")
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
    
    # Send progress via config (industry standard)
    send_progress(config, "ingest_video", "Validating video file", 10)
    
    video_path = state["video_path"]
    
    # Validate video file
    if not validate_video_file(video_path):
        state["errors"] = state.get("errors", []) + ["Invalid video file"]
        return state
    
    # Use existing video_id from state (passed from API) or generate new one
    video_id = state.get("video_id") or str(uuid.uuid4())
    state["video_id"] = video_id
    
    # Upload original video to storage immediately for early viewing
    if not state.get("uploaded_video_path"):
        try:
            send_progress(config, "ingest_video", "Uploading original video", 15)
            
            storage = get_storage_service()
            uploaded_path = storage.upload_video(video_path, video_id)
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
        
        original_metadata = get_video_metadata(video_path)
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


# Legacy wrapper for backward compatibility
def ingest_video(state: PipelineState) -> PipelineState:
    """Legacy wrapper - calls impl without config."""
    return ingest_video_impl(state, None)
