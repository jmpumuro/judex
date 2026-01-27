"""
Emit results node for live feed.

Finalizes and formats the result for API response.
"""
import time
from app.live.state import LiveFeedState
from app.core.logging import get_logger
from app.utils.progress import send_progress

logger = get_logger("live.emit")


def emit_result(state: LiveFeedState) -> LiveFeedState:
    """
    Finalize and emit the analysis result.
    
    This node:
    1. Formats the final result object
    2. Calculates processing time
    3. Prepares response for API/frontend
    4. Marks completion
    
    Args:
        state: Current live feed state
        
    Returns:
        Updated state with final result
    """
    send_progress(state.get("progress_callback"), "emit", 
                 "Finalizing result", 95)
    
    try:
        # Calculate processing time
        start_time = state.get("frame_timestamp", time.time())
        processing_time_ms = (time.time() - start_time) * 1000
        state["processing_time_ms"] = processing_time_ms
        
        # Build final result object (matches API contract)
        result = {
            "frame_id": state["frame_id"],
            "stream_id": state.get("stream_id", "default"),
            "timestamp": state["frame_timestamp"],
            
            # Detection results
            "objects": state.get("vision_detections", []),
            "object_count": state.get("object_count", 0),
            "weapon_detected": state.get("weapon_detected", False),
            "person_detected": state.get("person_detected", False),
            
            # Violence analysis
            "violence_score": state.get("violence_score", 0.0),
            "violence_label": state.get("violence_label", "non-violence"),
            "violence_confidence": state.get("violence_confidence", 0.0),
            
            # Policy verdict
            "verdict": state.get("verdict", "SAFE"),
            "violations": state.get("violations", []),
            "criterion_scores": state.get("criterion_scores", {}),
            
            # Evidence
            "evidence": state.get("evidence", {}),
            
            # Metadata
            "frame_width": state.get("frame_width"),
            "frame_height": state.get("frame_height"),
            "processing_time_ms": processing_time_ms,
            "errors": state.get("errors", []),
            
            # Event info
            "save_as_event": state.get("save_as_event", False),
            "event_priority": state.get("event_priority", "low"),
        }
        
        state["result"] = result
        
        logger.info(
            f"Frame {state['frame_id']} analysis complete: "
            f"verdict={result['verdict']}, time={processing_time_ms:.0f}ms, "
            f"objects={result['object_count']}, violence={result['violence_score']:.2f}"
        )
        
        send_progress(state.get("progress_callback"), "complete", 
                     "Analysis complete", 100)
        state["current_stage"] = "complete"
        state["stage_progress"] = 100
        
        return state
        
    except Exception as e:
        logger.error(f"Result emission failed: {e}", exc_info=True)
        state.setdefault("errors", []).append(f"Emission error: {str(e)}")
        
        # Return minimal result
        state["result"] = {
            "frame_id": state["frame_id"],
            "verdict": "NEEDS_REVIEW",
            "error": str(e),
            "processing_time_ms": 0
        }
        return state
