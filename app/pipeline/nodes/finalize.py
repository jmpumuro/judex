"""
Finalize node - prepare final output.
"""
from app.pipeline.state import PipelineState
from app.core.logging import get_logger
from app.utils.progress import send_progress

logger = get_logger("node.finalize")


def finalize(state: PipelineState) -> PipelineState:
    """Prepare final output JSON."""
    logger.info("=== Finalize Node ===")
    
    send_progress(state.get("progress_callback"), "finalize", "Finalizing results", 98)
    
    criterion_scores = state.get("criterion_scores", {})
    violations = state.get("violations", [])
    verdict = state.get("verdict", "UNKNOWN")
    evidence = state.get("evidence", {})
    report = state.get("report", "")
    
    # Build criteria status
    criteria = {}
    for criterion, score in criterion_scores.items():
        if score >= 0.6:
            status = "violation"
        elif score >= 0.3:
            status = "caution"
        else:
            status = "ok"
        
        criteria[criterion] = {
            "score": round(score, 2),
            "status": status
        }
    
    # Build final result
    result = {
        "verdict": verdict,
        "criteria": criteria,
        "violations": violations,
        "evidence": evidence,
        "report": report,
        "metadata": {
            "video_id": state.get("video_id", ""),
            "duration": state.get("duration", 0),
            "fps": state.get("fps", 0),
            "width": state.get("width", 0),
            "height": state.get("height", 0),
            "has_audio": state.get("has_audio", False),
            "frames_analyzed": len(state.get("sampled_frames", [])),
            "segments_analyzed": len(state.get("segments", [])),
            "detections_count": len(state.get("vision_detections", [])),
            "violence_segments_count": len(state.get("violence_segments", [])),
            "ocr_results_count": len(state.get("ocr_results", [])),
        },
        "transcript": {
            "text": state.get("transcript", {}).get("full_text", ""),
            "chunks": state.get("transcript", {}).get("chunks", [])
        }
    }
    
    # Add labeled video path if available
    if state.get("labeled_video_path"):
        result["labeled_video_path"] = state["labeled_video_path"]
    
    # Add timings if available and include in metadata
    if "timings" in state:
        result["timings"] = state["timings"]
        # Also add total processing time to metadata for easy access
        result["metadata"]["processing_time"] = state["timings"].get("total_seconds", 0)
    
    state["result"] = result
    
    logger.info(f"Pipeline complete: verdict={verdict}")
    
    return state
