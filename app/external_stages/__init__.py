"""
External stage definitions - YAML-defined stages that call external HTTP endpoints.

This module provides:
- YAML schema validation for stage definitions
- External stage plugin that executes HTTP callbacks
- Registry for managing external stage configurations
"""
from app.external_stages.schema import (
    ExternalStageConfig,
    StageEndpoint,
    StageMapping,
    parse_stage_yaml,
    validate_stage_config,
)
from app.external_stages.plugin import ExternalHttpStagePlugin
from app.external_stages.registry import (
    ExternalStageRegistry,
    get_external_stage_registry,
)

__all__ = [
    "ExternalStageConfig",
    "StageEndpoint",
    "StageMapping",
    "parse_stage_yaml",
    "validate_stage_config",
    "ExternalHttpStagePlugin",
    "ExternalStageRegistry",
    "get_external_stage_registry",
]
