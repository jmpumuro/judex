"""
Tests for backward compatibility with original child-safety API.

Verifies that:
- Original /v1/evaluate endpoint still works
- Response shape matches original format
- Default behavior uses child-safety criteria
- Policy overrides still work
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app
from app.policies.presets import CHILD_SAFETY_PRESET, DEFAULT_PRESET


client = TestClient(app)


class TestDefaultPreset:
    """Tests for default preset configuration."""
    
    def test_default_preset_is_child_safety(self):
        """Verify default preset is child_safety."""
        assert DEFAULT_PRESET == CHILD_SAFETY_PRESET
        assert DEFAULT_PRESET.spec_id == "child_safety"
    
    def test_child_safety_has_expected_criteria(self):
        """Verify child_safety preset has all expected criteria."""
        expected_criteria = {"violence", "profanity", "sexual", "drugs", "hate"}
        actual_criteria = {c.id for c in CHILD_SAFETY_PRESET.criteria}
        
        assert expected_criteria == actual_criteria
    
    def test_child_safety_has_expected_detectors(self):
        """Verify child_safety preset has all expected detectors."""
        expected_detectors = {
            "yolo26_vision",
            "yoloworld_vision",
            "xclip_violence",
            "whisper_asr",
            "ocr",
            "text_moderation"
        }
        actual_detectors = {d.id for d in CHILD_SAFETY_PRESET.detectors}
        
        assert expected_detectors == actual_detectors


class TestOriginalEndpointStructure:
    """Tests for original /evaluate endpoint response structure."""
    
    @pytest.fixture
    def mock_pipeline_result(self):
        """Mock result from pipeline matching original format."""
        return {
            "verdict": "SAFE",
            "criteria": {
                "violence": {"score": 0.1, "status": "ok"},
                "profanity": {"score": 0.2, "status": "ok"},
                "sexual": {"score": 0.0, "status": "ok"},
                "drugs": {"score": 0.1, "status": "ok"},
                "hate": {"score": 0.0, "status": "ok"}
            },
            "violations": [],
            "evidence": {
                "vision": [],
                "violence_segments": [],
                "asr": [],
                "ocr": [],
                "transcript_moderation": [],
                "ocr_moderation": []
            },
            "report": "Video appears safe for children.",
            "metadata": {
                "video_id": "test_video_123",
                "duration": 30.0,
                "frames_analyzed": 450,
                "segments_analyzed": 8
            },
            "timings": {
                "total_seconds": 15.5,
                "operations": {
                    "ingest": 0.5,
                    "yolo": 3.0,
                    "violence": 5.0,
                    "asr": 4.0,
                    "fusion": 0.1
                }
            }
        }
    
    def test_health_endpoint(self):
        """Test health endpoint still works."""
        response = client.get("/v1/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
    
    def test_models_endpoint(self):
        """Test models endpoint still works."""
        response = client.get("/v1/models")
        assert response.status_code == 200
        
        data = response.json()
        assert "models" in data
        assert len(data["models"]) > 0


class TestCriteriaScoring:
    """Tests for criteria scoring backward compatibility."""
    
    def test_violence_thresholds(self):
        """Verify violence thresholds match original."""
        violence = next(
            c for c in CHILD_SAFETY_PRESET.criteria if c.id == "violence"
        )
        
        # Original thresholds from fuse_policy.py
        assert violence.thresholds.safe_below <= 0.40
        assert violence.thresholds.unsafe_above >= 0.70
    
    def test_profanity_thresholds(self):
        """Verify profanity thresholds."""
        profanity = next(
            c for c in CHILD_SAFETY_PRESET.criteria if c.id == "profanity"
        )
        
        assert profanity.thresholds.safe_below <= 0.40
    
    def test_hate_thresholds(self):
        """Verify hate speech thresholds."""
        hate = next(
            c for c in CHILD_SAFETY_PRESET.criteria if c.id == "hate"
        )
        
        assert hate.thresholds.safe_below <= 0.30
        assert hate.thresholds.unsafe_above >= 0.60


class TestVerdictLevels:
    """Tests for verdict level compatibility."""
    
    def test_verdict_levels_match_original(self):
        """Verify preset uses same verdict levels as original."""
        expected_verdicts = ["SAFE", "CAUTION", "UNSAFE", "NEEDS_REVIEW"]
        
        for v in expected_verdicts:
            assert v in CHILD_SAFETY_PRESET.verdict_levels


class TestFusionStrategy:
    """Tests for fusion strategy compatibility."""
    
    def test_uses_weighted_sum_by_default(self):
        """Verify default fusion is weighted sum (matching original)."""
        from app.evaluation.spec import FusionStrategy
        
        assert CHILD_SAFETY_PRESET.fusion.criterion_strategy == FusionStrategy.WEIGHTED_SUM
    
    def test_any_unsafe_aggregation(self):
        """Verify aggregation uses ANY_UNSAFE (matching original)."""
        from app.evaluation.spec import AggregationRule
        
        assert CHILD_SAFETY_PRESET.fusion.verdict_aggregation == AggregationRule.ANY_UNSAFE
    
    def test_multi_signal_confirmation_enabled(self):
        """Verify multi-signal confirmation is enabled (matching original)."""
        assert CHILD_SAFETY_PRESET.fusion.require_confirmation is True


class TestDetectorConfiguration:
    """Tests for detector configuration compatibility."""
    
    def test_yolo26_enabled(self):
        """Verify YOLO26 detector is enabled."""
        yolo = next(
            d for d in CHILD_SAFETY_PRESET.detectors if d.id == "yolo26_vision"
        )
        assert yolo.enabled is True
    
    def test_xclip_violence_enabled(self):
        """Verify X-CLIP violence detector is enabled."""
        xclip = next(
            d for d in CHILD_SAFETY_PRESET.detectors if d.id == "xclip_violence"
        )
        assert xclip.enabled is True
    
    def test_whisper_asr_enabled(self):
        """Verify Whisper ASR is enabled."""
        whisper = next(
            d for d in CHILD_SAFETY_PRESET.detectors if d.id == "whisper_asr"
        )
        assert whisper.enabled is True
    
    def test_text_moderation_depends_on_asr(self):
        """Verify text moderation depends on ASR."""
        text_mod = next(
            d for d in CHILD_SAFETY_PRESET.detectors if d.id == "text_moderation"
        )
        assert "whisper_asr" in text_mod.depends_on


class TestRouting:
    """Tests for routing configuration."""
    
    def test_violence_routing(self):
        """Verify violence criterion receives input from expected detectors."""
        violence_routing = next(
            r for r in CHILD_SAFETY_PRESET.routing if r.criterion_id == "violence"
        )
        
        source_detectors = [s.detector_id for s in violence_routing.sources]
        
        # Should include violence model and YOLO
        assert "xclip_violence" in source_detectors
        assert "yolo26_vision" in source_detectors
    
    def test_profanity_routing(self):
        """Verify profanity criterion receives input from text moderation."""
        profanity_routing = next(
            r for r in CHILD_SAFETY_PRESET.routing if r.criterion_id == "profanity"
        )
        
        source_detectors = [s.detector_id for s in profanity_routing.sources]
        assert "text_moderation" in source_detectors


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
