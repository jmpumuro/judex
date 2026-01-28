"""
Stage plugin system for pluggable pipeline execution.

This package provides a plugin architecture for pipeline stages:
- StagePlugin: Base interface for all stages
- StageRegistry: Registry for discovering and resolving stages
- PipelineRunner: Executes a sequence of stages dynamically

Builtin stages wrap existing detector nodes in pipeline/nodes/*.
"""
from app.pipeline.stages.base import StagePlugin, StageSpec, StageStatus
from app.pipeline.stages.registry import StageRegistry, get_stage_registry

__all__ = [
    "StagePlugin",
    "StageSpec",
    "StageStatus",
    "StageRegistry",
    "get_stage_registry",
]
