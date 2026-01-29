"""
Registry for external stage configurations.

Manages YAML-defined external stages:
- Storage in database
- Dynamic registration with stage registry
- Hot-reloading of stage definitions
"""
from typing import Dict, List, Optional
from app.external_stages.schema import (
    ExternalStageConfig,
    ExternalStagesDefinition,
    parse_stage_yaml,
    ValidationError,
)
from app.external_stages.plugin import ExternalHttpStagePlugin
from app.core.logging import get_logger

logger = get_logger("external_stages.registry")


class ExternalStageRegistry:
    """
    Registry for external stage configurations.
    
    Provides:
    - CRUD operations for stage configs
    - Integration with main stage registry
    - Validation and hot-reload
    """
    
    _instance: Optional["ExternalStageRegistry"] = None
    
    def __init__(self):
        self._configs: Dict[str, ExternalStageConfig] = {}
        self._yaml_sources: Dict[str, str] = {}  # config_id -> yaml content
    
    @classmethod
    def get_instance(cls) -> "ExternalStageRegistry":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def register_from_yaml(self, yaml_content: str, config_id: str = "default") -> List[str]:
        """
        Parse YAML and register all stages.
        
        Args:
            yaml_content: YAML string with stage definitions
            config_id: Identifier for this YAML config (for updates/deletes)
            
        Returns:
            List of registered stage IDs
            
        Raises:
            ValidationError: If YAML is invalid
        """
        definition = parse_stage_yaml(yaml_content)
        
        registered = []
        for stage_config in definition.stages:
            self._configs[stage_config.id] = stage_config
            registered.append(stage_config.id)
            logger.info(f"Registered external stage: {stage_config.id}")
        
        # Store YAML source for later retrieval
        self._yaml_sources[config_id] = yaml_content
        
        # Register with main stage registry
        self._sync_to_stage_registry()
        
        return registered
    
    def unregister(self, stage_id: str) -> bool:
        """
        Unregister a stage by ID.
        
        Returns:
            True if stage was removed, False if not found
        """
        if stage_id not in self._configs:
            return False
        
        del self._configs[stage_id]
        logger.info(f"Unregistered external stage: {stage_id}")
        
        # Sync with main registry
        self._sync_to_stage_registry()
        
        return True
    
    def get(self, stage_id: str) -> Optional[ExternalStageConfig]:
        """Get a stage configuration by ID."""
        return self._configs.get(stage_id)
    
    def get_config(self, stage_id: str) -> Optional["DBExternalStageConfig"]:
        """
        Get database config for a stage ID.
        
        This retrieves the DB model with the YAML content, used by
        the stage registry to create plugin instances.
        """
        try:
            from app.db.connection import get_db_session
            from app.db.models import ExternalStageConfig as ExternalStageModel
            
            with get_db_session() as session:
                # Check by stage_ids array or by config id
                configs = session.query(ExternalStageModel).filter(
                    ExternalStageModel.enabled == True
                ).all()
                
                for config in configs:
                    if config.stage_ids and stage_id in config.stage_ids:
                        return config
                    if config.id == stage_id:
                        return config
            return None
        except Exception as e:
            logger.warning(f"Failed to get DB config for {stage_id}: {e}")
            return None
    
    def has_config(self, stage_id: str) -> bool:
        """Check if a stage config exists by ID (either in memory or DB)."""
        if stage_id in self._configs:
            return True
        return self.get_config(stage_id) is not None
    
    def list_stages(self) -> List[ExternalStageConfig]:
        """List all registered external stages."""
        return list(self._configs.values())
    
    def get_stage_info(self) -> List[Dict]:
        """Get metadata for all external stages (for UI)."""
        return [
            {
                "type": config.id,
                "display_name": config.name,
                "description": config.description,
                "is_external": True,
                "enabled": config.enabled,
                "endpoint_url": config.endpoint.url,
                "display_color": config.display_color,
                "icon": config.icon,
                "input_keys": list(config.mapping.input_mapping.keys()),
                "output_keys": list(config.mapping.output_mapping.keys()),
            }
            for config in self._configs.values()
        ]
    
    def get_yaml(self, config_id: str = "default") -> Optional[str]:
        """Get the original YAML source for a config."""
        return self._yaml_sources.get(config_id)
    
    def create_plugin(self, stage_id: str) -> Optional[ExternalHttpStagePlugin]:
        """Create a plugin instance for a stage."""
        config = self.get(stage_id)
        if not config:
            return None
        return ExternalHttpStagePlugin(config)
    
    def _sync_to_stage_registry(self) -> None:
        """
        Sync external stages to the main stage registry.
        
        This allows external stages to be discovered and executed
        by the PipelineRunner just like builtin stages.
        """
        from app.pipeline.stages.registry import get_stage_registry
        
        registry = get_stage_registry()
        
        for config in self._configs.values():
            # Create a plugin class factory for this config
            # This is needed because the registry stores classes, not instances
            plugin = ExternalHttpStagePlugin(config)
            
            # Register or update
            try:
                registry.register(
                    stage_type=config.id,
                    plugin_class=type(
                        f"ExternalStage_{config.id}",
                        (ExternalHttpStagePlugin,),
                        {"_config_instance": config}
                    ),
                    override=True
                )
                
                # Also store the actual instance for direct access
                registry._instances[config.id] = plugin
                
            except Exception as e:
                logger.error(f"Failed to register external stage {config.id}: {e}")
    
    def clear(self) -> None:
        """Clear all registered stages."""
        self._configs.clear()
        self._yaml_sources.clear()
        logger.info("Cleared all external stages")


def get_external_stage_registry() -> ExternalStageRegistry:
    """Get the global external stage registry instance."""
    return ExternalStageRegistry.get_instance()


def load_external_stages_from_db() -> None:
    """
    Load external stages from database on startup.
    
    Called from main.py during initialization.
    """
    try:
        from app.db.connection import get_db_session
        from app.db.models import ExternalStageConfig as ExternalStageModel
        
        registry = get_external_stage_registry()
        
        with get_db_session() as session:
            configs = session.query(ExternalStageModel).filter(
                ExternalStageModel.enabled == True
            ).all()
            
            for config in configs:
                try:
                    registry.register_from_yaml(config.yaml_content, config.id)
                    logger.info(f"Loaded external stage config: {config.id}")
                except ValidationError as e:
                    logger.warning(f"Invalid stage config {config.id}: {e}")
                except Exception as e:
                    logger.error(f"Failed to load stage config {config.id}: {e}")
        
        logger.info(f"Loaded {len(registry.list_stages())} external stages from database")
        
    except Exception as e:
        logger.warning(f"Could not load external stages from database: {e}")
