"""
Live feed state definition for LangGraph.

This defines the state object for real-time frame analysis,
following the same pattern as the video pipeline.
"""
from typing import TypedDict, List, Dict, Any, Optional, Callable
import time


class LiveFeedState(TypedDict, total=False):
    """
    State object for live feed frame analysis.
    
    This state flows through the live feed graph and accumulates
    analysis results for each frame in real-time.
    """
    
    # Input
    frame_id: str  # Unique identifier for this frame
    frame_data: bytes  # Raw frame image data (JPEG/PNG bytes)
    frame_timestamp: float  # When the frame was captured
    stream_id: str  # Which stream this frame belongs to
    stream_metadata: Dict[str, Any]  # Stream configuration
    
    # Frame metadata
    frame_width: int
    frame_height: int
    frame_format: str  # 'jpeg', 'png', etc.
    
    # Progress tracking (optional, for UI updates)
    progress_callback: Optional[Callable[[str, str, int], None]]
    current_stage: str
    stage_progress: int
    
    # === DETECTION OUTPUTS ===
    
    # YOLO Vision Detection
    vision_detections: List[Dict[str, Any]]  # List of detected objects
    # Each detection: {label, confidence, bbox, category}
    object_count: int
    weapon_detected: bool
    person_detected: bool
    
    # Violence Detection
    violence_score: float  # 0.0 - 1.0
    violence_label: str  # 'violence' or 'non-violence'
    violence_confidence: float
    
    # === MODERATION ===
    
    # Text found in frame (OCR on key objects if needed)
    ocr_text: Optional[str]
    ocr_confidence: Optional[float]
    
    # Profanity/harmful content in detected text
    text_violations: List[Dict[str, Any]]
    
    # === POLICY & VERDICT ===
    
    # Policy evaluation
    criterion_scores: Dict[str, float]  # Same criteria as video pipeline
    violations: List[Dict[str, Any]]  # List of policy violations
    verdict: str  # 'SAFE', 'UNSAFE', 'NEEDS_REVIEW'
    
    # Evidence summary
    evidence: Dict[str, Any]  # Structured evidence for this frame
    
    # === OUTPUT ===
    
    # Final result object (sent to frontend/API)
    result: Dict[str, Any]
    
    # Timing for performance monitoring
    timings: Dict[str, float]  # Stage-by-stage timing
    processing_time_ms: float  # Total processing time
    
    # Errors
    errors: List[str]
    
    # === PERSISTENCE ===
    
    # Whether this frame should be saved as an event
    save_as_event: bool
    event_priority: str  # 'low', 'medium', 'high', 'critical'
    
    # Thumbnail for event storage (base64 or path)
    thumbnail_data: Optional[str]


class StreamContext(TypedDict, total=False):
    """
    Context for a continuous video stream.
    
    Maintains state across multiple frames for temporal analysis
    (e.g., tracking objects across frames, motion detection).
    """
    
    stream_id: str
    stream_url: Optional[str]
    stream_type: str  # 'webcam', 'rtsp', 'rtmp', 'http'
    
    # Stream metadata
    start_time: float
    last_frame_time: float
    total_frames_processed: int
    fps: float  # Estimated FPS
    
    # Temporal state (for tracking across frames)
    previous_detections: List[Dict[str, Any]]  # Last N frames of detections
    motion_history: List[float]  # Motion intensity over time
    
    # Aggregate statistics
    total_violations: int
    max_violence_score: float
    avg_violence_score: float
    
    # Active alerts
    active_alerts: List[Dict[str, Any]]
    
    # Model state (cached for performance)
    models_loaded: bool


def create_initial_state(
    frame_id: str,
    frame_data: bytes,
    stream_id: str = "default",
    stream_metadata: Optional[Dict[str, Any]] = None
) -> LiveFeedState:
    """
    Create initial state for a live feed frame.
    
    Args:
        frame_id: Unique identifier for the frame
        frame_data: Raw frame bytes
        stream_id: Stream identifier
        stream_metadata: Optional stream configuration
        
    Returns:
        Initialized LiveFeedState
    """
    return LiveFeedState(
        frame_id=frame_id,
        frame_data=frame_data,
        frame_timestamp=time.time(),
        stream_id=stream_id,
        stream_metadata=stream_metadata or {},
        current_stage="capture",
        stage_progress=0,
        vision_detections=[],
        object_count=0,
        weapon_detected=False,
        person_detected=False,
        violence_score=0.0,
        violence_label="non-violence",
        violence_confidence=0.0,
        ocr_text=None,
        text_violations=[],
        criterion_scores={},
        violations=[],
        verdict="SAFE",
        evidence={},
        result={},
        timings={},
        errors=[],
        save_as_event=False,
        event_priority="low",
        thumbnail_data=None
    )
