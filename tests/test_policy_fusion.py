"""
Test policy fusion engine.
"""
import pytest
from app.pipeline.state import PipelineState
from app.pipeline.nodes.fuse_policy import PolicyEngine
from app.core.config import get_policy_config


def test_policy_engine_safe_verdict():
    """Test that low scores produce SAFE verdict."""
    config = get_policy_config()
    engine = PolicyEngine(config)
    
    scores = {
        "violence": 0.1,
        "profanity": 0.2,
        "sexual": 0.1,
        "drugs": 0.1,
        "hate": 0.05
    }
    
    verdict = engine.determine_verdict(scores)
    assert verdict == "SAFE"


def test_policy_engine_unsafe_verdict():
    """Test that high violence score produces UNSAFE verdict."""
    config = get_policy_config()
    engine = PolicyEngine(config)
    
    scores = {
        "violence": 0.85,  # Above unsafe threshold (0.75)
        "profanity": 0.2,
        "sexual": 0.1,
        "drugs": 0.1,
        "hate": 0.05
    }
    
    verdict = engine.determine_verdict(scores)
    assert verdict == "UNSAFE"


def test_policy_engine_caution_verdict():
    """Test that medium profanity score produces CAUTION verdict."""
    config = get_policy_config()
    engine = PolicyEngine(config)
    
    scores = {
        "violence": 0.2,
        "profanity": 0.5,  # Above caution threshold (0.4)
        "sexual": 0.1,
        "drugs": 0.2,
        "hate": 0.05
    }
    
    verdict = engine.determine_verdict(scores)
    assert verdict == "CAUTION"


def test_policy_engine_multiple_violations():
    """Test extraction of multiple violations."""
    config = get_policy_config()
    engine = PolicyEngine(config)
    
    # Create mock state with evidence
    state = PipelineState(
        violence_segments=[
            {
                "id": "violence_segment_001",
                "start_time": 10.0,
                "end_time": 15.0,
                "violence_score": 0.8,
            }
        ],
        transcript_moderation=[
            {
                "id": "asr_span_001",
                "start_time": 20.0,
                "end_time": 25.0,
                "profanity_score": 0.7,
                "violence_score": 0.1,
                "sexual_score": 0.1,
                "drugs_score": 0.1,
                "hate_score": 0.1,
            }
        ],
        vision_detections=[],
        ocr_moderation=[]
    )
    
    scores = {
        "violence": 0.8,
        "profanity": 0.7,
        "sexual": 0.1,
        "drugs": 0.1,
        "hate": 0.1
    }
    
    violations = engine.extract_violations(scores, state)
    
    # Should have at least 2 violations (violence and profanity)
    assert len(violations) >= 2
    
    # Check that violations have required fields
    for violation in violations:
        assert "criterion" in violation
        assert "severity" in violation
        assert "score" in violation
        assert "timestamp_ranges" in violation
        assert "evidence_refs" in violation


def test_violence_score_computation():
    """Test violence score computation from evidence."""
    config = get_policy_config()
    engine = PolicyEngine(config)
    
    # Mock high violence from model
    state = PipelineState(
        violence_segments=[
            {"violence_score": 0.9},
            {"violence_score": 0.7},
        ],
        vision_detections=[
            {"category": "weapon", "label": "knife"},
        ],
        transcript_moderation=[
            {"violence_score": 0.3},
        ]
    )
    
    scores = engine.compute_scores(state)
    
    # Violence score should be high
    assert scores["violence"] > 0.5


def test_profanity_score_computation():
    """Test profanity score computation."""
    config = get_policy_config()
    engine = PolicyEngine(config)
    
    state = PipelineState(
        violence_segments=[],
        vision_detections=[],
        transcript_moderation=[
            {"profanity_score": 0.8, "profanity_words": ["fuck", "shit"]},
            {"profanity_score": 0.6, "profanity_words": ["damn"]},
        ],
        ocr_moderation=[
            {"profanity_score": 0.3},
        ]
    )
    
    scores = engine.compute_scores(state)
    
    # Profanity score should be significant
    assert scores["profanity"] > 0.4


def test_drugs_score_with_vision():
    """Test drugs score with substance detections."""
    config = get_policy_config()
    engine = PolicyEngine(config)
    
    state = PipelineState(
        violence_segments=[],
        vision_detections=[
            {"category": "substance", "label": "syringe"},
            {"category": "substance", "label": "bottle"},
        ],
        transcript_moderation=[
            {"drugs_score": 0.4},
        ],
        ocr_moderation=[]
    )
    
    scores = engine.compute_scores(state)
    
    # Drugs score should be elevated
    assert scores["drugs"] > 0.3


def test_threshold_overrides():
    """Test that policy config overrides work."""
    # Override thresholds
    config = get_policy_config({
        "thresholds": {
            "unsafe": {
                "violence": 0.5  # Lower threshold
            }
        }
    })
    
    engine = PolicyEngine(config)
    
    scores = {
        "violence": 0.6,  # Above new threshold (0.5) but below default (0.75)
        "profanity": 0.1,
        "sexual": 0.1,
        "drugs": 0.1,
        "hate": 0.1
    }
    
    verdict = engine.determine_verdict(scores)
    assert verdict == "UNSAFE"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
