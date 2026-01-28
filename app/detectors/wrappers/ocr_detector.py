"""
OCR detector wrapper.

Wraps OCR functionality for text extraction from video frames.
"""
import time
from typing import Dict, Any, List
from app.detectors.base import BaseDetector, DetectorResult, DetectorContext
from app.evaluation.evidence import EvidenceItem, EvidenceCollection
from app.evaluation.spec import DetectorSpec, DetectorType
from app.core.logging import get_logger

logger = get_logger("detector.ocr")


class OCRDetector(BaseDetector):
    """
    Wrapper for OCR text extraction.
    
    Extracts visible text from video frames.
    """
    
    detector_type = DetectorType.OCR.value
    
    def __init__(self, spec: DetectorSpec):
        super().__init__(spec)
        self._model = None
        self._model_version = "easyocr"
    
    def load_model(self):
        """Load the OCR model."""
        if self._model is None:
            try:
                import easyocr
                self._model = easyocr.Reader(['en'], gpu=True, verbose=False)
            except Exception as e:
                logger.warning(f"GPU OCR failed, falling back to CPU: {e}")
                import easyocr
                self._model = easyocr.Reader(['en'], gpu=False, verbose=False)
    
    def detect(self, context: DetectorContext) -> DetectorResult:
        """
        Run OCR on sampled frames.
        """
        start_time = time.time()
        self.load_model()
        
        evidence = EvidenceCollection()
        ocr_results = []
        
        sample_interval = self.params.get("sample_interval", 1.0)
        min_confidence = self.params.get("min_confidence", 0.3)
        
        # Use sampled frames from context
        frames = context.sampled_frames
        if not frames:
            logger.warning("No sampled frames available for OCR")
            return self._create_result(
                evidence=evidence,
                raw_outputs={"ocr_results": [], "text_detections": []},
                duration=time.time() - start_time,
                warnings=["No frames to process"]
            )
        
        # Sample frames at interval
        processed_times = set()
        for frame_info in frames:
            frame_path = frame_info.get("path")
            timestamp = frame_info.get("timestamp", 0.0)
            
            # Skip if we've recently processed this time
            bucket = int(timestamp / sample_interval)
            if bucket in processed_times:
                continue
            processed_times.add(bucket)
            
            if not frame_path:
                continue
            
            try:
                # Run OCR
                results = self._model.readtext(frame_path)
                
                for bbox, text, confidence in results:
                    if confidence < min_confidence:
                        continue
                    
                    text = text.strip()
                    if not text:
                        continue
                    
                    # Convert bbox to normalized format
                    # EasyOCR returns [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
                    x_coords = [p[0] for p in bbox]
                    y_coords = [p[1] for p in bbox]
                    norm_bbox = {
                        "x1": min(x_coords),
                        "y1": min(y_coords),
                        "x2": max(x_coords),
                        "y2": max(y_coords)
                    }
                    
                    # Create evidence item
                    item = EvidenceItem.from_ocr_result(
                        detector_id=self.detector_id,
                        text=text,
                        confidence=confidence,
                        timestamp=timestamp,
                        bbox=norm_bbox
                    )
                    evidence.add(item)
                    
                    ocr_results.append({
                        "id": item.id,
                        "text": text,
                        "confidence": confidence,
                        "timestamp": timestamp,
                        "bbox": norm_bbox
                    })
            
            except Exception as e:
                logger.error(f"OCR failed for {frame_path}: {e}")
        
        duration = time.time() - start_time
        logger.info(
            f"OCR processed {len(processed_times)} frames, "
            f"found {len(ocr_results)} text regions in {duration:.2f}s"
        )
        
        return self._create_result(
            evidence=evidence,
            raw_outputs={
                "ocr_results": ocr_results,
                "text_detections": ocr_results,  # Alias
                "frames_processed": len(processed_times),
                "total_text_regions": len(ocr_results)
            },
            duration=duration
        )
