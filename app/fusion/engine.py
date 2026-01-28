"""
Fusion engine - orchestrates scoring and verdict determination.

The FusionEngine:
1. Computes per-criterion scores using the configured strategy
2. Determines per-criterion verdicts based on thresholds
3. Aggregates criterion verdicts into final verdict
4. Extracts violations and generates explanations
"""
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from app.evaluation.spec import (
    EvaluationSpec,
    CriterionSpec,
    VerdictLevel,
    AggregationRule
)
from app.evaluation.evidence import EvidenceCollection, EvidenceItem
from app.detectors.base import DetectorResult
from app.fusion.registry import get_fusion_strategy
from app.core.logging import get_logger

logger = get_logger("fusion.engine")


@dataclass
class CriterionResult:
    """Result for a single criterion."""
    criterion_id: str
    score: float
    verdict: str
    threshold_crossed: Optional[str] = None
    evidence_count: int = 0
    evidence_refs: List[str] = field(default_factory=list)
    detector_sources: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "verdict": self.verdict,
            "threshold_crossed": self.threshold_crossed,
            "evidence_count": self.evidence_count,
            "evidence_refs": self.evidence_refs[:10],  # Limit refs in response
            "detector_sources": self.detector_sources
        }


@dataclass
class Violation:
    """A detected violation."""
    criterion_id: str
    severity: str
    score: float
    timestamp_ranges: List[List[float]] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "criterion": self.criterion_id,
            "severity": self.severity,
            "score": round(self.score, 3),
            "timestamp_ranges": self.timestamp_ranges[:20],
            "evidence_refs": self.evidence_refs[:10]
        }


@dataclass
class FusionResult:
    """Complete result from fusion engine."""
    # Final verdict
    verdict: str
    confidence: float
    
    # Per-criterion results
    criteria_results: Dict[str, CriterionResult] = field(default_factory=dict)
    
    # Violations
    violations: List[Violation] = field(default_factory=list)
    
    # Explanation
    explanation: Dict[str, Any] = field(default_factory=dict)
    
    # Evidence summary
    total_evidence_items: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "confidence": round(self.confidence, 3),
            "criteria": {
                cid: result.to_dict()
                for cid, result in self.criteria_results.items()
            },
            "violations": [v.to_dict() for v in self.violations],
            "explanation": self.explanation,
            "total_evidence_items": self.total_evidence_items
        }


class FusionEngine:
    """
    Engine for fusing detector outputs into scores and verdicts.
    """
    
    def __init__(self, spec: EvaluationSpec):
        self.spec = spec
        self.strategy = get_fusion_strategy(spec.fusion)
    
    def fuse(
        self,
        detector_outputs: Dict[str, DetectorResult],
        all_evidence: Optional[EvidenceCollection] = None
    ) -> FusionResult:
        """
        Fuse detector outputs into criterion scores and final verdict.
        
        Args:
            detector_outputs: Dict of detector_id -> DetectorResult
            all_evidence: Combined evidence collection (optional)
            
        Returns:
            FusionResult with scores, verdict, and violations
        """
        # Compute per-criterion scores and verdicts
        criteria_results = {}
        
        for criterion in self.spec.get_enabled_criteria():
            routing_rules = self.spec.get_routing_for_criterion(criterion.id)
            
            # Compute score using strategy
            score = self.strategy.compute_criterion_score(
                criterion,
                routing_rules,
                detector_outputs
            )
            
            # Determine verdict for this criterion
            verdict, threshold_crossed = self._criterion_verdict(criterion, score)
            
            # Find relevant evidence
            evidence_refs = self._find_evidence_refs(
                criterion.id,
                detector_outputs,
                all_evidence
            )
            
            # Track detector sources
            detector_sources = [r.detector_id for r in routing_rules if r.detector_id in detector_outputs]
            
            criteria_results[criterion.id] = CriterionResult(
                criterion_id=criterion.id,
                score=score,
                verdict=verdict,
                threshold_crossed=threshold_crossed,
                evidence_count=len(evidence_refs),
                evidence_refs=evidence_refs,
                detector_sources=detector_sources
            )
        
        # Determine final verdict
        final_verdict, confidence = self._aggregate_verdict(criteria_results)
        
        # Apply multi-signal confirmation if configured
        if self.spec.fusion.require_confirmation:
            final_verdict, confidence = self._apply_confirmation(
                final_verdict,
                confidence,
                criteria_results,
                detector_outputs
            )
        
        # Extract violations
        violations = self._extract_violations(
            criteria_results,
            detector_outputs,
            all_evidence
        )
        
        # Generate explanation
        explanation = self._generate_explanation(
            final_verdict,
            criteria_results,
            violations
        )
        
        # Count total evidence
        total_evidence = sum(
            len(result.evidence) for result in detector_outputs.values()
        )
        
        return FusionResult(
            verdict=final_verdict,
            confidence=confidence,
            criteria_results=criteria_results,
            violations=violations,
            explanation=explanation,
            total_evidence_items=total_evidence
        )
    
    def _criterion_verdict(
        self,
        criterion: CriterionSpec,
        score: float
    ) -> Tuple[str, Optional[str]]:
        """
        Determine verdict for a single criterion based on thresholds.
        
        Returns:
            (verdict, threshold_crossed or None)
        """
        thresholds = criterion.thresholds
        
        if score >= thresholds.unsafe_above:
            return VerdictLevel.UNSAFE.value, "unsafe_above"
        elif score >= thresholds.caution_below:
            return VerdictLevel.CAUTION.value, "caution_below"
        elif score < thresholds.safe_below:
            return VerdictLevel.SAFE.value, None
        else:
            return VerdictLevel.CAUTION.value, None
    
    def _aggregate_verdict(
        self,
        criteria_results: Dict[str, CriterionResult]
    ) -> Tuple[str, float]:
        """
        Aggregate criterion verdicts into final verdict.
        
        Returns:
            (verdict, confidence)
        """
        aggregation = self.spec.fusion.verdict_aggregation
        
        verdicts = [r.verdict for r in criteria_results.values()]
        scores = [r.score for r in criteria_results.values()]
        
        if not verdicts:
            return VerdictLevel.SAFE.value, 1.0
        
        if aggregation == AggregationRule.ANY_UNSAFE:
            # Any UNSAFE criterion -> UNSAFE
            if VerdictLevel.UNSAFE.value in verdicts:
                confidence = max(
                    r.score for r in criteria_results.values()
                    if r.verdict == VerdictLevel.UNSAFE.value
                )
                return VerdictLevel.UNSAFE.value, confidence
            
            if VerdictLevel.CAUTION.value in verdicts:
                confidence = max(
                    r.score for r in criteria_results.values()
                    if r.verdict == VerdictLevel.CAUTION.value
                )
                return VerdictLevel.CAUTION.value, confidence
            
            return VerdictLevel.SAFE.value, 1.0 - max(scores)
        
        elif aggregation == AggregationRule.MAJORITY:
            # Majority vote
            from collections import Counter
            counts = Counter(verdicts)
            majority = counts.most_common(1)[0][0]
            confidence = counts[majority] / len(verdicts)
            return majority, confidence
        
        elif aggregation == AggregationRule.WEIGHTED:
            # Weighted by criterion severity
            weighted_scores = {}
            total_weight = 0
            
            for cid, result in criteria_results.items():
                criterion = next(
                    (c for c in self.spec.criteria if c.id == cid),
                    None
                )
                weight = criterion.severity_weight if criterion else 1.0
                
                # Convert verdict to numeric
                verdict_value = {
                    VerdictLevel.SAFE.value: 0,
                    VerdictLevel.CAUTION.value: 0.5,
                    VerdictLevel.UNSAFE.value: 1.0,
                    VerdictLevel.NEEDS_REVIEW.value: 0.7
                }.get(result.verdict, 0.5)
                
                weighted_scores[cid] = verdict_value * weight
                total_weight += weight
            
            avg_score = sum(weighted_scores.values()) / total_weight if total_weight > 0 else 0
            
            if avg_score >= 0.7:
                return VerdictLevel.UNSAFE.value, avg_score
            elif avg_score >= 0.4:
                return VerdictLevel.CAUTION.value, avg_score
            else:
                return VerdictLevel.SAFE.value, 1 - avg_score
        
        elif aggregation == AggregationRule.THRESHOLD:
            # Based on aggregated score
            avg_score = sum(scores) / len(scores)
            
            if avg_score >= 0.7:
                return VerdictLevel.UNSAFE.value, avg_score
            elif avg_score >= 0.4:
                return VerdictLevel.CAUTION.value, avg_score
            else:
                return VerdictLevel.SAFE.value, 1 - avg_score
        
        # Default to ANY_UNSAFE behavior
        return VerdictLevel.SAFE.value, 1.0
    
    def _apply_confirmation(
        self,
        verdict: str,
        confidence: float,
        criteria_results: Dict[str, CriterionResult],
        detector_outputs: Dict[str, DetectorResult]
    ) -> Tuple[str, float]:
        """
        Apply multi-signal confirmation for UNSAFE verdicts.
        
        If configured, requires multiple detector sources to confirm
        before marking as UNSAFE.
        """
        if verdict != VerdictLevel.UNSAFE.value:
            return verdict, confidence
        
        threshold = self.spec.fusion.confirmation_threshold
        
        # Count confirming signals (detectors with significant scores)
        confirming_signals = 0
        for result in criteria_results.values():
            if result.verdict == VerdictLevel.UNSAFE.value:
                confirming_signals += len(result.detector_sources)
        
        # Unique detector sources
        all_sources = set()
        for result in criteria_results.values():
            all_sources.update(result.detector_sources)
        
        if len(all_sources) < threshold:
            # Not enough confirmation, downgrade to NEEDS_REVIEW
            logger.info(
                f"UNSAFE verdict downgraded to NEEDS_REVIEW: "
                f"only {len(all_sources)} sources, need {threshold}"
            )
            return VerdictLevel.NEEDS_REVIEW.value, confidence * 0.8
        
        return verdict, confidence
    
    def _find_evidence_refs(
        self,
        criterion_id: str,
        detector_outputs: Dict[str, DetectorResult],
        all_evidence: Optional[EvidenceCollection]
    ) -> List[str]:
        """Find evidence references for a criterion."""
        refs = []
        
        # Check all evidence
        if all_evidence:
            for item in all_evidence.items:
                if item.criterion_id == criterion_id:
                    refs.append(item.id)
                elif item.category and item.category.lower() == criterion_id.lower():
                    refs.append(item.id)
        
        # Also check detector outputs
        for detector_id, result in detector_outputs.items():
            for item in result.evidence.items:
                if item.category and item.category.lower() == criterion_id.lower():
                    if item.id not in refs:
                        refs.append(item.id)
        
        return refs
    
    def _extract_violations(
        self,
        criteria_results: Dict[str, CriterionResult],
        detector_outputs: Dict[str, DetectorResult],
        all_evidence: Optional[EvidenceCollection]
    ) -> List[Violation]:
        """Extract violations from criteria that exceed thresholds."""
        violations = []
        
        for cid, result in criteria_results.items():
            if result.verdict in [VerdictLevel.UNSAFE.value, VerdictLevel.CAUTION.value]:
                # Find criterion spec for severity
                criterion = next(
                    (c for c in self.spec.criteria if c.id == cid),
                    None
                )
                
                severity = "medium"
                if result.verdict == VerdictLevel.UNSAFE.value:
                    severity = "high"
                elif criterion and criterion.severity_level:
                    severity = criterion.severity_level.value
                
                # Get timestamp ranges from evidence
                timestamp_ranges = self._get_timestamp_ranges(
                    result.evidence_refs,
                    detector_outputs,
                    all_evidence
                )
                
                violations.append(Violation(
                    criterion_id=cid,
                    severity=severity,
                    score=result.score,
                    timestamp_ranges=timestamp_ranges,
                    evidence_refs=result.evidence_refs
                ))
        
        return violations
    
    def _get_timestamp_ranges(
        self,
        evidence_refs: List[str],
        detector_outputs: Dict[str, DetectorResult],
        all_evidence: Optional[EvidenceCollection]
    ) -> List[List[float]]:
        """Get timestamp ranges from evidence references."""
        ranges = []
        
        # Search all evidence
        all_items = []
        if all_evidence:
            all_items.extend(all_evidence.items)
        for result in detector_outputs.values():
            all_items.extend(result.evidence.items)
        
        for item in all_items:
            if item.id in evidence_refs:
                for tr in item.time_ranges:
                    ranges.append([tr.start, tr.end])
                if item.timestamp is not None and not item.time_ranges:
                    ranges.append([item.timestamp, item.timestamp + 1])
        
        return ranges[:20]  # Limit
    
    def _generate_explanation(
        self,
        final_verdict: str,
        criteria_results: Dict[str, CriterionResult],
        violations: List[Violation]
    ) -> Dict[str, Any]:
        """Generate human-readable explanation of the verdict."""
        explanation = {
            "verdict": final_verdict,
            "summary": "",
            "criterion_explanations": {},
            "key_factors": []
        }
        
        # Build summary
        if final_verdict == VerdictLevel.SAFE.value:
            explanation["summary"] = "Content passed all safety criteria."
        elif final_verdict == VerdictLevel.CAUTION.value:
            flagged = [cid for cid, r in criteria_results.items() if r.verdict == VerdictLevel.CAUTION.value]
            explanation["summary"] = f"Content flagged for review on {len(flagged)} criteria: {', '.join(flagged)}"
        elif final_verdict == VerdictLevel.UNSAFE.value:
            unsafe = [cid for cid, r in criteria_results.items() if r.verdict == VerdictLevel.UNSAFE.value]
            explanation["summary"] = f"Content marked unsafe due to {len(unsafe)} criteria: {', '.join(unsafe)}"
        elif final_verdict == VerdictLevel.NEEDS_REVIEW.value:
            explanation["summary"] = "Content requires human review - borderline case or conflicting signals."
        
        # Per-criterion explanations
        for cid, result in criteria_results.items():
            criterion = next((c for c in self.spec.criteria if c.id == cid), None)
            
            explanation["criterion_explanations"][cid] = {
                "score": round(result.score, 3),
                "verdict": result.verdict,
                "threshold": result.threshold_crossed,
                "evidence_count": result.evidence_count,
                "detectors_used": result.detector_sources,
                "description": criterion.description if criterion else None
            }
        
        # Key factors (most significant contributors)
        sorted_results = sorted(
            criteria_results.values(),
            key=lambda r: r.score,
            reverse=True
        )
        
        for result in sorted_results[:3]:
            if result.score > 0.3:
                explanation["key_factors"].append({
                    "criterion": result.criterion_id,
                    "score": round(result.score, 3),
                    "evidence_count": result.evidence_count
                })
        
        return explanation
