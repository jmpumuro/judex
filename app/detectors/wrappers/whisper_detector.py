"""
Whisper ASR detector wrapper.

Wraps the existing Whisper model for audio transcription.
"""
import time
from typing import Dict, Any, List
from app.detectors.base import BaseDetector, DetectorResult, DetectorContext
from app.evaluation.evidence import EvidenceItem, EvidenceCollection
from app.evaluation.spec import DetectorSpec, DetectorType
from app.core.logging import get_logger

logger = get_logger("detector.whisper")


class WhisperASRDetector(BaseDetector):
    """
    Wrapper for Whisper automatic speech recognition.
    
    Transcribes audio from video files.
    """
    
    detector_type = DetectorType.WHISPER_ASR.value
    
    def __init__(self, spec: DetectorSpec):
        super().__init__(spec)
        self._model = None
        self._model_version = "whisper-small"
    
    def load_model(self):
        """Load the Whisper model."""
        if self._model is None:
            from app.models.whisper_asr import get_whisper_model
            self._model = get_whisper_model()
            self._model_version = self._model.model_id if hasattr(self._model, 'model_id') else "whisper"
    
    def detect(self, context: DetectorContext) -> DetectorResult:
        """
        Run speech recognition on audio.
        """
        start_time = time.time()
        self.load_model()
        
        evidence = EvidenceCollection()
        transcript_chunks = []
        full_text = ""
        
        audio_path = context.audio_path
        
        if not audio_path:
            logger.warning("No audio path available for ASR")
            return self._create_result(
                evidence=evidence,
                raw_outputs={
                    "transcript": {"full_text": "", "chunks": []},
                    "chunks": []
                },
                duration=time.time() - start_time,
                warnings=["No audio to process"]
            )
        
        try:
            # Run transcription
            result = self._model.transcribe(audio_path)
            
            full_text = result.get("text", "")
            segments = result.get("segments", [])
            
            for seg in segments:
                seg_start = seg.get("start", 0)
                seg_end = seg.get("end", 0)
                seg_text = seg.get("text", "").strip()
                
                if not seg_text:
                    continue
                
                # Create evidence item
                item = EvidenceItem.from_asr_chunk(
                    detector_id=self.detector_id,
                    text=seg_text,
                    start_time=seg_start,
                    end_time=seg_end,
                    confidence=seg.get("no_speech_prob", 0)
                )
                evidence.add(item)
                
                transcript_chunks.append({
                    "id": item.id,
                    "start_time": seg_start,
                    "end_time": seg_end,
                    "text": seg_text
                })
        
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            return self._create_result(
                evidence=evidence,
                raw_outputs={
                    "transcript": {"full_text": "", "chunks": []},
                    "chunks": []
                },
                duration=time.time() - start_time,
                warnings=[f"Transcription failed: {str(e)}"]
            )
        
        duration = time.time() - start_time
        logger.info(
            f"Whisper transcribed {len(transcript_chunks)} segments, "
            f"{len(full_text)} chars in {duration:.2f}s"
        )
        
        return self._create_result(
            evidence=evidence,
            raw_outputs={
                "transcript": {
                    "full_text": full_text,
                    "chunks": transcript_chunks
                },
                "chunks": transcript_chunks,
                "word_count": len(full_text.split()),
                "segment_count": len(transcript_chunks)
            },
            duration=duration
        )
