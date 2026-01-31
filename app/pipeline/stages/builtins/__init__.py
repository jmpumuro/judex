"""
Builtin stage plugins that wrap existing pipeline nodes.

These plugins provide the StagePlugin interface for existing detector
implementations, allowing them to be used in the pluggable pipeline system.
"""
from app.pipeline.stages.builtins.yolo26 import Yolo26StagePlugin
from app.pipeline.stages.builtins.yoloworld import YoloWorldStagePlugin
from app.pipeline.stages.builtins.violence import ViolenceStagePlugin
from app.pipeline.stages.builtins.whisper import WhisperStagePlugin
from app.pipeline.stages.builtins.ocr import OcrStagePlugin
from app.pipeline.stages.builtins.text_moderation import TextModerationStagePlugin

# Enhanced Violence Detection Stack (new)
from app.pipeline.stages.builtins.window_mining import WindowMiningStagePlugin
from app.pipeline.stages.builtins.pose_heuristics import PoseHeuristicsStagePlugin
from app.pipeline.stages.builtins.videomae_violence import VideoMAEViolenceStagePlugin

# NSFW Visual Detection (reduces sexual false positives)
from app.pipeline.stages.builtins.nsfw_detection import NSFWDetectionStagePlugin

__all__ = [
    # Core stages
    "Yolo26StagePlugin",
    "YoloWorldStagePlugin",
    "ViolenceStagePlugin",
    "WhisperStagePlugin",
    "OcrStagePlugin",
    "TextModerationStagePlugin",
    # Enhanced violence detection stack
    "WindowMiningStagePlugin",
    "PoseHeuristicsStagePlugin",
    "VideoMAEViolenceStagePlugin",
    # NSFW visual detection (sexual content confirmation)
    "NSFWDetectionStagePlugin",
]
