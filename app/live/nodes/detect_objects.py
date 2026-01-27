"""
Object detection node for live feed.

Runs YOLO26 detection on the live frame using industry-standard
in-memory processing (no disk I/O).
"""
import cv2
import numpy as np
from io import BytesIO
from pathlib import Path
from app.live.state import LiveFeedState
from app.models.yolo26 import YOLO26Detector
from app.core.logging import get_logger
from app.utils.progress import send_progress

logger = get_logger("live.detect")

# Singleton detector instance (cached across frames for performance)
_detector_instance = None


def get_detector() -> YOLO26Detector:
    """Get or create YOLO detector instance."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = YOLO26Detector()
        _detector_instance.load()
        logger.info("YOLO26 detector loaded for live feed")
    return _detector_instance


def detect_objects(state: LiveFeedState) -> LiveFeedState:
    """
    Run YOLO26 object detection on the frame.
    
    INDUSTRY STANDARD OPTIMIZATIONS:
    - In-memory processing (no disk I/O)
    - Direct numpy array processing
    - Singleton model instance
    
    Args:
        state: Current live feed state
        
    Returns:
        Updated state with object detections
    """
    send_progress(state.get("progress_callback"), "detect_objects", "Running YOLO detection", 30)
    
    try:
        # Get detector
        detector = get_detector()
        
        # Decode frame to numpy array (in-memory)
        frame_bytes = state["frame_data"]
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame_img is None:
            raise ValueError("Failed to decode frame for detection")
        
        # INDUSTRY STANDARD: Use model's direct prediction on numpy array if supported
        # If model only supports file paths, use in-memory buffer via PIL
        try:
            # Try direct prediction on numpy array (fastest - zero I/O)
            from PIL import Image
            # Convert BGR (OpenCV) to RGB (PIL/YOLO)
            frame_rgb = cv2.cvtColor(frame_img, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(frame_rgb)
            
            # YOLO can accept PIL Image directly (no disk I/O!)
            results = detector.model.predict(
                source=pil_img,
                conf=detector.confidence,
                verbose=False
            )
            
            # Parse results (same format as file-based detection)
            detections = []
            if results and len(results) > 0:
                result = results[0]
                boxes = result.boxes
                
                for box in boxes:
                    cls_id = int(box.cls[0])
                    confidence = float(box.conf[0])
                    coords = box.xyxy[0].cpu().numpy()
                    
                    label = detector.model.names[cls_id]
                    category = detector._map_to_category(label)
                    
                    detections.append({
                        "label": label,
                        "confidence": confidence,
                        "category": category,
                        "bbox": {
                            "x1": float(coords[0]),
                            "y1": float(coords[1]),
                            "x2": float(coords[2]),
                            "y2": float(coords[3])
                        },
                        "timestamp": state["frame_timestamp"]
                    })
            
        except Exception as e:
            # Fallback: Use temp file (only if direct prediction fails)
            logger.warning(f"Direct prediction failed, using file fallback: {e}")
            import tempfile
            import os
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                temp_path = tmp.name
                cv2.imwrite(temp_path, frame_img)
            
            try:
                detections = detector.detect(temp_path, timestamp=state["frame_timestamp"])
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        
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
            f"Frame {state['frame_id']}: {len(detections)} objects detected "
            f"(weapon={weapon_detected}, person={person_detected})"
        )
        
        send_progress(state.get("progress_callback"), "detect_objects", 
                     f"{len(detections)} objects detected", 50)
        state["current_stage"] = "detect_violence"
        state["stage_progress"] = 50
        
        return state
        
    except Exception as e:
        logger.error(f"Object detection failed: {e}", exc_info=True)
        state.setdefault("errors", []).append(f"Detection error: {str(e)}")
        # Continue with empty detections
        state["vision_detections"] = []
        state["object_count"] = 0
        state["weapon_detected"] = False
        state["person_detected"] = False
        return state
