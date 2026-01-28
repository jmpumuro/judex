"""
YOLO-World detector wrapper.

Wraps the existing YOLO-World model for prompt-based object detection.
"""
import time
from typing import Dict, Any, List
from app.detectors.base import BaseDetector, DetectorResult, DetectorContext
from app.evaluation.evidence import EvidenceItem, EvidenceCollection
from app.evaluation.spec import DetectorSpec, DetectorType
from app.core.logging import get_logger

logger = get_logger("detector.yoloworld")


class YOLOWorldDetectorWrapper(BaseDetector):
    """
    Wrapper for YOLO-World prompt-based detection.
    
    Uses text prompts to detect specific objects of interest.
    """
    
    detector_type = DetectorType.YOLOWORLD.value
    
    # Default prompts for safety detection
    DEFAULT_PROMPTS = [
        "weapon", "knife", "gun", "blood", "drugs", "alcohol",
        "cigarette", "needle", "pills", "fire", "explosion"
    ]
    
    def __init__(self, spec: DetectorSpec):
        super().__init__(spec)
        self._model = None
        self._model_version = "yoloworld-l"
    
    def load_model(self):
        """Load the YOLO-World model."""
        if self._model is None:
            from app.models.yoloworld import get_yoloworld_detector
            self._model = get_yoloworld_detector()
    
    def detect(self, context: DetectorContext) -> DetectorResult:
        """
        Run YOLO-World detection on sampled frames.
        """
        start_time = time.time()
        self.load_model()
        
        evidence = EvidenceCollection()
        all_detections = []
        prompt_matches = {}
        
        prompts = self.params.get("prompts", self.DEFAULT_PROMPTS)
        confidence_threshold = self.params.get("confidence_threshold", 0.3)
        
        # Process sampled frames
        frames = context.sampled_frames
        if not frames:
            logger.warning("No sampled frames available for YOLO-World detection")
            return self._create_result(
                evidence=evidence,
                raw_outputs={"detections": [], "prompt_matches": {}},
                duration=time.time() - start_time,
                warnings=["No frames to process"]
            )
        
        for frame_info in frames:
            frame_path = frame_info.get("path")
            timestamp = frame_info.get("timestamp", 0.0)
            
            if not frame_path:
                continue
            
            try:
                # Run YOLO-World detection with prompts
                detections = self._model.detect_with_prompts(
                    frame_path,
                    prompts,
                    confidence_threshold
                )
                
                for det in detections:
                    label = det["label"]
                    
                    # Create evidence item
                    item = EvidenceItem.from_yolo_detection(
                        detector_id=self.detector_id,
                        label=label,
                        confidence=det["confidence"],
                        bbox=det.get("bbox", {}),
                        timestamp=timestamp,
                        frame_path=frame_path,
                        category=self._get_category(label),
                        prompt_match=label
                    )
                    evidence.add(item)
                    
                    # Track for raw output
                    all_detections.append({
                        "id": item.id,
                        "label": label,
                        "confidence": det["confidence"],
                        "bbox": det.get("bbox"),
                        "timestamp": timestamp,
                        "prompt_match": label
                    })
                    
                    # Track prompt matches
                    if label not in prompt_matches:
                        prompt_matches[label] = []
                    prompt_matches[label].append({
                        "confidence": det["confidence"],
                        "timestamp": timestamp
                    })
            
            except Exception as e:
                logger.error(f"YOLO-World detection failed for {frame_path}: {e}")
        
        duration = time.time() - start_time
        logger.info(
            f"YOLO-World processed {len(frames)} frames with {len(prompts)} prompts, "
            f"found {len(all_detections)} matches in {duration:.2f}s"
        )
        
        return self._create_result(
            evidence=evidence,
            raw_outputs={
                "detections": all_detections,
                "prompt_matches": prompt_matches,
                "prompts_used": prompts,
                "frames_processed": len(frames)
            },
            duration=duration
        )
    
    def _get_category(self, label: str) -> str:
        """Map label to category."""
        label_lower = label.lower()
        
        if any(w in label_lower for w in ["weapon", "knife", "gun"]):
            return "weapon"
        if any(w in label_lower for w in ["drug", "pill", "needle"]):
            return "substance"
        if any(w in label_lower for w in ["blood", "fire", "explosion"]):
            return "dangerous"
        if any(w in label_lower for w in ["alcohol", "cigarette"]):
            return "substance"
        
        return "object"
