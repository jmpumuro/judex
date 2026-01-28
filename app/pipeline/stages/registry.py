"""
Stage registry for discovering and resolving stage plugins.

The registry maintains a mapping of stage types to plugin implementations.
Builtin stages are registered on import; custom stages can be registered
at runtime.
"""
from typing import Dict, List, Optional, Type
from app.pipeline.stages.base import StagePlugin
from app.core.logging import get_logger

logger = get_logger("stages.registry")


class StageRegistry:
    """
    Registry for stage plugins.
    
    Provides:
    - Registration of stage plugins by type
    - Resolution of plugins by type
    - Listing of available stages
    """
    
    _instance: Optional["StageRegistry"] = None
    
    def __init__(self):
        self._stages: Dict[str, Type[StagePlugin]] = {}
        self._instances: Dict[str, StagePlugin] = {}
    
    @classmethod
    def get_instance(cls) -> "StageRegistry":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._register_builtins()
        return cls._instance
    
    def register(
        self, 
        stage_type: str, 
        plugin_class: Type[StagePlugin],
        override: bool = False
    ) -> None:
        """
        Register a stage plugin.
        
        Args:
            stage_type: Registry key for this stage
            plugin_class: StagePlugin subclass
            override: If True, allow overwriting existing registration
        """
        if stage_type in self._stages and not override:
            raise ValueError(
                f"Stage type '{stage_type}' already registered. "
                f"Use override=True to replace."
            )
        
        self._stages[stage_type] = plugin_class
        logger.debug(f"Registered stage plugin: {stage_type}")
    
    def get(self, stage_type: str) -> StagePlugin:
        """
        Get a stage plugin instance by type.
        
        Args:
            stage_type: Registry key
            
        Returns:
            StagePlugin instance (cached)
            
        Raises:
            KeyError: If stage type not registered
        """
        if stage_type not in self._stages:
            available = ", ".join(sorted(self._stages.keys()))
            raise KeyError(
                f"Unknown stage type: '{stage_type}'. "
                f"Available stages: {available}"
            )
        
        # Lazy instantiation with caching
        if stage_type not in self._instances:
            self._instances[stage_type] = self._stages[stage_type]()
        
        return self._instances[stage_type]
    
    def has(self, stage_type: str) -> bool:
        """Check if a stage type is registered."""
        return stage_type in self._stages
    
    def list_stages(self) -> List[str]:
        """List all registered stage types."""
        return sorted(self._stages.keys())
    
    def get_stage_info(self, stage_type: str) -> Dict:
        """Get metadata about a stage."""
        plugin = self.get(stage_type)
        return {
            "type": stage_type,
            "display_name": plugin.display_name,
            "input_keys": list(plugin.input_keys),
            "output_keys": list(plugin.output_keys),
        }
    
    def list_stage_info(self) -> List[Dict]:
        """Get metadata for all registered stages."""
        return [self.get_stage_info(t) for t in self.list_stages()]
    
    def _register_builtins(self) -> None:
        """Register all builtin stage plugins."""
        # Import here to avoid circular imports
        from app.pipeline.stages.builtins import (
            Yolo26StagePlugin,
            YoloWorldStagePlugin,
            ViolenceStagePlugin,
            WhisperStagePlugin,
            OcrStagePlugin,
            TextModerationStagePlugin,
        )
        
        builtin_stages = [
            Yolo26StagePlugin,
            YoloWorldStagePlugin,
            ViolenceStagePlugin,
            WhisperStagePlugin,
            OcrStagePlugin,
            TextModerationStagePlugin,
        ]
        
        for plugin_class in builtin_stages:
            # Create instance to get stage_type
            instance = plugin_class()
            self.register(instance.stage_type, plugin_class)
        
        logger.info(f"Registered {len(builtin_stages)} builtin stage plugins")


def get_stage_registry() -> StageRegistry:
    """Get the global stage registry instance."""
    return StageRegistry.get_instance()
