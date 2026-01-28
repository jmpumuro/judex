"""
Auto-routing from user criteria to internal detectors.

This is the internal logic that maps user-facing criteria
to the appropriate detectors. Users don't see or configure this.

The routing is based on semantic matching of criterion names/descriptions
to detector capabilities. All configuration is externalized.
"""
from typing import List, Set

from app.evaluation.criteria import EvaluationCriteria, Criterion
from app.evaluation.routing_config import (
    get_routing_config,
    DetectorCapability,
    DetectorConfig
)
from app.core.logging import get_logger

logger = get_logger("evaluation.routing")


def _extract_keywords(criterion_id: str, criterion: Criterion) -> Set[str]:
    """Extract keywords from criterion for capability matching."""
    config = get_routing_config()
    keywords = set()
    
    # Add criterion ID (e.g., "violence", "profanity")
    keywords.add(criterion_id.lower())
    
    # Add words from label
    if criterion.label:
        keywords.update(word.lower() for word in criterion.label.split())
    
    # Add words from description (only words longer than min_keyword_length)
    if criterion.description:
        keywords.update(
            word.lower() 
            for word in criterion.description.split() 
            if len(word) > config.min_keyword_length
        )
    
    return keywords


def _get_required_capabilities(keywords: Set[str]) -> Set[DetectorCapability]:
    """Determine required capabilities from keywords."""
    config = get_routing_config()
    capabilities = set()
    
    for keyword in keywords:
        for criterion_key, caps in config.keyword_to_capabilities.items():
            if criterion_key in keyword or keyword in criterion_key:
                capabilities.update(caps)
    
    return capabilities


def route_criteria_to_detectors(criteria: EvaluationCriteria) -> List[str]:
    """
    Automatically determine which detectors to run based on criteria.
    
    This is the core routing logic that maps user criteria to detectors.
    Users never see this - they just define what they want to evaluate.
    
    Returns:
        List of detector IDs to run, in priority order
    """
    config = get_routing_config()
    required_capabilities: Set[DetectorCapability] = set()
    
    # Analyze each enabled criterion
    for crit_id, criterion in criteria.get_enabled_criteria().items():
        keywords = _extract_keywords(crit_id, criterion)
        caps = _get_required_capabilities(keywords)
        required_capabilities.update(caps)
        
        logger.debug(f"Criterion '{crit_id}' maps to capabilities: {caps}")
    
    # If no capabilities matched, use defaults
    if not required_capabilities:
        logger.warning("No capabilities matched criteria, using default detector set")
        return list(config.default_detector_ids)
    
    # Select detectors that provide required capabilities
    selected_detectors: List[DetectorConfig] = []
    
    # Sort by priority (lower = earlier)
    sorted_detectors = sorted(config.detectors.values(), key=lambda d: d.priority)
    
    for detector in sorted_detectors:
        # Check if this detector provides any needed capability
        provides = set(detector.capabilities) & required_capabilities
        
        if provides:
            selected_detectors.append(detector)
            logger.debug(f"Selected detector '{detector.id}' for capabilities: {provides}")
    
    # Always include text_moderation if we have audio or text extraction
    _ensure_text_moderation(selected_detectors, config)
    
    detector_ids = [d.id for d in sorted(selected_detectors, key=lambda d: d.priority)]
    logger.info(f"Routed {len(criteria.get_enabled_criteria())} criteria to {len(detector_ids)} detectors: {detector_ids}")
    
    return detector_ids


def _ensure_text_moderation(
    selected_detectors: List[DetectorConfig], 
    config
) -> None:
    """Ensure text_moderation is included when needed."""
    has_text_source = any(
        DetectorCapability.AUDIO_SPEECH in d.capabilities or 
        DetectorCapability.VISUAL_TEXT in d.capabilities 
        for d in selected_detectors
    )
    
    if has_text_source:
        text_mod = config.detectors.get("text_moderation")
        if text_mod and text_mod not in selected_detectors:
            selected_detectors.append(text_mod)


def get_detector_for_criterion(criterion_id: str) -> List[str]:
    """
    Get primary detectors that contribute to a specific criterion score.
    
    Used for explaining which detectors contributed to a criterion's score.
    """
    config = get_routing_config()
    keywords = {criterion_id.lower()}
    caps = _get_required_capabilities(keywords)
    
    detectors = []
    for detector_id, detector_config in config.detectors.items():
        if set(detector_config.capabilities) & caps:
            detectors.append(detector_id)
    
    return detectors
