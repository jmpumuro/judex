"""
Detector wrappers that adapt existing model implementations to the BaseDetector interface.
"""
from app.detectors.wrappers.yolo26_detector import YOLO26DetectorWrapper
from app.detectors.wrappers.yoloworld_detector import YOLOWorldDetectorWrapper
from app.detectors.wrappers.xclip_detector import XCLIPViolenceDetector
from app.detectors.wrappers.whisper_detector import WhisperASRDetector
from app.detectors.wrappers.ocr_detector import OCRDetector
from app.detectors.wrappers.text_moderation_detector import TextModerationDetector

__all__ = [
    "YOLO26DetectorWrapper",
    "YOLOWorldDetectorWrapper", 
    "XCLIPViolenceDetector",
    "WhisperASRDetector",
    "OCRDetector",
    "TextModerationDetector"
]
