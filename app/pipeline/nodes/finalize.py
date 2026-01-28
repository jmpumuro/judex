"""
Finalize node - prepare final output using unified result format.
"""
from app.pipeline.state import PipelineState
from app.core.logging import get_logger
from app.utils.progress import send_progress

logger = get_logger("node.finalize")


def finalize(state: PipelineState) -> PipelineState:
    """
    Prepare final output JSON.
    
    Uses unified format from criteria_scores (set by generic_fuse_policy).
    """
    logger.info("=== Finalize Node ===")
    
    send_progress(state.get("progress_callback"), "finalize", "Finalizing results", 98)
    
    # Get data from state (unified format from fusion)
    criteria_scores = state.get("criteria_scores", {})
    violations = state.get("violations", [])
    verdict = state.get("verdict", "UNKNOWN")
    confidence = state.get("confidence", 0.0)
    evidence = state.get("evidence", {})
    report = state.get("report", "")
    
    # Build final result
    result = {
        "verdict": verdict,
        "confidence": round(confidence, 3),
        "criteria": criteria_scores,  # Already in unified format
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
    
    # Add timings
    if "timings" in state:
        result["timings"] = state["timings"]
        result["metadata"]["processing_time"] = state["timings"].get("total_seconds", 0)
    
    state["result"] = result
    
    logger.info(f"Pipeline complete: verdict={verdict}")
    
    return state
