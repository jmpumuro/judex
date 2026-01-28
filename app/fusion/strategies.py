"""
Fusion strategies for computing criterion scores from evidence.

Each strategy implements a different algorithm for combining
multiple detector signals into a single criterion score.
"""
from typing import Dict, List, Any, Optional
from abc import ABC, abstractmethod
from app.evaluation.evidence import EvidenceCollection
from app.evaluation.spec import (
    CriterionSpec,
    RoutingRule,
    FusionSpec,
    FusionStrategy as FusionStrategyEnum
)
from app.detectors.base import DetectorResult


class BaseFusionStrategy(ABC):
    """
    Abstract base class for fusion strategies.
    """
    
    strategy_type: str = "base"
    
    def __init__(self, spec: FusionSpec):
        self.spec = spec
    
    @abstractmethod
    def compute_criterion_score(
        self,
        criterion: CriterionSpec,
        routing_rules: List[RoutingRule],
        detector_outputs: Dict[str, DetectorResult]
    ) -> float:
        """
        Compute the score for a criterion from detector outputs.
        
        Args:
            criterion: The criterion specification
            routing_rules: Rules mapping detectors to this criterion
            detector_outputs: Dict of detector_id -> DetectorResult
            
        Returns:
            Score between 0.0 and 1.0
        """
        pass
    
    def _extract_scores_from_detector(
        self,
        detector_id: str,
        output_field: str,
        detector_outputs: Dict[str, DetectorResult],
        criterion_id: str
    ) -> List[float]:
        """
        Extract relevant scores from a detector's output.
        
        Args:
            detector_id: ID of the detector
            output_field: Field to extract from (or "*" for all)
            detector_outputs: All detector results
            criterion_id: Criterion we're computing for (for filtering)
            
        Returns:
            List of scores (0.0-1.0)
        """
        if detector_id not in detector_outputs:
            return []
        
        result = detector_outputs[detector_id]
        scores = []
        
        # Try to get scores from evidence first
        for item in result.evidence:
            if item.score is not None:
                # Filter by category if it matches criterion
                if item.category and item.category.lower() == criterion_id.lower():
                    scores.append(item.score)
                elif not item.category:
                    scores.append(item.score)
        
        # If no evidence scores, try raw outputs
        if not scores:
            raw = result.raw_outputs
            
            if output_field == "*":
                # Extract any score-like values
                scores.extend(self._extract_scores_from_dict(raw, criterion_id))
            elif output_field in raw:
                field_data = raw[output_field]
                scores.extend(self._extract_scores_from_dict(
                    {output_field: field_data},
                    criterion_id
                ))
        
        return scores
    
    def _extract_scores_from_dict(
        self,
        data: Dict[str, Any],
        criterion_id: str
    ) -> List[float]:
        """
        Recursively extract score values from a dict.
        """
        scores = []
        
        for key, value in data.items():
            # Look for score fields
            if isinstance(value, (int, float)) and 0 <= value <= 1:
                key_lower = key.lower()
                criterion_lower = criterion_id.lower()
                
                # Match by criterion name in key
                if criterion_lower in key_lower or "score" in key_lower:
                    scores.append(float(value))
            
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        # Look for criterion-specific scores in list items
                        score_key = f"{criterion_id}_score"
                        if score_key in item:
                            scores.append(float(item[score_key]))
                        elif "score" in item:
                            scores.append(float(item["score"]))
                        elif "confidence" in item:
                            scores.append(float(item["confidence"]))
            
            elif isinstance(value, dict):
                scores.extend(self._extract_scores_from_dict(value, criterion_id))
        
        return [s for s in scores if 0 <= s <= 1]


class WeightedSumStrategy(BaseFusionStrategy):
    """
    Weighted sum fusion strategy.
    
    Computes criterion score as weighted sum of detector scores,
    normalized by total weight.
    """
    
    strategy_type = FusionStrategyEnum.WEIGHTED_SUM.value
    
    def compute_criterion_score(
        self,
        criterion: CriterionSpec,
        routing_rules: List[RoutingRule],
        detector_outputs: Dict[str, DetectorResult]
    ) -> float:
        if not routing_rules:
            return 0.0
        
        total_weight = 0.0
        weighted_sum = 0.0
        
        for rule in routing_rules:
            scores = self._extract_scores_from_detector(
                rule.detector_id,
                rule.output_field,
                detector_outputs,
                criterion.id
            )
            
            if scores:
                # Use max score from this detector
                max_score = max(scores)
                weighted_sum += max_score * rule.weight
                total_weight += rule.weight
        
        if total_weight == 0:
            return 0.0
        
        return min(weighted_sum / total_weight, 1.0)


class MaxStrategy(BaseFusionStrategy):
    """
    Maximum fusion strategy.
    
    Takes the maximum score across all detector sources.
    """
    
    strategy_type = FusionStrategyEnum.MAX.value
    
    def compute_criterion_score(
        self,
        criterion: CriterionSpec,
        routing_rules: List[RoutingRule],
        detector_outputs: Dict[str, DetectorResult]
    ) -> float:
        all_scores = []
        
        for rule in routing_rules:
            scores = self._extract_scores_from_detector(
                rule.detector_id,
                rule.output_field,
                detector_outputs,
                criterion.id
            )
            all_scores.extend(scores)
        
        return max(all_scores) if all_scores else 0.0


class AverageStrategy(BaseFusionStrategy):
    """
    Average fusion strategy.
    
    Computes simple average of all detector scores.
    """
    
    strategy_type = FusionStrategyEnum.AVERAGE.value
    
    def compute_criterion_score(
        self,
        criterion: CriterionSpec,
        routing_rules: List[RoutingRule],
        detector_outputs: Dict[str, DetectorResult]
    ) -> float:
        all_scores = []
        
        for rule in routing_rules:
            scores = self._extract_scores_from_detector(
                rule.detector_id,
                rule.output_field,
                detector_outputs,
                criterion.id
            )
            all_scores.extend(scores)
        
        if not all_scores:
            return 0.0
        
        return sum(all_scores) / len(all_scores)


class RuleBasedStrategy(BaseFusionStrategy):
    """
    Rule-based fusion strategy.
    
    Applies custom rules defined in the fusion spec.
    """
    
    strategy_type = FusionStrategyEnum.RULE_BASED.value
    
    def compute_criterion_score(
        self,
        criterion: CriterionSpec,
        routing_rules: List[RoutingRule],
        detector_outputs: Dict[str, DetectorResult]
    ) -> float:
        # Get rules for this criterion
        rules = [r for r in self.spec.rules if r.get("criterion_id") == criterion.id]
        
        if not rules:
            # Fall back to weighted sum
            return WeightedSumStrategy(self.spec).compute_criterion_score(
                criterion, routing_rules, detector_outputs
            )
        
        # Collect all scores first
        detector_scores: Dict[str, float] = {}
        for rule in routing_rules:
            scores = self._extract_scores_from_detector(
                rule.detector_id,
                rule.output_field,
                detector_outputs,
                criterion.id
            )
            if scores:
                detector_scores[rule.detector_id] = max(scores)
        
        # Apply rules
        final_score = 0.0
        for rule in rules:
            rule_type = rule.get("type", "threshold")
            
            if rule_type == "threshold":
                # If detector score >= threshold, apply boost
                detector_id = rule.get("detector_id")
                threshold = rule.get("threshold", 0.5)
                boost = rule.get("boost", 0.3)
                
                if detector_id in detector_scores:
                    if detector_scores[detector_id] >= threshold:
                        final_score += boost
            
            elif rule_type == "multiply":
                # Multiply detector scores
                detector_ids = rule.get("detector_ids", [])
                scores = [detector_scores.get(d, 0) for d in detector_ids]
                if all(s > 0 for s in scores):
                    import math
                    final_score = max(final_score, math.prod(scores) ** (1/len(scores)))
            
            elif rule_type == "any":
                # Any detector above threshold
                threshold = rule.get("threshold", 0.5)
                if any(s >= threshold for s in detector_scores.values()):
                    final_score = max(final_score, max(detector_scores.values()))
        
        return min(final_score, 1.0)
