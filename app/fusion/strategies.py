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


class ReliabilityWeightedStrategy(BaseFusionStrategy):
    """
    Reliability-weighted fusion strategy.
    
    Each detector has a reliability weight (0-1) that reflects its historical
    accuracy and domain suitability. Scores are combined using these weights,
    with calibrated thresholds applied.
    
    Industry Standard:
    - Deterministic (no ML training required)
    - Configurable reliability weights per detector
    - Calibration profiles (conservative/balanced/aggressive)
    - Missing signal handling (graceful degradation)
    - Debug output for explainability
    """
    
    strategy_type = "reliability_weighted"
    
    # Default reliability weights for detectors
    # Higher = more reliable for violence detection
    DEFAULT_RELIABILITY_WEIGHTS: Dict[str, float] = {
        # Violence specialists
        "xclip": 0.85,          # Strong video violence classifier
        "videomae_violence": 0.80,  # Action recognition based
        "pose_heuristics": 0.70,    # Deterministic but limited
        
        # Supporting signals
        "yolo26": 0.60,         # Object detection, indirect signal
        "yoloworld": 0.55,      # Open-vocab detection
        "window_mining": 0.50,  # Preprocessing, not direct detection
        
        # Text/audio signals
        "whisper": 0.65,        # Transcription for text moderation
        "ocr": 0.55,            # OCR for text moderation
        "text_moderation": 0.75,  # Good for profanity/hate
    }
    
    # Calibration profiles
    CALIBRATION_PROFILES: Dict[str, Dict[str, float]] = {
        "conservative": {
            "score_multiplier": 0.8,
            "threshold_boost": 0.1,
            "min_sources": 2,
        },
        "balanced": {
            "score_multiplier": 1.0,
            "threshold_boost": 0.0,
            "min_sources": 1,
        },
        "aggressive": {
            "score_multiplier": 1.2,
            "threshold_boost": -0.1,
            "min_sources": 1,
        },
    }
    
    def compute_criterion_score(
        self,
        criterion: CriterionSpec,
        routing_rules: List[RoutingRule],
        detector_outputs: Dict[str, DetectorResult]
    ) -> float:
        """
        Compute criterion score using reliability-weighted fusion.
        """
        if not routing_rules:
            return 0.0
        
        # Get calibration profile from spec
        calibration = self.spec.custom_config.get("calibration", "balanced") if hasattr(self.spec, "custom_config") else "balanced"
        profile = self.CALIBRATION_PROFILES.get(calibration, self.CALIBRATION_PROFILES["balanced"])
        
        # Get custom reliability weights if provided
        custom_weights = {}
        if hasattr(self.spec, "custom_config") and self.spec.custom_config:
            custom_weights = self.spec.custom_config.get("reliability_weights", {})
        
        # Collect scores with reliability weights
        weighted_scores = []
        total_reliability = 0.0
        sources_with_signal = 0
        
        for rule in routing_rules:
            detector_id = rule.detector_id
            
            # Get reliability weight
            reliability = custom_weights.get(
                detector_id, 
                self.DEFAULT_RELIABILITY_WEIGHTS.get(detector_id, 0.5)
            )
            
            # Extract scores from detector
            scores = self._extract_scores_from_detector(
                detector_id,
                rule.output_field,
                detector_outputs,
                criterion.id
            )
            
            if scores:
                max_score = max(scores)
                # Apply rule weight as additional factor
                combined_weight = reliability * rule.weight
                
                weighted_scores.append({
                    "detector": detector_id,
                    "score": max_score,
                    "reliability": reliability,
                    "rule_weight": rule.weight,
                    "combined_weight": combined_weight,
                    "contribution": max_score * combined_weight,
                })
                
                total_reliability += combined_weight
                sources_with_signal += 1
        
        # Handle missing signals
        if sources_with_signal < profile["min_sources"]:
            # Not enough sources, return low score with uncertainty
            if weighted_scores:
                # Use available data but with penalty
                base_score = sum(ws["contribution"] for ws in weighted_scores) / max(total_reliability, 0.001)
                return max(0.0, min(base_score * 0.5, 0.3))  # Cap at 0.3 for uncertain
            return 0.0
        
        # Compute weighted average
        if total_reliability == 0:
            return 0.0
        
        raw_score = sum(ws["contribution"] for ws in weighted_scores) / total_reliability
        
        # Apply calibration
        calibrated_score = raw_score * profile["score_multiplier"]
        
        return max(0.0, min(calibrated_score, 1.0))
    
    def get_fusion_debug(
        self,
        criterion: CriterionSpec,
        routing_rules: List[RoutingRule],
        detector_outputs: Dict[str, DetectorResult]
    ) -> Dict[str, Any]:
        """
        Get debug information about the fusion process.
        
        Returns detailed breakdown of how the score was computed.
        """
        calibration = self.spec.custom_config.get("calibration", "balanced") if hasattr(self.spec, "custom_config") else "balanced"
        profile = self.CALIBRATION_PROFILES.get(calibration, self.CALIBRATION_PROFILES["balanced"])
        
        custom_weights = {}
        if hasattr(self.spec, "custom_config") and self.spec.custom_config:
            custom_weights = self.spec.custom_config.get("reliability_weights", {})
        
        debug = {
            "criterion_id": criterion.id,
            "calibration_profile": calibration,
            "profile_settings": profile,
            "detector_contributions": [],
            "missing_detectors": [],
            "total_reliability": 0.0,
            "sources_with_signal": 0,
        }
        
        expected_detectors = {rule.detector_id for rule in routing_rules}
        found_detectors = set()
        
        for rule in routing_rules:
            detector_id = rule.detector_id
            reliability = custom_weights.get(
                detector_id,
                self.DEFAULT_RELIABILITY_WEIGHTS.get(detector_id, 0.5)
            )
            
            scores = self._extract_scores_from_detector(
                detector_id,
                rule.output_field,
                detector_outputs,
                criterion.id
            )
            
            if scores:
                found_detectors.add(detector_id)
                max_score = max(scores)
                combined_weight = reliability * rule.weight
                
                debug["detector_contributions"].append({
                    "detector": detector_id,
                    "score": round(max_score, 3),
                    "reliability": reliability,
                    "rule_weight": rule.weight,
                    "contribution": round(max_score * combined_weight, 3),
                })
                
                debug["total_reliability"] += combined_weight
                debug["sources_with_signal"] += 1
        
        # Track missing detectors
        debug["missing_detectors"] = list(expected_detectors - found_detectors)
        
        return debug
