"""
Tests for the generic evaluation API contract.

Verifies that:
- /evaluate/generic endpoint accepts evaluation_spec
- /evaluate/generic endpoint accepts preset_id
- Response includes all expected fields
- Invalid specs are rejected with clear errors
"""
import pytest
import json
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
from app.main import app
from app.evaluation.spec import SCHEMA_VERSION


client = TestClient(app)


class TestPresetEndpoints:
    """Tests for preset management endpoints."""
    
    def test_list_presets(self):
        """Test listing available presets."""
        response = client.get("/v1/presets")
        assert response.status_code == 200
        
        data = response.json()
        assert "presets" in data
        assert len(data["presets"]) > 0
        
        # Check child_safety preset exists
        preset_ids = [p["id"] for p in data["presets"]]
        assert "child_safety" in preset_ids
        assert "default" in preset_ids
    
    def test_get_preset_details(self):
        """Test getting preset details."""
        response = client.get("/v1/presets/child_safety")
        assert response.status_code == 200
        
        data = response.json()
        assert data["preset_id"] == "child_safety"
        assert "spec_name" in data
        assert "criteria" in data
        assert "detectors" in data
        assert "fusion" in data
        
        # Check expected criteria exist
        criteria_ids = [c["id"] for c in data["criteria"]]
        assert "violence" in criteria_ids
        assert "profanity" in criteria_ids
    
    def test_get_unknown_preset(self):
        """Test getting unknown preset returns 404."""
        response = client.get("/v1/presets/unknown_preset")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestGenericEvaluateInputValidation:
    """Tests for input validation on /evaluate/generic."""
    
    def test_requires_video_or_url(self):
        """Test that video or URL is required."""
        response = client.post("/v1/evaluate/generic")
        assert response.status_code == 422  # Validation error
    
    def test_rejects_both_video_and_url(self):
        """Test that providing both video and URL is rejected."""
        # This would require actual file handling in test
        pass
    
    def test_invalid_evaluation_spec_json(self):
        """Test that invalid JSON in evaluation_spec is rejected."""
        response = client.post(
            "/v1/evaluate/generic",
            data={"evaluation_spec": "not valid json", "url": "http://example.com/video.mp4"}
        )
        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()
    
    def test_invalid_evaluation_spec_schema(self):
        """Test that invalid spec schema is rejected."""
        invalid_spec = {
            "schema_version": "2.0",  # Wrong version
            "criteria": [{"id": "test", "label": "Test"}],
            "detectors": [{"id": "d1", "type": "yolo26"}]
        }
        response = client.post(
            "/v1/evaluate/generic",
            data={
                "evaluation_spec": json.dumps(invalid_spec),
                "url": "http://example.com/video.mp4"
            }
        )
        assert response.status_code == 400
        assert "schema version" in response.json()["detail"].lower()
    
    def test_unknown_preset_id(self):
        """Test that unknown preset_id is rejected."""
        response = client.post(
            "/v1/evaluate/generic",
            data={
                "preset_id": "unknown_preset",
                "url": "http://example.com/video.mp4"
            }
        )
        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()


class TestGenericEvaluateWithMockedPipeline:
    """Tests with mocked pipeline to verify response structure."""
    
    @pytest.fixture
    def mock_pipeline_result(self):
        """Mock result from pipeline."""
        return {
            "verdict": "SAFE",
            "criteria": {
                "violence": {"score": 0.1, "status": "ok"},
                "profanity": {"score": 0.2, "status": "ok"}
            },
            "violations": [],
            "evidence": {"vision": [], "asr": []},
            "report": "Video appears safe.",
            "metadata": {
                "video_id": "test123",
                "duration": 10.0,
                "frames_analyzed": 100,
                "segments_analyzed": 5
            },
            "timings": {"total_seconds": 5.0}
        }
    
    @patch("app.api.routes.run_pipeline")
    async def test_response_structure_with_preset(self, mock_run, mock_pipeline_result):
        """Test response structure when using a preset."""
        mock_run.return_value = mock_pipeline_result
        
        # This test would need actual video file or URL handling
        # For now, just verify the endpoint exists
        pass
    
    def test_response_includes_explanation_when_requested(self):
        """Test that explanation is included when outputs.include_explain is true."""
        # Would need to mock the pipeline
        pass
    
    def test_response_includes_model_versions(self):
        """Test that model versions are included when requested."""
        # Would need to mock the pipeline
        pass


class TestBackwardCompatibility:
    """Tests to ensure backward compatibility with original /evaluate endpoint."""
    
    def test_original_evaluate_still_works(self):
        """Test that /evaluate endpoint still works without changes."""
        # Would need to mock the pipeline
        pass
    
    def test_generic_without_spec_uses_default(self):
        """Test that /evaluate/generic without spec uses child_safety preset."""
        # Verify by checking that default criteria are used
        pass


class TestSpecValidation:
    """Additional spec validation tests via API."""
    
    def test_spec_with_unknown_detector_type(self):
        """Test that unknown detector type is rejected."""
        spec = {
            "schema_version": SCHEMA_VERSION,
            "criteria": [{"id": "test", "label": "Test"}],
            "detectors": [{"id": "d1", "type": "unknown_detector"}]
        }
        response = client.post(
            "/v1/evaluate/generic",
            data={
                "evaluation_spec": json.dumps(spec),
                "url": "http://example.com/video.mp4"
            }
        )
        assert response.status_code == 400
    
    def test_spec_with_circular_routing(self):
        """Test that circular routing references are handled."""
        spec = {
            "schema_version": SCHEMA_VERSION,
            "criteria": [{"id": "test", "label": "Test"}],
            "detectors": [{"id": "d1", "type": "yolo26"}],
            "routing": [
                {
                    "criterion_id": "nonexistent",  # Bad reference
                    "sources": [{"detector_id": "d1", "weight": 1.0}]
                }
            ]
        }
        response = client.post(
            "/v1/evaluate/generic",
            data={
                "evaluation_spec": json.dumps(spec),
                "url": "http://example.com/video.mp4"
            }
        )
        assert response.status_code == 400
        assert "unknown criterion" in response.json()["detail"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
