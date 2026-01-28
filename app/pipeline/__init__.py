"""
Pipeline package for video evaluation.

This package provides the LangGraph-based video analysis pipeline with:
- Stable graph structure (no per-request compilation)
- Pluggable stage system (StagePlugin + StageRegistry)
- PipelineRunner for dynamic stage execution

Main entry points:
- run_pipeline(): Run evaluation with stable graph
- get_stable_graph(): Get cached compiled graph
- get_stage_registry(): Get registry of available stages
"""
from app.pipeline.graph import (
    run_pipeline,
    run_pipeline_sync,
    get_stable_graph,
    build_stable_graph,
)
from app.pipeline.state import PipelineState
from app.pipeline.runner import (
    PipelineRunner,
    StageRun,
    PipelineRunResult,
    build_pipeline_from_criteria,
    build_pipeline_from_detectors,
)
from app.pipeline.stages import (
    StagePlugin,
    StageSpec,
    StageStatus,
    StageRegistry,
    get_stage_registry,
)

__all__ = [
    # Main entry points
    "run_pipeline",
    "run_pipeline_sync",
    "get_stable_graph",
    "build_stable_graph",
    
    # State
    "PipelineState",
    
    # Runner
    "PipelineRunner",
    "StageRun",
    "PipelineRunResult",
    "build_pipeline_from_criteria",
    "build_pipeline_from_detectors",
    
    # Stages
    "StagePlugin",
    "StageSpec",
    "StageStatus",
    "StageRegistry",
    "get_stage_registry",
]
