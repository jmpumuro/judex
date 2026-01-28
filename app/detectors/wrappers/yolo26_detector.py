"""
YOLO26 detector wrapper.

Wraps the existing YOLO26Detector model to produce standardized evidence.
"""
import time
from typing import Dict, Any, List
from app.detectors.base import BaseDetector, DetectorResult, DetectorContext
from app.evaluation.evidence import EvidenceItem, EvidenceCollection
from app.evaluation.spec import DetectorSpec, DetectorType
from app.core.logging import get_logger

logger = get_logger("detector.yolo26")


class YOLO26DetectorWrapper(BaseDetector):
    """
    Wrapper for YOLO26 object detection.
    
    Detects objects in video frames and categorizes safety-relevant detections.
    """
    
    detector_type = DetectorType.YOLO26.value
    
    # Category mappings for safety-relevant objects
    SAFETY_CATEGORIES = {
        "weapon": ["knife", "gun", "rifle", "sword", "pistol", "firearm"],
        "substance": ["bottle", "wine glass", "cup", "cigarette"],
        "dangerous": ["scissors", "fire", "explosion"],
    }
    
    def __init__(self, spec: DetectorSpec):
        super().__init__(spec)
        self._model = None
        self._model_version = "yolo11n"  # Default model
    
    def load_model(self):
        """Load the YOLO26 model."""
        if self._model is None:
            from app.models.yolo26 import get_yolo26_detector
            self._model = get_yolo26_detector()
    
    def detect(self, context: DetectorContext) -> DetectorResult:
        """
        Run YOLO26 detection on sampled frames.
        """
        start_time = time.time()
        self.load_model()
        
        evidence = EvidenceCollection()
        all_detections = []
        safety_signals = {cat: [] for cat in self.SAFETY_CATEGORIES}
        
        confidence_threshold = self.params.get("confidence_threshold", 0.5)
        
        # Process sampled frames
        frames = context.sampled_frames
        if not frames:
            logger.warning("No sampled frames available for YOLO26 detection")
            return self._create_result(
                evidence=evidence,
                raw_outputs={"detections": [], "safety_signals": safety_signals},
                duration=time.time() - start_time,
                warnings=["No frames to process"]
            )
        
        for frame_info in frames:
            frame_path = frame_info.get("path")
            timestamp = frame_info.get("timestamp", 0.0)
            
            if not frame_path:
                continue
            
            try:
                # Run YOLO detection
                detections = self._model.detect(frame_path, confidence_threshold)
                
                for det in detections:
                    # Create evidence item
                    category = self._categorize_detection(det["label"])
                    
                    item = EvidenceItem.from_yolo_detection(
                        detector_id=self.detector_id,
                        label=det["label"],
                        confidence=det["confidence"],
                        bbox=det.get("bbox", {}),
                        timestamp=timestamp,
                        frame_path=frame_path,
                        category=category
                    )
                    evidence.add(item)
                    
                    # Track for raw output
                    all_detections.append({
                        "id": item.id,
                        "label": det["label"],
                        "confidence": det["confidence"],
                        "bbox": det.get("bbox"),
                        "timestamp": timestamp,
                        "category": category
                    })
                    
                    # Track safety signals
                    if category in safety_signals:
                        safety_signals[category].append({
                            "label": det["label"],
                            "confidence": det["confidence"],
                            "timestamp": timestamp
                        })
            
            except Exception as e:
                logger.error(f"YOLO26 detection failed for {frame_path}: {e}")
        
        duration = time.time() - start_time
        logger.info(
            f"YOLO26 processed {len(frames)} frames, "
            f"found {len(all_detections)} detections in {duration:.2f}s"
        )
        
        return self._create_result(
            evidence=evidence,
            raw_outputs={
                "detections": all_detections,
                "safety_signals": safety_signals,
                "frames_processed": len(frames)
            },
            duration=duration
        )
    
    def _categorize_detection(self, label: str) -> str:
        """Categorize a detection label into safety categories."""
        label_lower = label.lower()
        
        for category, keywords in self.SAFETY_CATEGORIES.items():
            if any(kw in label_lower for kw in keywords):
                return category
        
        return "object"  # Default category
