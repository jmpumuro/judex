"""
Audio ASR transcription node.
"""
from pathlib import Path
from app.pipeline.state import PipelineState
from app.core.logging import get_logger
from app.models import get_whisper_asr
from app.utils.ffmpeg import extract_audio
from app.utils.progress import send_progress, save_stage_output, format_stage_output

logger = get_logger("node.asr")


def run_audio_asr(state: PipelineState) -> PipelineState:
    """Run Whisper ASR on video audio."""
    logger.info("=== Audio ASR Node ===")
    
    send_progress(state.get("progress_callback"), "audio_transcription", "Extracting audio", 50)
    
    video_path = state["video_path"]
    work_dir = state["work_dir"]
    has_audio = state.get("has_audio", False)
    
    if not has_audio:
        logger.info("Video has no audio track")
        state["transcript"] = {"full_text": "", "chunks": []}
        return state
    
    # Check if audio was already extracted during normalization
    pre_extracted_audio = state.get("audio_path")
    
    if pre_extracted_audio and Path(pre_extracted_audio).exists():
        logger.info(f"Using pre-extracted audio from normalization: {pre_extracted_audio}")
        audio_path = pre_extracted_audio
    else:
        # Extract audio if not already done
        audio_dir = Path(work_dir) / "audio"
        audio_path = str(audio_dir / "audio.wav")
        
        try:
            extract_audio(video_path, audio_path)
            logger.info(f"Audio extracted to {audio_path}")
        except Exception as e:
            logger.error(f"Audio extraction failed: {e}")
            state["errors"] = state.get("errors", []) + [f"Audio extraction failed: {e}"]
            state["transcript"] = {"full_text": "", "chunks": []}
            return state
    
    # Transcribe audio
    asr = get_whisper_asr()
    
    send_progress(state.get("progress_callback"), "audio_transcription", "Transcribing audio with Whisper", 70)
    
    try:
        transcript = asr.transcribe(audio_path)
        state["transcript"] = transcript
        
        logger.info(f"Transcribed {len(transcript.get('chunks', []))} audio chunks")
        if transcript.get("full_text"):
            logger.info(f"Transcript preview: {transcript['full_text'][:200]}...")
        else:
            logger.warning("Transcription completed but no text was detected")
        
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        state["errors"] = state.get("errors", []) + [f"Transcription failed: {e}"]
        state["transcript"] = {"full_text": "", "chunks": []}
    
    # Save stage output for real-time retrieval
    transcript = state.get("transcript", {})
    chunks = transcript.get("chunks", [])
    
    save_stage_output(state.get("video_id"), "audio_asr", format_stage_output(
        "audio_asr",
        has_audio=has_audio,
        full_text=transcript.get("full_text", "")[:500],  # First 500 chars
        chunks_count=len(chunks),
        # Include first 10 chunks for preview
        chunks=[
            {
                "text": c.get("text", ""),
                "start_time": c.get("start_time"),
                "end_time": c.get("end_time")
            }
            for c in chunks[:10]
        ],
        total_duration=chunks[-1]["end_time"] if chunks else 0
    ))
    
    return state
