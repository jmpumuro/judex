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

__all__ = [
    "Yolo26StagePlugin",
    "YoloWorldStagePlugin",
    "ViolenceStagePlugin",
    "WhisperStagePlugin",
    "OcrStagePlugin",
    "TextModerationStagePlugin",
]
