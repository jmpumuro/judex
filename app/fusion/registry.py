"""
Fusion strategy registry.

Maps FusionStrategy enum values to strategy implementations.
"""
from typing import Dict, Type, List
from app.evaluation.spec import FusionSpec, FusionStrategy as FusionStrategyEnum
from app.fusion.strategies import (
    BaseFusionStrategy,
    WeightedSumStrategy,
    MaxStrategy,
    AverageStrategy,
    RuleBasedStrategy,
    ReliabilityWeightedStrategy,
)


class FusionNotFoundError(Exception):
    """Raised when a fusion strategy is not registered."""
    pass


class FusionRegistry:
    """
    Registry for fusion strategy implementations.
    """
    
    _strategies: Dict[str, Type[BaseFusionStrategy]] = {}
    
    @classmethod
    def register(
        cls,
        strategy_type: str,
        strategy_class: Type[BaseFusionStrategy]
    ) -> None:
        """Register a fusion strategy implementation."""
        cls._strategies[strategy_type] = strategy_class
    
    @classmethod
    def get(cls, spec: FusionSpec) -> BaseFusionStrategy:
        """
        Get a fusion strategy instance for the given spec.
        
        Args:
            spec: FusionSpec with strategy configuration
            
        Returns:
            Configured BaseFusionStrategy instance
        """
        strategy_type = spec.criterion_strategy.value
        
        if strategy_type not in cls._strategies:
            available = list(cls._strategies.keys())
            raise FusionNotFoundError(
                f"Fusion strategy '{strategy_type}' not registered. "
                f"Available: {available}"
            )
        
        strategy_class = cls._strategies[strategy_type]
        return strategy_class(spec)
    
    @classmethod
    def list_types(cls) -> List[str]:
        """List registered strategy types."""
        return list(cls._strategies.keys())


# ===== CONVENIENCE FUNCTIONS =====

def get_fusion_strategy(spec: FusionSpec) -> BaseFusionStrategy:
    """Get a fusion strategy instance for the given spec."""
    return FusionRegistry.get(spec)


def register_fusion_strategy(
    strategy_type: str,
    strategy_class: Type[BaseFusionStrategy]
) -> None:
    """Register a fusion strategy implementation."""
    FusionRegistry.register(strategy_type, strategy_class)


def list_fusion_strategies() -> List[str]:
    """List registered strategy types."""
    return FusionRegistry.list_types()


# ===== REGISTER BUILT-IN STRATEGIES =====

FusionRegistry.register(FusionStrategyEnum.WEIGHTED_SUM.value, WeightedSumStrategy)
FusionRegistry.register(FusionStrategyEnum.MAX.value, MaxStrategy)
FusionRegistry.register(FusionStrategyEnum.AVERAGE.value, AverageStrategy)
FusionRegistry.register(FusionStrategyEnum.RULE_BASED.value, RuleBasedStrategy)
FusionRegistry.register("reliability_weighted", ReliabilityWeightedStrategy)