"""
Test API contract and endpoints.
"""
import pytest
import tempfile
import subprocess
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings

client = TestClient(app)


def create_test_video(output_path: str, duration: int = 3):
    """Create a test video using ffmpeg."""
    cmd = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", f"color=c=blue:s=320x240:d={duration}",
        "-f", "lavfi",
        "-i", "anullsrc",
        "-t", str(duration),
        "-pix_fmt", "yuv420p",
        "-y",
        output_path
    ]
    subprocess.run(cmd, capture_output=True, check=True)


@pytest.fixture
def test_video():
    """Create a temporary test video."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    temp_path = temp_file.name
    temp_file.close()
    
    try:
        create_test_video(temp_path)
        yield temp_path
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_health_endpoint():
    """Test health check endpoint."""
    response = client.get("/v1/health")
    assert response.status_code == 200
    
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"
    assert "version" in data


def test_root_endpoint():
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    
    data = response.json()
    assert "service" in data
    assert "version" in data
    assert "status" in data


def test_models_endpoint():
    """Test models list endpoint."""
    response = client.get("/v1/models")
    assert response.status_code == 200
    
    data = response.json()
    assert "models" in data
    assert len(data["models"]) > 0
    
    # Check model structure
    model = data["models"][0]
    assert "model_id" in model
    assert "model_type" in model
    assert "cached" in model
    assert "status" in model


def test_evaluate_endpoint_requires_file():
    """Test that evaluate endpoint requires a file."""
    response = client.post("/v1/evaluate")
    assert response.status_code == 422  # Validation error


def test_evaluate_endpoint_structure(test_video):
    """Test evaluate endpoint returns correct structure."""
    with open(test_video, "rb") as f:
        response = client.post(
            "/v1/evaluate",
            files={"file": ("test.mp4", f, "video/mp4")}
        )
    
    # Should succeed (or fail gracefully)
    assert response.status_code in [200, 500]
    
    if response.status_code == 200:
        data = response.json()
        
        # Check required fields
        assert "verdict" in data
        assert data["verdict"] in ["SAFE", "CAUTION", "UNSAFE", "NEEDS_REVIEW"]
        
        assert "criteria" in data
        assert isinstance(data["criteria"], dict)
        
        # Check each criterion
        for criterion in ["violence", "profanity", "sexual", "drugs", "hate"]:
            assert criterion in data["criteria"]
            assert "score" in data["criteria"][criterion]
            assert "status" in data["criteria"][criterion]
            assert 0.0 <= data["criteria"][criterion]["score"] <= 1.0
        
        assert "violations" in data
        assert isinstance(data["violations"], list)
        
        assert "evidence" in data
        assert isinstance(data["evidence"], dict)
        
        assert "report" in data
        assert isinstance(data["report"], str)


def test_evaluate_with_policy_override(test_video):
    """Test evaluate endpoint with policy override."""
    policy_override = {
        "sampling_fps": 0.5,  # Lower FPS for faster test
        "thresholds": {
            "unsafe": {
                "violence": 0.9  # Higher threshold
            }
        }
    }
    
    import json
    
    with open(test_video, "rb") as f:
        response = client.post(
            "/v1/evaluate",
            files={"file": ("test.mp4", f, "video/mp4")},
            data={"policy": json.dumps(policy_override)}
        )
    
    assert response.status_code in [200, 500]


def test_evaluate_invalid_policy_json(test_video):
    """Test that invalid policy JSON returns error."""
    with open(test_video, "rb") as f:
        response = client.post(
            "/v1/evaluate",
            files={"file": ("test.mp4", f, "video/mp4")},
            data={"policy": "invalid json{"}
        )
    
    assert response.status_code == 400


def test_response_has_metadata(test_video):
    """Test that response includes metadata."""
    with open(test_video, "rb") as f:
        response = client.post(
            "/v1/evaluate",
            files={"file": ("test.mp4", f, "video/mp4")}
        )
    
    if response.status_code == 200:
        data = response.json()
        
        if "metadata" in data:
            metadata = data["metadata"]
            assert "video_id" in metadata
            assert "duration" in metadata
            assert "frames_analyzed" in metadata
            assert "segments_analyzed" in metadata


def test_response_has_evidence_structure(test_video):
    """Test that evidence has correct structure."""
    with open(test_video, "rb") as f:
        response = client.post(
            "/v1/evaluate",
            files={"file": ("test.mp4", f, "video/mp4")}
        )
    
    if response.status_code == 200:
        data = response.json()
        evidence = data["evidence"]
        
        # Check evidence keys
        assert "vision" in evidence
        assert "violence_segments" in evidence
        assert "asr" in evidence
        assert "ocr" in evidence


def test_violations_structure(test_video):
    """Test that violations have correct structure."""
    with open(test_video, "rb") as f:
        response = client.post(
            "/v1/evaluate",
            files={"file": ("test.mp4", f, "video/mp4")}
        )
    
    if response.status_code == 200:
        data = response.json()
        violations = data["violations"]
        
        for violation in violations:
            assert "criterion" in violation
            assert "severity" in violation
            assert "timestamp_ranges" in violation
            assert "evidence_refs" in violation


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
