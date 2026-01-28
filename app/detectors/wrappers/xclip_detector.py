"""
X-CLIP Violence detector wrapper.

Wraps the existing X-CLIP violence detection model.
"""
import time
from typing import Dict, Any, List
from app.detectors.base import BaseDetector, DetectorResult, DetectorContext
from app.evaluation.evidence import EvidenceItem, EvidenceCollection, TimeRange
from app.evaluation.spec import DetectorSpec, DetectorType
from app.core.logging import get_logger

logger = get_logger("detector.xclip")


class XCLIPViolenceDetector(BaseDetector):
    """
    Wrapper for X-CLIP violence detection.
    
    Analyzes video segments for violence using a video-text model.
    """
    
    detector_type = DetectorType.XCLIP_VIOLENCE.value
    
    def __init__(self, spec: DetectorSpec):
        super().__init__(spec)
        self._model = None
        self._model_version = "xclip-violence-v1"
    
    def load_model(self):
        """Load the X-CLIP model."""
        if self._model is None:
            from app.models.violence_xclip import get_violence_detector
            self._model = get_violence_detector()
    
    def detect(self, context: DetectorContext) -> DetectorResult:
        """
        Run violence detection on video segments.
        """
        start_time = time.time()
        self.load_model()
        
        evidence = EvidenceCollection()
        violence_segments = []
        violence_scores = []
        
        segment_duration = self.params.get("segment_duration", 4.0)
        violence_threshold = self.params.get("violence_threshold", 0.4)
        
        video_path = context.video_path
        duration = context.duration
        
        if not video_path or duration <= 0:
            return self._create_result(
                evidence=evidence,
                raw_outputs={"violence_segments": [], "violence_scores": []},
                duration=time.time() - start_time,
                warnings=["No video to process"]
            )
        
        try:
            # Analyze video segments
            segments = self._model.analyze_video(
                video_path,
                segment_duration=segment_duration
            )
            
            for seg in segments:
                seg_start = seg.get("start_time", 0)
                seg_end = seg.get("end_time", seg_start + segment_duration)
                violence_score = seg.get("violence_score", 0)
                
                violence_scores.append({
                    "start_time": seg_start,
                    "end_time": seg_end,
                    "score": violence_score
                })
                
                # Create evidence for segments above threshold
                if violence_score >= violence_threshold:
                    item = EvidenceItem.from_violence_segment(
                        detector_id=self.detector_id,
                        violence_score=violence_score,
                        start_time=seg_start,
                        end_time=seg_end,
                        label="violence",
                        all_predictions=seg.get("all_predictions", {})
                    )
                    evidence.add(item)
                    
                    violence_segments.append({
                        "id": item.id,
                        "start_time": seg_start,
                        "end_time": seg_end,
                        "violence_score": violence_score,
                        "label": seg.get("label", "violence")
                    })
        
        except Exception as e:
            logger.error(f"X-CLIP violence detection failed: {e}")
            return self._create_result(
                evidence=evidence,
                raw_outputs={"violence_segments": [], "violence_scores": []},
                duration=time.time() - start_time,
                warnings=[f"Detection failed: {str(e)}"]
            )
        
        duration = time.time() - start_time
        max_score = max([s["score"] for s in violence_scores], default=0)
        logger.info(
            f"X-CLIP analyzed {len(violence_scores)} segments, "
            f"max violence score: {max_score:.2f}, "
            f"flagged {len(violence_segments)} segments in {duration:.2f}s"
        )
        
        return self._create_result(
            evidence=evidence,
            raw_outputs={
                "violence_segments": violence_segments,
                "violence_scores": violence_scores,
                "max_violence_score": max_score,
                "segments_analyzed": len(violence_scores)
            },
            duration=duration
        )
