"""
Fusion strategies for combining detector outputs into criterion scores and verdicts.

The fusion module provides:
- Per-criterion score computation from detector evidence
- Final verdict determination from criterion scores
- Explanation generation for audit trails
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
    "FusionResult"
]
