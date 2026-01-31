"""
Fusion strategies for combining detector outputs into criterion scores and verdicts.

The fusion module provides:
- Per-criterion score computation from detector evidence
- Final verdict determination from criterion scores
- Explanation generation for audit trails
- Research-backed multi-modal fusion (Dempster-Shafer, reliability weighting)
"""
from app.fusion.registry import (
    FusionRegistry,
    get_fusion_strategy,
    register_fusion_strategy,
    list_fusion_strategies
)
from app.fusion.strategies import (
    BaseFusionStrategy,
    WeightedSumStrategy,
    MaxStrategy,
    AverageStrategy,
    RuleBasedStrategy
)
from app.fusion.engine import FusionEngine, FusionResult

# Research-backed fusion (recommended)
from app.fusion.research_fusion import (
    ResearchBackedFusion,
    compute_all_scores_research_backed,
    fuse_violence_signals,
    fuse_sexual_signals,
    fuse_profanity_signals,
    fuse_drugs_signals,
    fuse_hate_signals,
    Signal,
    SignalSource,
    SignalReliability,
    FusionResult as ResearchFusionResult,
)

# Violence validation (false positive reduction)
from app.fusion.violence_validation import (
    ViolenceValidator,
    ValidationResult,
    SceneContext,
    validate_violence_score,
)

__all__ = [
    "FusionRegistry",
    "get_fusion_strategy",
    "register_fusion_strategy",
    "list_fusion_strategies",
    "BaseFusionStrategy",
    "WeightedSumStrategy",
    "MaxStrategy",
    "AverageStrategy",
    "RuleBasedStrategy",
    "FusionEngine",
    "FusionResult",
    # Research-backed fusion
    "ResearchBackedFusion",
    "compute_all_scores_research_backed",
    "fuse_violence_signals",
    "fuse_sexual_signals",
    "fuse_profanity_signals",
    "fuse_drugs_signals",
    "fuse_hate_signals",
    "Signal",
    "SignalSource",
    "SignalReliability",
    "ResearchFusionResult",
    # Violence validation
    "ViolenceValidator",
    "ValidationResult",
    "SceneContext",
    "validate_violence_score",
]
