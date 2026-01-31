"""
Run Pipeline node - executes dynamic detector stages via PipelineRunner.

This is the bridge between the stable LangGraph structure and the
dynamic stage execution system. All detector stages run inside
this single node, keeping the main graph stable.

Industry Standard Architecture:
- Plugin Pattern: Stages are self-contained plugins
- Registry Pattern: Dynamic stage discovery
- Phase-based Execution: Independent stages can run in parallel
- Uses LangGraph config for callbacks and criteria

Graph structure becomes:
  ingest -> segment -> run_pipeline -> fuse_policy -> llm_report -> END
                         └── (dynamic stages via PipelineRunner)

Parallel Execution Phases:
  1. INGEST: Video ingestion
  2. EXTRACT: Frame extraction, segmentation
  3. PREPROCESS: Window mining, quick YOLO pass
  4. DETECT: Main detectors (parallel: xclip, videomae, pose, whisper, ocr)
  5. ANALYZE: Text moderation
  6. FUSE: Score fusion
  7. REPORT: Report generation
"""
import asyncio
import os
from typing import Dict, Any, Optional
from langchain_core.runnables import RunnableConfig

from app.pipeline.state import PipelineState
from app.pipeline.runner import PipelineRunner, build_pipeline_from_criteria
from app.pipeline.callbacks import get_progress_callback, get_evaluation_criteria, send_progress
from app.core.logging import get_logger

logger = get_logger("node.run_pipeline")

# Environment configuration for parallel execution
ENABLE_PARALLEL_EXECUTION = os.getenv("ENABLE_PARALLEL_STAGES", "false").lower() == "true"
MAX_PARALLEL_STAGES = int(os.getenv("MAX_PARALLEL_STAGES", "3"))


def run_pipeline_node_impl(state: PipelineState, config: Optional[RunnableConfig] = None) -> PipelineState:
    """
    LangGraph node that runs detector stages dynamically.
    
    Industry Standard: Receives config parameter for callbacks and criteria.
    - Callbacks from config["callbacks"]
    - Criteria from config["configurable"]["evaluation_criteria"]
    
    This node:
    1. Reads evaluation_criteria from config (not state)
    2. Builds a pipeline plan (from criteria.pipeline or auto-routing)
    3. Executes stages via PipelineRunner
    4. Returns updated state with all detector outputs
    """
    logger.info("=== Run Pipeline Node ===")
    
    # Get progress callback from config (industry standard)
    progress_handler = get_progress_callback(config)
    progress_callback = progress_handler.send_progress_sync if progress_handler else None
    
    send_progress(config, "run_pipeline", "Starting detector pipeline", 25)
    
    # Get criteria from config (industry standard - not from state)
    criteria = get_evaluation_criteria(config)
    if not criteria:
        logger.warning("No evaluation_criteria in config, using defaults")
        from app.evaluation.criteria import CHILD_SAFETY_CRITERIA
        criteria = CHILD_SAFETY_CRITERIA
    
    # Build pipeline from criteria
    stages = build_pipeline_from_criteria(criteria)
    logger.info(f"Built pipeline with {len(stages)} stages: {[s.type for s in stages]}")
    
    if not stages:
        logger.warning("No stages to run - skipping detector pipeline")
        return state
    
    # Create runner with progress callback
    # Note: We pass the raw callback function, not the handler
    runner = PipelineRunner(
        progress_callback=progress_callback,
        video_id=state.get("video_id"),
        stop_on_error=False,
    )
    
    # Run the pipeline (parallel or sequential based on config)
    try:
        # Choose execution mode
        if ENABLE_PARALLEL_EXECUTION:
            logger.info(f"Using PARALLEL execution (max_parallel={MAX_PARALLEL_STAGES})")
            run_coro = runner.run_parallel(stages, dict(state), max_parallel=MAX_PARALLEL_STAGES)
        else:
            logger.info("Using SEQUENTIAL execution")
            run_coro = runner.run(stages, dict(state))
        
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, run_coro)
                result = future.result()
        else:
            result = loop.run_until_complete(run_coro)
    except RuntimeError:
        if ENABLE_PARALLEL_EXECUTION:
            result = asyncio.run(runner.run_parallel(stages, dict(state), max_parallel=MAX_PARALLEL_STAGES))
        else:
            result = asyncio.run(runner.run(stages, dict(state)))
    
    # Merge results back into state
    for key, value in result.final_state.items():
        state[key] = value
    
    # Log summary
    successful = sum(1 for r in result.stages_run if r.status.value == "completed")
    logger.info(
        f"Pipeline complete: {successful}/{len(result.stages_run)} stages succeeded, "
        f"{result.total_duration_ms:.0f}ms total"
    )
    
    if result.errors:
        logger.warning(f"Pipeline errors: {result.errors}")
    
    send_progress(config, "run_pipeline", f"Detector pipeline complete ({successful} stages)", 75)
    
    return state


# Legacy wrapper for backward compatibility
def run_pipeline_node(state: PipelineState) -> PipelineState:
    """Legacy wrapper - calls impl without config."""
    return run_pipeline_node_impl(state, None)


async def run_pipeline_node_async(state: PipelineState, config: Optional[RunnableConfig] = None) -> PipelineState:
    """
    Async version of run_pipeline_node for direct async invocation.
    
    Supports parallel execution when ENABLE_PARALLEL_STAGES=true.
    """
    logger.info("=== Run Pipeline Node (Async) ===")
    
    # Get criteria from config
    criteria = get_evaluation_criteria(config)
    if not criteria:
        from app.evaluation.criteria import CHILD_SAFETY_CRITERIA
        criteria = CHILD_SAFETY_CRITERIA
    
    # Get progress callback from config
    progress_handler = get_progress_callback(config)
    progress_callback = progress_handler.send_progress_sync if progress_handler else None
    
    # Build and run pipeline
    stages = build_pipeline_from_criteria(criteria)
    
    runner = PipelineRunner(
        progress_callback=progress_callback,
        video_id=state.get("video_id"),
        stop_on_error=False,
    )
    
    # Choose execution mode based on environment config
    if ENABLE_PARALLEL_EXECUTION:
        logger.info(f"Using PARALLEL execution (max_parallel={MAX_PARALLEL_STAGES})")
        result = await runner.run_parallel(stages, dict(state), max_parallel=MAX_PARALLEL_STAGES)
    else:
        logger.info("Using SEQUENTIAL execution")
        result = await runner.run(stages, dict(state))
    
    # Merge results
    for key, value in result.final_state.items():
        state[key] = value
    
    return state
