"""
Violence detection node.
"""
from pathlib import Path
from app.pipeline.state import PipelineState
from app.core.config import settings
from app.core.logging import get_logger
from app.utils.hashing import generate_violence_id
from app.utils.progress import send_progress
from app.utils.ffmpeg import create_labeled_video

logger = get_logger("node.violence")


# Singleton detector instance
_detector = None


def get_detector():
    """Get or create violence detector instance."""
    global _detector
    if _detector is None:
        if settings.use_xclip_violence:
            from app.models.violence_xclip import XCLIPViolenceDetector
            _detector = XCLIPViolenceDetector()
            logger.info("Using X-CLIP violence detector")
        else:
            from app.models.violence import ViolenceDetector
            _detector = ViolenceDetector()
            logger.info("Using VideoMAE violence detector")
        _detector.load()
    return _detector


def run_violence_model(state: PipelineState) -> PipelineState:
    """Run violence detection model on video segments."""
    logger.info("=== Violence Detection Node ===")
    
    send_progress(state.get("progress_callback"), "violence_detection", "Loading violence detection model", 40)
    
    segments = state.get("segments", [])
    
    if not segments:
        logger.warning("No video segments available")
        return state
    
    detector = get_detector()
    
    send_progress(state.get("progress_callback"), "violence_detection", f"Analyzing {len(segments)} video segments", 60)
    
    violence_segments = []
    
    for segment in segments:
        segment_index = segment["index"]
        start_time = segment["start_time"]
        end_time = segment["end_time"]
        frames = segment["frames"]
        
        # Analyze segment
        result = detector.analyze_segment(
            frames,
            start_time,
            end_time - start_time
        )
        
        # Add ID
        result["id"] = generate_violence_id(segment_index)
        result["segment_index"] = segment_index
        
        violence_segments.append(result)
        
        if result["violence_score"] > 0.3:
            logger.info(f"Segment {segment_index} ({start_time:.1f}-{end_time:.1f}s): "
                       f"violence_score={result['violence_score']:.2f}, label={result['label']}")
    
    state["violence_segments"] = violence_segments
    
    # Summary
    high_violence = [s for s in violence_segments if s["violence_score"] > 0.5]
    logger.info(f"Analyzed {len(violence_segments)} segments, {len(high_violence)} with high violence scores")
    
    # Update labeled video to include violence timeline markers
    if high_violence and state.get("labeled_video_path"):
        try:
            send_progress(state.get("progress_callback"), "violence_detection", "Adding violence timeline markers to video", 65)
            
            video_path = state["video_path"]
            work_dir = state["work_dir"]
            fps = state.get("fps", 30.0)
            vision_detections = state.get("vision_detections", [])
            
            # Regenerate labeled video with violence timeline
            labeled_video_path = str(Path(work_dir) / "labeled.mp4")
            create_labeled_video(video_path, labeled_video_path, vision_detections, fps, violence_segments)
            
            logger.info(f"Updated labeled video with {len(high_violence)} violence markers")
            
        except Exception as e:
            logger.error(f"Failed to update labeled video with violence timeline: {e}")
            # Don't fail the pipeline if this fails
    
    return state
