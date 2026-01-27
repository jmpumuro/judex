"""
Content moderation node for live feed.

Applies policy rules and determines verdict.
"""
from app.live.state import LiveFeedState
from app.core.logging import get_logger
from app.utils.progress import send_progress

logger = get_logger("live.moderate")


def moderate_content(state: LiveFeedState) -> LiveFeedState:
    """
    Apply content policy and determine verdict.
    
    This node:
    1. Evaluates policy criteria based on detections
    2. Determines violations
    3. Assigns verdict (SAFE / UNSAFE / NEEDS_REVIEW)
    4. Calculates event priority
    
    Args:
        state: Current live feed state
        
    Returns:
        Updated state with verdict and violations
    """
    send_progress(state.get("progress_callback"), "moderate", 
                 "Applying policy", 80)
    
    try:
        # Extract detection results
        violence_score = state.get("violence_score", 0.0)
        weapon_detected = state.get("weapon_detected", False)
        object_count = state.get("object_count", 0)
        
        # Initialize criterion scores (same as video pipeline)
        criterion_scores = {
            "violence": violence_score,
            "graphic_content": 0.0,  # Not analyzed in live feed yet
            "profanity": 0.0,  # Not analyzed in live feed yet
            "hate_speech": 0.0,  # Not analyzed in live feed yet
            "weapon_presence": 1.0 if weapon_detected else 0.0,
        }
        
        state["criterion_scores"] = criterion_scores
        
        # Detect violations
        violations = []
        
        if violence_score > 0.7:
            violations.append({
                "type": "violence",
                "severity": "high",
                "confidence": violence_score,
                "description": f"High violence score: {violence_score:.2f}"
            })
        elif violence_score > 0.4:
            violations.append({
                "type": "violence",
                "severity": "medium",
                "confidence": violence_score,
                "description": f"Moderate violence score: {violence_score:.2f}"
            })
        
        if weapon_detected:
            violations.append({
                "type": "weapon",
                "severity": "high",
                "confidence": 0.9,  # YOLO confidence is already filtered
                "description": "Weapon detected in frame"
            })
        
        state["violations"] = violations
        
        # Determine verdict
        if len(violations) == 0:
            verdict = "SAFE"
            event_priority = "low"
            save_as_event = False
        elif any(v["severity"] == "high" for v in violations):
            verdict = "UNSAFE"
            event_priority = "critical" if weapon_detected else "high"
            save_as_event = True
        elif violence_score > 0.4:
            verdict = "NEEDS_REVIEW"
            event_priority = "medium"
            save_as_event = True
        else:
            verdict = "SAFE"
            event_priority = "low"
            save_as_event = False
        
        state["verdict"] = verdict
        state["event_priority"] = event_priority
        state["save_as_event"] = save_as_event
        
        # Build evidence
        evidence = {
            "detections": state.get("vision_detections", []),
            "violence_score": violence_score,
            "weapon_detected": weapon_detected,
            "object_count": object_count,
        }
        state["evidence"] = evidence
        
        logger.info(
            f"Frame {state['frame_id']}: verdict={verdict}, "
            f"violations={len(violations)}, priority={event_priority}"
        )
        
        send_progress(state.get("progress_callback"), "moderate", 
                     f"Verdict: {verdict}", 90)
        state["current_stage"] = "emit"
        state["stage_progress"] = 90
        
        return state
        
    except Exception as e:
        logger.error(f"Content moderation failed: {e}", exc_info=True)
        state.setdefault("errors", []).append(f"Moderation error: {str(e)}")
        state["verdict"] = "NEEDS_REVIEW"
        state["violations"] = []
        state["event_priority"] = "medium"
        return state
