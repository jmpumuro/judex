"""
Unified Result Models - Industry-standard format for evaluation results.

Single source of truth for all result structures used across:
- Fusion output
- Finalize node
- Database storage
- API responses
"""
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
from enum import Enum


class Verdict(str, Enum):
    """Evaluation verdict levels."""
    SAFE = "SAFE"
    CAUTION = "CAUTION"
    UNSAFE = "UNSAFE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass
class CriterionScore:
    """
    Score for a single criterion.
    
    This is the unified format used everywhere in the pipeline.
    """
    score: float          # 0.0 to 1.0
    verdict: str          # SAFE, CAUTION, UNSAFE
    label: str            # Human-readable name
    severity: str         # low, medium, high, critical
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CriterionScore":
        """Create from dict, handling various input formats."""
        if isinstance(data, (int, float)):
            # Simple score value - derive verdict
            score = float(data)
            return cls(
                score=score,
                verdict="UNSAFE" if score >= 0.7 else "CAUTION" if score >= 0.3 else "SAFE",
                label="Unknown",
                severity="medium"
            )
        return cls(
            score=data.get("score", 0.0),
            verdict=data.get("verdict", "SAFE"),
            label=data.get("label", "Unknown"),
            severity=data.get("severity", "medium")
        )


@dataclass
class Violation:
    """A detected policy violation."""
    criterion: str        # Criterion ID
    label: str            # Human-readable name
    severity: str         # low, medium, high, critical
    score: float          # Score that triggered violation
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass  
class EvaluationResult:
    """
    Complete evaluation result.
    
    This is the unified structure returned by the pipeline
    and stored in the database.
    """
    verdict: Verdict
    confidence: float
    criteria: Dict[str, CriterionScore]  # criterion_id -> score
    violations: List[Violation]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "verdict": self.verdict.value if isinstance(self.verdict, Verdict) else self.verdict,
            "confidence": round(self.confidence, 3),
            "criteria": {k: v.to_dict() for k, v in self.criteria.items()},
            "violations": [v.to_dict() for v in self.violations]
        }
    
    def get_score(self, criterion_id: str) -> float:
        """Get score for a criterion (0.0 if not found)."""
        if criterion_id in self.criteria:
            return self.criteria[criterion_id].score
        return 0.0
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvaluationResult":
        """Create from dict."""
        criteria = {}
        for k, v in data.get("criteria", {}).items():
            criteria[k] = CriterionScore.from_dict(v)
        
        violations = [
            Violation(**v) if isinstance(v, dict) else v
            for v in data.get("violations", [])
        ]
        
        verdict = data.get("verdict", "NEEDS_REVIEW")
        if isinstance(verdict, str):
            verdict = Verdict(verdict) if verdict in Verdict.__members__ else Verdict.NEEDS_REVIEW
        
        return cls(
            verdict=verdict,
            confidence=data.get("confidence", 0.0),
            criteria=criteria,
            violations=violations
        )


def create_criterion_score(
    score: float,
    label: str,
    severity: str,
    safe_threshold: float = 0.3,
    caution_threshold: float = 0.6,
    unsafe_threshold: float = 0.7
) -> CriterionScore:
    """
    Factory function to create a CriterionScore with automatic verdict.
    
    Args:
        score: Raw score (0.0 to 1.0)
        label: Human-readable name
        severity: Criterion severity
        safe_threshold: Below this = SAFE
        caution_threshold: Below this = CAUTION  
        unsafe_threshold: Above this = UNSAFE
    """
    if score >= unsafe_threshold:
        verdict = "UNSAFE"
    elif score >= caution_threshold:
        verdict = "CAUTION"
    else:
        verdict = "SAFE"
    
    return CriterionScore(
        score=round(score, 3),
        verdict=verdict,
        label=label,
        severity=severity
    )
