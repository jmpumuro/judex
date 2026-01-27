"""
Capture and prepare frame for analysis.

This node receives raw frame data and prepares it for detection models.
"""
import cv2
import numpy as np
from io import BytesIO
from app.live.state import LiveFeedState
from app.core.logging import get_logger
from app.utils.progress import send_progress

logger = get_logger("live.capture")


def capture_frame(state: LiveFeedState) -> LiveFeedState:
    """
    Decode and prepare frame for analysis.
    
    This node:
    1. Decodes frame bytes to numpy array
    2. Extracts frame metadata (dimensions, format)
    3. Validates frame quality
    4. Prepares frame for detection models
    
    Args:
        state: Current live feed state
        
    Returns:
        Updated state with decoded frame
    """
    send_progress(state.get("progress_callback"), "capture", "Decoding frame", 10)
    
    try:
        # Decode frame bytes
        frame_bytes = state["frame_data"]
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame_img is None:
            raise ValueError("Failed to decode frame image")
        
        # Extract metadata
        height, width, channels = frame_img.shape
        state["frame_width"] = width
        state["frame_height"] = height
        state["frame_format"] = "bgr"  # OpenCV default
        
        # Store decoded frame in state (for downstream nodes)
        # Note: We store it as bytes in BytesIO to avoid serialization issues
        is_success, buffer = cv2.imencode(".jpg", frame_img)
        if not is_success:
            raise ValueError("Failed to re-encode frame")
        
        state["frame_data"] = buffer.tobytes()  # Update with validated frame
        
        logger.debug(f"Frame {state['frame_id']} decoded: {width}x{height}")
        
        send_progress(state.get("progress_callback"), "capture", "Frame ready", 20)
        state["current_stage"] = "detect_objects"
        state["stage_progress"] = 20
        
        return state
        
    except Exception as e:
        logger.error(f"Frame capture failed: {e}", exc_info=True)
        state.setdefault("errors", []).append(f"Capture error: {str(e)}")
        state["verdict"] = "NEEDS_REVIEW"
        return state
