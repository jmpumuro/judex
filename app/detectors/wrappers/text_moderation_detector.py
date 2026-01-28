"""
Text moderation detector wrapper.

Wraps the existing text moderation model for content analysis.
"""
import time
from typing import Dict, Any, List
from app.detectors.base import BaseDetector, DetectorResult, DetectorContext
from app.evaluation.evidence import EvidenceItem, EvidenceCollection
from app.evaluation.spec import DetectorSpec, DetectorType
from app.core.logging import get_logger

logger = get_logger("detector.text_moderation")


class TextModerationDetector(BaseDetector):
    """
    Wrapper for text content moderation.
    
    Analyzes transcript and OCR text for inappropriate content.
    """
    
    detector_type = DetectorType.TEXT_MODERATION.value
    
    def __init__(self, spec: DetectorSpec):
        super().__init__(spec)
        self._model = None
        self._model_version = "text-moderation-v1"
    
    def load_model(self):
        """Load the text moderation model."""
        if self._model is None:
            from app.models.moderation import get_text_moderator
            self._model = get_text_moderator()
    
    def detect(self, context: DetectorContext) -> DetectorResult:
        """
        Run text moderation on transcript and OCR results.
        
        Requires whisper_asr and ocr detectors to have run first.
        """
        start_time = time.time()
        self.load_model()
        
        evidence = EvidenceCollection()
        transcript_moderation = []
        ocr_moderation = []
        
        categories = self.params.get(
            "categories",
            ["profanity", "sexual", "drugs", "hate", "violence"]
        )
        
        # Get transcript from dependent detector
        whisper_result = context.detector_outputs.get("whisper_asr")
        ocr_result = context.detector_outputs.get("ocr")
        
        # Moderate transcript chunks
        if whisper_result:
            transcript_data = whisper_result.raw_outputs.get("transcript", {})
            chunks = transcript_data.get("chunks", [])
            
            for chunk in chunks:
                text = chunk.get("text", "")
                if not text.strip():
                    continue
                
                try:
                    scores = self._model.moderate(text, categories)
                    
                    mod_result = {
                        "id": chunk.get("id", ""),
                        "text": text[:200],  # Truncate for storage
                        "start_time": chunk.get("start_time", 0),
                        "end_time": chunk.get("end_time", 0),
                        **{f"{cat}_score": scores.get(cat, 0) for cat in categories},
                        **{f"{cat}_words": scores.get(f"{cat}_words", []) for cat in categories}
                    }
                    transcript_moderation.append(mod_result)
                    
                    # Create evidence items for significant findings
                    evidence_items = EvidenceItem.from_text_moderation(
                        detector_id=self.detector_id,
                        text=text,
                        scores=scores,
                        start_time=chunk.get("start_time"),
                        end_time=chunk.get("end_time"),
                        source="transcript"
                    )
                    evidence.add_many(evidence_items)
                
                except Exception as e:
                    logger.error(f"Text moderation failed for chunk: {e}")
        
        # Moderate OCR text
        if ocr_result:
            ocr_results = ocr_result.raw_outputs.get("ocr_results", [])
            
            for ocr_item in ocr_results:
                text = ocr_item.get("text", "")
                if not text.strip():
                    continue
                
                try:
                    scores = self._model.moderate(text, categories)
                    
                    mod_result = {
                        "id": ocr_item.get("id", ""),
                        "text": text[:200],
                        "timestamp": ocr_item.get("timestamp", 0),
                        **{f"{cat}_score": scores.get(cat, 0) for cat in categories}
                    }
                    ocr_moderation.append(mod_result)
                    
                    # Create evidence items for significant findings
                    evidence_items = EvidenceItem.from_text_moderation(
                        detector_id=self.detector_id,
                        text=text,
                        scores=scores,
                        start_time=ocr_item.get("timestamp"),
                        source="ocr"
                    )
                    evidence.add_many(evidence_items)
                
                except Exception as e:
                    logger.error(f"OCR text moderation failed: {e}")
        
        duration = time.time() - start_time
        logger.info(
            f"Text moderation analyzed {len(transcript_moderation)} transcript chunks, "
            f"{len(ocr_moderation)} OCR items in {duration:.2f}s"
        )
        
        return self._create_result(
            evidence=evidence,
            raw_outputs={
                "transcript_moderation": transcript_moderation,
                "ocr_moderation": ocr_moderation,
                "transcript_chunks_analyzed": len(transcript_moderation),
                "ocr_items_analyzed": len(ocr_moderation)
            },
            duration=duration
        )
