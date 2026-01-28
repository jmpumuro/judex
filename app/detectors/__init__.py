"""
Detector registry and implementations.

Detectors are modular components that analyze video/audio/text and produce
standardized EvidenceItem outputs.

Each detector:
- Has a unique type (from DetectorType enum)
- Accepts params from DetectorSpec
- Produces List[EvidenceItem] as output
- Reports timing and model versions
"""
from app.detectors.registry import (
    DetectorRegistry,
    get_detector,
    register_detector,
    list_detectors,
    DetectorNotFoundError
)
from app.detectors.base import BaseDetector, DetectorResult

__all__ = [
    "DetectorRegistry",
    "get_detector",
    "register_detector",
    "list_detectors",
    "DetectorNotFoundError",
    "BaseDetector",
    "DetectorResult"
]
