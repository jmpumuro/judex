"""
YOLOE detection node for live feed.

Uses YOLOE (efficient YOLO variant) for real-time object detection
in live streams with optimized performance.
"""
import cv2
import numpy as np
from io import BytesIO
from pathlib import Path
from app.live.state import LiveFeedState
from app.models.yoloe import YOLOEDetector
from app.core.logging import get_logger
from app.utils.progress import send_progress

logger = get_logger("live.yoloe")

# Singleton detector instance (cached across frames for performance)
_detector_instance = None


def get_detector() -> YOLOEDetector:
    """Get or create YOLOE detector instance."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = YOLOEDetector()
        _detector_instance.load()
        logger.info("YOLOE detector loaded for live feed")
    return _detector_instance


def detect_objects_yoloe(state: LiveFeedState) -> LiveFeedState:
    """
    Run YOLOE object detection on the live frame.
    
    OPTIMIZED FOR LIVE FEED:
    - In-memory processing (PIL Image directly)
    - Efficient model variant (YOLOv8n)
    - FP16 inference on GPU
    - No disk I/O
    
    Args:
        state: Current live feed state
        
    Returns:
        Updated state with object detections
    """
    send_progress(state.get("progress_callback"), "detect_objects_yoloe", "Running YOLOE detection", 30)
    
    try:
        # Get detector
        detector = get_detector()
        
        # Decode frame to numpy array (in-memory)
        frame_bytes = state["frame_data"]
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame_img is None:
            raise ValueError("Failed to decode frame for detection")
        
        # Convert to PIL Image for direct prediction (zero I/O)
        from PIL import Image
        frame_rgb = cv2.cvtColor(frame_img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame_rgb)
        
        # Run YOLOE detection directly on PIL Image
        detections = detector.detect_pil(pil_img, timestamp=state["frame_timestamp"])
        
        # Store results
        state["vision_detections"] = detections
        state["object_count"] = len(detections)
        
        # Check for specific categories
        weapon_detected = any(
            d.get("category") == "weapon" for d in detections
        )
        person_detected = any(
            d.get("category") == "person" or d.get("label", "").lower() == "person"
            for d in detections
        )
        
        state["weapon_detected"] = weapon_detected
        state["person_detected"] = person_detected
        
        logger.debug(
            f"Frame {state['frame_id']}: YOLOE detected {len(detections)} objects "
            f"(weapon={weapon_detected}, person={person_detected})"
        )
        
        send_progress(state.get("progress_callback"), "detect_objects_yoloe", 
                     f"{len(detections)} objects detected", 50)
        state["current_stage"] = "detect_violence"
        state["stage_progress"] = 50
        
        return state
        
    except Exception as e:
        logger.error(f"YOLOE detection failed: {e}", exc_info=True)
        state.setdefault("errors", []).append(f"YOLOE detection error: {str(e)}")
        # Continue with empty detections
        state["vision_detections"] = []
        state["object_count"] = 0
        state["weapon_detected"] = False
        state["person_detected"] = False
        return state
