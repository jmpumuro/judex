"""
Pipeline state definition for LangGraph.
"""
from typing import TypedDict, List, Dict, Any, Optional, Callable


class PipelineState(TypedDict, total=False):
    """State object for the media safety analysis pipeline (video + image)."""
    
    # Input
    video_path: str  # Legacy name, supports both video and image paths
    media_path: str  # Preferred: unified media path
    media_type: str  # "video" or "image" - from MediaType enum
    policy_config: Dict[str, Any]
    
    # Generic evaluation criteria (user-defined)
    evaluation_criteria: Any  # EvaluationCriteria object
    
    # Progress tracking
    progress_callback: Optional[Callable[[str, str, int], None]]
    current_stage: str
    stage_progress: int
    
    # Working directory
    work_dir: str
    video_id: str
    
    # Reprocessing flag
    is_reprocessing: bool
    
    # Video metadata
    duration: float
    fps: float
    width: int
    height: int
    has_audio: bool
    original_metadata: Dict[str, Any]  # Original video metadata before normalization
    audio_path: Optional[str]  # Path to extracted audio (mono 16kHz WAV)
    
    # Labeled video with YOLO detections
    labeled_video_path: Optional[str]
    
    # Segmentation
    segments: List[Dict[str, Any]]  # {start_time, end_time, frames}
    sampled_frames: List[Dict[str, Any]]  # {path, timestamp, frame_index}
    
    # Model outputs
    vision_detections: List[Dict[str, Any]]  # YOLO26 detections
    yoloworld_detections: List[Dict[str, Any]]  # YOLO-World detections
    violence_segments: List[Dict[str, Any]]  # X-CLIP violence detection
    transcript: Dict[str, Any]  # {full_text, chunks}
    ocr_results: List[Dict[str, Any]]
    
    # ==== NEW: Enhanced Violence Detection Stack ====
    # Candidate window mining outputs
    candidate_windows: List[Dict[str, Any]]  # {start_time, end_time, reason, score, cues}
    window_mining_debug: Dict[str, Any]  # Motion scores, cues for audit
    
    # VideoMAE violence detection outputs (parallel to X-CLIP)
    videomae_scores: List[Dict[str, Any]]  # {window_idx, start_time, end_time, score, label}
    
    # Pose-based violence heuristics outputs
    pose_signals: List[Dict[str, Any]]  # {timestamp, signal_type, confidence, reason, persons}
    pose_keypoints: List[Dict[str, Any]]  # Raw pose detections if available
    
    # ==== END Enhanced Violence Detection ====
    
    # ==== NSFW Visual Detection (Sexual Content) ====
    # Industry Standard: Requires visual confirmation for sexual content scoring
    # Profanity alone ≠ Sexual content
    nsfw_results: Dict[str, Any]  # {is_nsfw, nsfw_score, nsfw_frames, detections}
    # ==== END NSFW Detection ====
    
    # Text moderation results
    transcript_moderation: List[Dict[str, Any]]
    ocr_moderation: List[Dict[str, Any]]
    
    # Policy outputs (from fusion)
    criteria_scores: Dict[str, Any]  # Per-criterion scores from fusion
    violations: List[Dict[str, Any]]
    verdict: str
    confidence: float
    
    # ==== NEW: Enhanced Fusion Debug ====
    fusion_debug: Dict[str, Any]  # Reliability weights, missing signals, calibration info
    
    # Stage execution tracking (from PipelineRunner)
    stage_runs: List[Dict[str, Any]]
    
    # Evidence
    evidence: Dict[str, Any]
    
    # LLM report
    report: str
    
    # Final output
    result: Dict[str, Any]
    
    # Timing
    timings: Dict[str, float]
    
    # Errors
    errors: List[str]
