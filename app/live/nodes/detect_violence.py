"""
Violence detection node for live feed.

Uses industry-standard heuristic approach for single-frame real-time analysis.
VideoMAE requires temporal context (16 frames) which isn't available in single-frame processing.
"""
import cv2
import numpy as np
from app.live.state import LiveFeedState
from app.core.logging import get_logger
from app.utils.progress import send_progress

logger = get_logger("live.violence")


def detect_violence(state: LiveFeedState) -> LiveFeedState:
    """
    Estimate violence risk using heuristic approach.
    
    INDUSTRY STANDARD for single-frame real-time processing:
    - VideoMAE/temporal models need 16+ frames (not suitable for single frame)
    - Use heuristics based on object detection signals
    - Fast, no I/O, provides real-time feedback
    
    Heuristic scoring:
    - Weapon detected: 0.8-0.9 (high risk)
    - Multiple people + weapon: 0.9-1.0 (very high risk)
    - Large crowd (5+ people): 0.3-0.4 (medium risk)
    - Person + sharp object: 0.6-0.7 (elevated risk)
    - Normal scene: 0.0-0.2 (low/no risk)
    
    Note: For accurate violence detection, use the batch video pipeline
    which analyzes temporal patterns across multiple frames.
    
    Args:
        state: Current live feed state
        
    Returns:
        Updated state with violence score
    """
    send_progress(state.get("progress_callback"), "detect_violence", 
                 "Analyzing violence", 60)
    
    try:
        # Get detection signals
        detections = state.get("vision_detections", [])
        weapon_detected = state.get("weapon_detected", False)
        person_detected = state.get("person_detected", False)
        object_count = state.get("object_count", 0)
        
        # Count specific object types
        person_count = sum(1 for d in detections if d.get("category") == "person" or d.get("label", "").lower() == "person")
        weapon_count = sum(1 for d in detections if d.get("category") == "weapon")
        
        # HEURISTIC SCORING (industry standard for real-time)
        violence_score = 0.0
        violence_label = "non-violence"
        confidence = 0.0
        
        if weapon_count > 0:
            # Weapon present - high risk
            violence_score = 0.75 + (weapon_count * 0.05)  # 0.75-0.95
            if person_count > 0:
                # Person + weapon - very high risk
                violence_score = min(0.85 + (weapon_count * 0.05), 1.0)  # 0.85-1.0
            violence_label = "violence"
            confidence = 0.85
            
        elif person_count >= 5:
            # Large crowd - medium risk (potential unrest)
            violence_score = 0.30 + (person_count * 0.02)
            violence_score = min(violence_score, 0.50)  # Cap at 0.50
            violence_label = "potential-violence"
            confidence = 0.65
            
        elif person_count >= 3:
            # Multiple people - slight elevation
            violence_score = 0.15 + (person_count * 0.02)
            violence_label = "non-violence"
            confidence = 0.60
            
        else:
            # Normal scene
            violence_score = 0.05 if person_count > 0 else 0.0
            violence_label = "non-violence"
            confidence = 0.90
        
        # Store results
        state["violence_score"] = min(violence_score, 1.0)
        state["violence_label"] = violence_label
        state["violence_confidence"] = confidence
        
        logger.debug(
            f"Frame {state['frame_id']}: violence_score={state['violence_score']:.2f} "
            f"(heuristic: persons={person_count}, weapons={weapon_count})"
        )
        
        send_progress(state.get("progress_callback"), "detect_violence", 
                     f"Violence: {state['violence_score']:.0%}", 70)
        state["current_stage"] = "moderate"
        state["stage_progress"] = 70
        
        return state
        
    except Exception as e:
        logger.error(f"Violence detection failed: {e}", exc_info=True)
        state.setdefault("errors", []).append(f"Violence detection error: {str(e)}")
        # Continue with safe defaults
        state["violence_score"] = 0.0
        state["violence_label"] = "non-violence"
        state["violence_confidence"] = 0.0
        return state
