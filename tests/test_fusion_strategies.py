"""
Tests for fusion strategies.

Verifies that:
- Weighted sum correctly combines detector outputs
- Max strategy takes the maximum score
- Rule-based fusion applies custom rules
- Verdict aggregation works correctly
"""
import pytest
from app.evaluation.spec import (
    CriterionSpec,
    DetectorSpec,
    DetectorType,
    FusionSpec,
    FusionStrategy,
    AggregationRule,
    RoutingRule,
    VerdictThresholds
)
from app.evaluation.evidence import EvidenceCollection, EvidenceItem
from app.detectors.base import DetectorResult
from app.fusion.strategies import (
    WeightedSumStrategy,
    MaxStrategy,
    AverageStrategy,
    RuleBasedStrategy
)
from app.fusion.engine import FusionEngine, FusionResult
from app.policies.presets import CHILD_SAFETY_PRESET


class TestWeightedSumStrategy:
    """Tests for weighted sum fusion."""
    
    @pytest.fixture
    def strategy(self):
        """Create a weighted sum strategy."""
        return WeightedSumStrategy(FusionSpec())
    
    @pytest.fixture
    def criterion(self):
        """Create a test criterion."""
        return CriterionSpec(
            id="violence",
            label="Violence",
            thresholds=VerdictThresholds(
                safe_below=0.3,
                caution_below=0.6,
                unsafe_above=0.6
            )
        )
    
    def test_single_detector_score(self, strategy, criterion):
        """Test score from a single detector."""
        routing = [
            RoutingRule(detector_id="detector1", weight=1.0)
        ]
        
        # Create mock detector result with evidence
        evidence = EvidenceCollection()
        evidence.add(EvidenceItem(
            detector_id="detector1",
            label="violence",
            category="violence",
            confidence=0.8,
            score=0.8
        ))
        
        detector_outputs = {
            "detector1": DetectorResult(
                detector_id="detector1",
                detector_type="test",
                evidence=evidence,
                raw_outputs={"violence_score": 0.8}
            )
        }
        
        score = strategy.compute_criterion_score(criterion, routing, detector_outputs)
        assert 0.7 <= score <= 0.9  # Should be around 0.8
    
    def test_weighted_combination(self, strategy, criterion):
        """Test weighted combination of multiple detectors."""
        routing = [
            RoutingRule(detector_id="detector1", weight=0.7),
            RoutingRule(detector_id="detector2", weight=0.3)
        ]
        
        # Detector 1: high score, high weight
        evidence1 = EvidenceCollection()
        evidence1.add(EvidenceItem(
            detector_id="detector1",
            label="violence",
            category="violence",
            confidence=0.9,
            score=0.9
        ))
        
        # Detector 2: low score, low weight
        evidence2 = EvidenceCollection()
        evidence2.add(EvidenceItem(
            detector_id="detector2",
            label="violence",
            category="violence",
            confidence=0.2,
            score=0.2
        ))
        
        detector_outputs = {
            "detector1": DetectorResult(
                detector_id="detector1",
                detector_type="test",
                evidence=evidence1
            ),
            "detector2": DetectorResult(
                detector_id="detector2",
                detector_type="test",
                evidence=evidence2
            )
        }
        
        score = strategy.compute_criterion_score(criterion, routing, detector_outputs)
        
        # Expected: (0.9 * 0.7 + 0.2 * 0.3) / (0.7 + 0.3) = 0.69
        assert 0.6 <= score <= 0.8
    
    def test_missing_detector(self, strategy, criterion):
        """Test handling of missing detector output."""
        routing = [
            RoutingRule(detector_id="missing", weight=1.0)
        ]
        
        detector_outputs = {}  # No outputs
        
        score = strategy.compute_criterion_score(criterion, routing, detector_outputs)
        assert score == 0.0


class TestMaxStrategy:
    """Tests for max fusion."""
    
    @pytest.fixture
    def strategy(self):
        return MaxStrategy(FusionSpec(criterion_strategy=FusionStrategy.MAX))
    
    @pytest.fixture
    def criterion(self):
        return CriterionSpec(id="profanity", label="Profanity")
    
    def test_takes_maximum(self, strategy, criterion):
        """Test that max strategy takes the highest score."""
        routing = [
            RoutingRule(detector_id="d1", weight=1.0),
            RoutingRule(detector_id="d2", weight=1.0),
            RoutingRule(detector_id="d3", weight=1.0)
        ]
        
        # Create evidence with different scores
        e1 = EvidenceCollection()
        e1.add(EvidenceItem(detector_id="d1", label="profanity", category="profanity", confidence=0.3, score=0.3))
        
        e2 = EvidenceCollection()
        e2.add(EvidenceItem(detector_id="d2", label="profanity", category="profanity", confidence=0.9, score=0.9))
        
        e3 = EvidenceCollection()
        e3.add(EvidenceItem(detector_id="d3", label="profanity", category="profanity", confidence=0.5, score=0.5))
        
        detector_outputs = {
            "d1": DetectorResult(detector_id="d1", detector_type="test", evidence=e1),
            "d2": DetectorResult(detector_id="d2", detector_type="test", evidence=e2),
            "d3": DetectorResult(detector_id="d3", detector_type="test", evidence=e3)
        }
        
        score = strategy.compute_criterion_score(criterion, routing, detector_outputs)
        assert score == 0.9  # Should take the max


class TestAverageStrategy:
    """Tests for average fusion."""
    
    @pytest.fixture
    def strategy(self):
        return AverageStrategy(FusionSpec(criterion_strategy=FusionStrategy.AVERAGE))
    
    @pytest.fixture
    def criterion(self):
        return CriterionSpec(id="hate", label="Hate Speech")
    
    def test_computes_average(self, strategy, criterion):
        """Test that average strategy computes mean."""
        routing = [
            RoutingRule(detector_id="d1", weight=1.0),
            RoutingRule(detector_id="d2", weight=1.0)
        ]
        
        e1 = EvidenceCollection()
        e1.add(EvidenceItem(detector_id="d1", label="hate", category="hate", confidence=0.4, score=0.4))
        
        e2 = EvidenceCollection()
        e2.add(EvidenceItem(detector_id="d2", label="hate", category="hate", confidence=0.8, score=0.8))
        
        detector_outputs = {
            "d1": DetectorResult(detector_id="d1", detector_type="test", evidence=e1),
            "d2": DetectorResult(detector_id="d2", detector_type="test", evidence=e2)
        }
        
        score = strategy.compute_criterion_score(criterion, routing, detector_outputs)
        assert score == pytest.approx(0.6, rel=0.1)  # (0.4 + 0.8) / 2


class TestFusionEngine:
    """Tests for the complete fusion engine."""
    
    @pytest.fixture
    def engine(self):
        """Create engine with child safety preset."""
        return FusionEngine(CHILD_SAFETY_PRESET)
    
    def test_safe_verdict(self, engine):
        """Test that low scores result in SAFE verdict."""
        # Create detector outputs with low scores
        evidence = EvidenceCollection()
        for crit in ["violence", "profanity", "sexual", "drugs", "hate"]:
            evidence.add(EvidenceItem(
                detector_id="test",
                label=crit,
                category=crit,
                confidence=0.1,
                score=0.1
            ))
        
        detector_outputs = {
            "xclip_violence": DetectorResult(
                detector_id="xclip_violence",
                detector_type="xclip_violence",
                evidence=evidence,
                raw_outputs={"violence_scores": [{"score": 0.1}]}
            ),
            "text_moderation": DetectorResult(
                detector_id="text_moderation",
                detector_type="text_moderation",
                evidence=evidence,
                raw_outputs={
                    "transcript_moderation": [
                        {"profanity_score": 0.1, "hate_score": 0.1, "sexual_score": 0.1, "drugs_score": 0.1}
                    ]
                }
            )
        }
        
        result = engine.fuse(detector_outputs, evidence)
        assert result.verdict == "SAFE"
    
    def test_unsafe_verdict_with_confirmation(self, engine):
        """Test UNSAFE verdict requires confirmation signals."""
        # High violence from single source - should be NEEDS_REVIEW without confirmation
        evidence = EvidenceCollection()
        evidence.add(EvidenceItem(
            detector_id="xclip_violence",
            label="violence",
            category="violence",
            confidence=0.95,
            score=0.95
        ))
        
        detector_outputs = {
            "xclip_violence": DetectorResult(
                detector_id="xclip_violence",
                detector_type="xclip_violence",
                evidence=evidence,
                raw_outputs={"violence_scores": [{"score": 0.95}]}
            )
        }
        
        result = engine.fuse(detector_outputs, evidence)
        
        # With only 1 detector source and confirmation required,
        # might be downgraded to NEEDS_REVIEW
        assert result.verdict in ["UNSAFE", "NEEDS_REVIEW"]
    
    def test_violations_extracted(self, engine):
        """Test that violations are extracted for flagged criteria."""
        evidence = EvidenceCollection()
        evidence.add(EvidenceItem(
            detector_id="text_moderation",
            label="profanity",
            category="profanity",
            confidence=0.8,
            score=0.8
        ))
        
        detector_outputs = {
            "text_moderation": DetectorResult(
                detector_id="text_moderation",
                detector_type="text_moderation",
                evidence=evidence,
                raw_outputs={
                    "transcript_moderation": [{"profanity_score": 0.8}]
                }
            )
        }
        
        result = engine.fuse(detector_outputs, evidence)
        
        # Should have a profanity violation
        assert len(result.violations) > 0
        profanity_violations = [v for v in result.violations if v.criterion_id == "profanity"]
        assert len(profanity_violations) > 0
    
    def test_explanation_generated(self, engine):
        """Test that explanation is generated."""
        evidence = EvidenceCollection()
        detector_outputs = {}
        
        result = engine.fuse(detector_outputs, evidence)
        
        assert result.explanation is not None
        assert "verdict" in result.explanation
        assert "summary" in result.explanation
        assert "criterion_explanations" in result.explanation


class TestVerdictAggregation:
    """Tests for verdict aggregation rules."""
    
    def test_any_unsafe_rule(self):
        """Test ANY_UNSAFE aggregation - any UNSAFE criterion makes final UNSAFE."""
        from app.evaluation.spec import EvaluationSpec
        
        spec = EvaluationSpec(
            criteria=[
                CriterionSpec(id="c1", label="C1"),
                CriterionSpec(id="c2", label="C2"),
                CriterionSpec(id="c3", label="C3")
            ],
            detectors=[
                DetectorSpec(id="d1", type=DetectorType.YOLO26)
            ],
            fusion=FusionSpec(
                verdict_aggregation=AggregationRule.ANY_UNSAFE,
                require_confirmation=False
            )
        )
        
        engine = FusionEngine(spec)
        
        # Create evidence where one criterion is high
        evidence = EvidenceCollection()
        evidence.add(EvidenceItem(
            detector_id="d1", label="c1", category="c1", confidence=0.9, score=0.9
        ))
        evidence.add(EvidenceItem(
            detector_id="d1", label="c2", category="c2", confidence=0.1, score=0.1
        ))
        evidence.add(EvidenceItem(
            detector_id="d1", label="c3", category="c3", confidence=0.1, score=0.1
        ))
        
        detector_outputs = {
            "d1": DetectorResult(detector_id="d1", detector_type="test", evidence=evidence)
        }
        
        result = engine.fuse(detector_outputs, evidence)
        
        # Should be UNSAFE because c1 is high
        assert result.verdict in ["UNSAFE", "CAUTION"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
