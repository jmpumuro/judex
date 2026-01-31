"""
Violence detection node.
"""
from pathlib import Path
from app.pipeline.state import PipelineState
from app.core.logging import get_logger
from app.models import get_violence_detector
from app.utils.hashing import generate_violence_id
from app.utils.progress import send_progress, save_stage_output, format_stage_output
from app.utils.ffmpeg import create_labeled_video

logger = get_logger("node.violence")


def run_violence_model(state: PipelineState) -> PipelineState:
    """Run violence detection model on video segments."""
    logger.info("=== Violence Detection Node ===")
    
    send_progress(state.get("progress_callback"), "violence_detection", "Loading violence detection model", 40)
    
    segments = state.get("segments", [])
    
    if not segments:
        logger.warning("No video segments available")
        return state
    
    detector = get_violence_detector()
    
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
    
    # Save stage output for real-time retrieval
    max_score = max([s["violence_score"] for s in violence_segments]) if violence_segments else 0
    high_violence_segments = [s for s in violence_segments if s["violence_score"] > 0.5]
    
    save_stage_output(state.get("video_id"), "violence", format_stage_output(
        "violence",
        segments_analyzed=len(violence_segments),
        max_violence_score=round(max_score, 3),
        high_violence_count=len(high_violence_segments),
        # Full violence segments list (for frontend compatibility)
        violence_segments=[
            {
                "start_time": s["start_time"],
                "end_time": s["end_time"],
                "violence_score": round(s["violence_score"], 3),
                "score": round(s["violence_score"], 3),  # Alias for compatibility
                "label": s.get("label"),
                "id": s.get("id"),
                "segment_index": s.get("segment_index")
            }
            for s in violence_segments
        ],
        # Include high-scoring segments for preview
        high_violence_segments=[
            {
                "start_time": s["start_time"],
                "end_time": s["end_time"],
                "score": round(s["violence_score"], 3),
                "label": s.get("label")
            }
            for s in high_violence_segments
        ],
        # Summary per segment
        segment_scores=[
            {"index": s["segment_index"], "score": round(s["violence_score"], 3)}
            for s in violence_segments
        ]
    ))
    
    return state
