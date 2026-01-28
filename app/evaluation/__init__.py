"""
Evaluation framework for generic video analysis.

This module provides a flexible, user-defined evaluation system where users can:
- Define custom criteria with thresholds and severity weights
- Select and configure detectors
- Specify fusion strategies for combining evidence
- Control outputs (labeled video, raw evidence, reports)
"""
from app.evaluation.spec import (
    EvaluationSpec,
    CriterionSpec,
    DetectorSpec,
    FusionSpec,
    OutputSpec,
    RoutingSpec,
    VerdictLevel,
    SCHEMA_VERSION
)
from app.evaluation.evidence import EvidenceItem, EvidenceCollection

__all__ = [
    "EvaluationSpec",
    "CriterionSpec", 
    "DetectorSpec",
    "FusionSpec",
    "OutputSpec",
    "RoutingSpec",
    "VerdictLevel",
    "EvidenceItem",
    "EvidenceCollection",
    "SCHEMA_VERSION"
]
