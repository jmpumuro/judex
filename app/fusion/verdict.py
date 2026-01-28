"""
Verdict Determination Strategies.

Encapsulates the logic for determining final verdict from criterion scores.
Follows Strategy pattern for extensibility.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from dataclasses import dataclass
from enum import Enum
import os

from app.core.logging import get_logger

logger = get_logger("fusion.verdict")


class VerdictLevel(str, Enum):
    """Possible verdict outcomes."""
    SAFE = "SAFE"
    CAUTION = "CAUTION"
    UNSAFE = "UNSAFE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass
class VerdictResult:
    """Result of verdict determination."""
    verdict: VerdictLevel
    confidence: float
    contributing_criteria: List[str]  # Criteria that influenced the verdict


class VerdictStrategy(ABC):
    """Abstract base for verdict determination strategies."""
    
    @abstractmethod
    def determine(self, criteria_scores: Dict[str, Dict[str, Any]]) -> VerdictResult:
        """
        Determine final verdict from criterion scores.
        
        Args:
            criteria_scores: Dict of criterion_id -> {score, verdict, label, severity}
            
        Returns:
            VerdictResult with final verdict and confidence
        """
        pass


class AnyUnsafeStrategy(VerdictStrategy):
    """
    ANY_UNSAFE: One unsafe criterion makes entire video unsafe.
    
    This is the most conservative approach - appropriate for child safety.
    """
    
    def determine(self, criteria_scores: Dict[str, Dict[str, Any]]) -> VerdictResult:
        unsafe_criteria = [
            cid for cid, data in criteria_scores.items() 
            if data.get("verdict") == "UNSAFE"
        ]
        caution_criteria = [
            cid for cid, data in criteria_scores.items() 
            if data.get("verdict") == "CAUTION"
        ]
        
        if unsafe_criteria:
            max_score = max(
                criteria_scores[cid]["score"] for cid in unsafe_criteria
            )
            return VerdictResult(
                verdict=VerdictLevel.UNSAFE,
                confidence=max_score,
                contributing_criteria=unsafe_criteria
            )
        elif caution_criteria:
            max_score = max(
                criteria_scores[cid]["score"] for cid in caution_criteria
            )
            return VerdictResult(
                verdict=VerdictLevel.CAUTION,
                confidence=max_score,
                contributing_criteria=caution_criteria
            )
        else:
            all_scores = [d["score"] for d in criteria_scores.values()]
            min_score = min(all_scores) if all_scores else 0
            return VerdictResult(
                verdict=VerdictLevel.SAFE,
                confidence=1.0 - min_score,
                contributing_criteria=[]
            )


class MajorityUnsafeStrategy(VerdictStrategy):
    """
    MAJORITY_UNSAFE: Majority of criteria must be unsafe.
    
    More lenient - appropriate for general content moderation.
    """
    
    def determine(self, criteria_scores: Dict[str, Dict[str, Any]]) -> VerdictResult:
        total = len(criteria_scores)
        if total == 0:
            return VerdictResult(VerdictLevel.SAFE, 1.0, [])
        
        unsafe_criteria = [
            cid for cid, data in criteria_scores.items() 
            if data.get("verdict") == "UNSAFE"
        ]
        
        if len(unsafe_criteria) > total / 2:
            avg_score = sum(
                criteria_scores[cid]["score"] for cid in unsafe_criteria
            ) / len(unsafe_criteria)
            return VerdictResult(
                verdict=VerdictLevel.UNSAFE,
                confidence=avg_score,
                contributing_criteria=unsafe_criteria
            )
        elif unsafe_criteria:
            return VerdictResult(
                verdict=VerdictLevel.CAUTION,
                confidence=len(unsafe_criteria) / total,
                contributing_criteria=unsafe_criteria
            )
        else:
            return VerdictResult(
                verdict=VerdictLevel.SAFE,
                confidence=1.0,
                contributing_criteria=[]
            )


class WeightedAverageStrategy(VerdictStrategy):
    """
    WEIGHTED_AVERAGE: Uses severity-weighted average of scores.
    
    Configurable thresholds determine verdict.
    """
    
    # Configurable thresholds
    unsafe_threshold: float = 0.7
    caution_threshold: float = 0.3
    
    def __init__(self):
        # Allow env override
        if val := os.getenv("VERDICT_UNSAFE_THRESHOLD"):
            self.unsafe_threshold = float(val)
        if val := os.getenv("VERDICT_CAUTION_THRESHOLD"):
            self.caution_threshold = float(val)
    
    def determine(self, criteria_scores: Dict[str, Dict[str, Any]]) -> VerdictResult:
        if not criteria_scores:
            return VerdictResult(VerdictLevel.SAFE, 1.0, [])
        
        # Weight by severity
        severity_weights = {
            "critical": 2.0,
            "high": 1.5,
            "medium": 1.0,
            "low": 0.5
        }
        
        weighted_sum = 0.0
        total_weight = 0.0
        contributing = []
        
        for cid, data in criteria_scores.items():
            weight = severity_weights.get(data.get("severity", "medium"), 1.0)
            score = data.get("score", 0)
            weighted_sum += score * weight
            total_weight += weight
            
            if score > self.caution_threshold:
                contributing.append(cid)
        
        avg_score = weighted_sum / total_weight if total_weight > 0 else 0
        
        if avg_score >= self.unsafe_threshold:
            verdict = VerdictLevel.UNSAFE
        elif avg_score >= self.caution_threshold:
            verdict = VerdictLevel.CAUTION
        else:
            verdict = VerdictLevel.SAFE
        
        return VerdictResult(
            verdict=verdict,
            confidence=avg_score if verdict != VerdictLevel.SAFE else 1.0 - avg_score,
            contributing_criteria=contributing
        )


class CriticalOnlyStrategy(VerdictStrategy):
    """
    CRITICAL_ONLY: Only critical-severity criteria can cause UNSAFE.
    
    Other severities can only cause CAUTION at most.
    """
    
    def determine(self, criteria_scores: Dict[str, Dict[str, Any]]) -> VerdictResult:
        critical_unsafe = [
            cid for cid, data in criteria_scores.items()
            if data.get("verdict") == "UNSAFE" and data.get("severity") == "critical"
        ]
        
        any_unsafe = [
            cid for cid, data in criteria_scores.items()
            if data.get("verdict") == "UNSAFE"
        ]
        
        if critical_unsafe:
            max_score = max(
                criteria_scores[cid]["score"] for cid in critical_unsafe
            )
            return VerdictResult(
                verdict=VerdictLevel.UNSAFE,
                confidence=max_score,
                contributing_criteria=critical_unsafe
            )
        elif any_unsafe:
            max_score = max(
                criteria_scores[cid]["score"] for cid in any_unsafe
            )
            return VerdictResult(
                verdict=VerdictLevel.CAUTION,
                confidence=max_score,
                contributing_criteria=any_unsafe
            )
        else:
            return VerdictResult(
                verdict=VerdictLevel.SAFE,
                confidence=1.0,
                contributing_criteria=[]
            )


# Strategy Registry
_VERDICT_STRATEGIES: Dict[str, type] = {
    "any_unsafe": AnyUnsafeStrategy,
    "majority_unsafe": MajorityUnsafeStrategy,
    "weighted_average": WeightedAverageStrategy,
    "critical_only": CriticalOnlyStrategy,
}


def get_verdict_strategy(strategy_name: str = None) -> VerdictStrategy:
    """
    Get a verdict strategy by name.
    
    Defaults to any_unsafe if not specified.
    Can be overridden via VERDICT_STRATEGY env var.
    """
    if strategy_name is None:
        strategy_name = os.getenv("VERDICT_STRATEGY", "any_unsafe")
    
    strategy_class = _VERDICT_STRATEGIES.get(strategy_name.lower())
    if not strategy_class:
        logger.warning(f"Unknown verdict strategy '{strategy_name}', using any_unsafe")
        strategy_class = AnyUnsafeStrategy
    
    return strategy_class()


def register_verdict_strategy(name: str, strategy_class: type) -> None:
    """Register a custom verdict strategy."""
    _VERDICT_STRATEGIES[name.lower()] = strategy_class
    logger.info(f"Registered verdict strategy: {name}")


def list_verdict_strategies() -> List[str]:
    """List available verdict strategies."""
    return list(_VERDICT_STRATEGIES.keys())
