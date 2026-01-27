"""
Pipeline state definition for LangGraph.
"""
from typing import TypedDict, List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field


class PipelineState(TypedDict, total=False):
    """State object for the video safety analysis pipeline."""
    
    # Input
    video_path: str
    policy_config: Dict[str, Any]
    
    # Progress tracking
    progress_callback: Optional[Callable[[str, str, int], None]]
    current_stage: str
    stage_progress: int
    
    # Working directory
    work_dir: str
    video_id: str
    
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
    vision_detections: List[Dict[str, Any]]
    violence_segments: List[Dict[str, Any]]
    transcript: Dict[str, Any]  # {full_text, chunks}
    ocr_results: List[Dict[str, Any]]
    
    # Text moderation results
    transcript_moderation: List[Dict[str, Any]]
    ocr_moderation: List[Dict[str, Any]]
    
    # Policy outputs
    criterion_scores: Dict[str, float]
    violations: List[Dict[str, Any]]
    verdict: str
    
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
