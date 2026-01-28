"""
Run Pipeline node - executes dynamic detector stages via PipelineRunner.

This is the bridge between the stable LangGraph structure and the
dynamic stage execution system. All detector stages run inside
this single node, keeping the main graph stable.

Graph structure becomes:
  ingest -> segment -> run_pipeline -> fuse_policy -> llm_report -> END
                         └── (dynamic stages via PipelineRunner)
"""
import asyncio
from typing import Dict, Any

from app.pipeline.state import PipelineState
from app.pipeline.runner import PipelineRunner, build_pipeline_from_criteria
from app.core.logging import get_logger
from app.utils.progress import send_progress

logger = get_logger("node.run_pipeline")


def run_pipeline_node(state: PipelineState) -> PipelineState:
    """
    LangGraph node that runs detector stages dynamically.
    
    This node:
    1. Reads evaluation_criteria from state
    2. Builds a pipeline plan (from criteria.pipeline or auto-routing)
    3. Executes stages via PipelineRunner
    4. Returns updated state with all detector outputs
    
    Args:
        state: Current pipeline state (must have evaluation_criteria)
        
    Returns:
        Updated state with detector outputs merged in
    """
    logger.info("=== Run Pipeline Node ===")
    
    send_progress(
        state.get("progress_callback"),
        "run_pipeline",
        "Starting detector pipeline",
        25
    )
    
    # Get criteria for routing
    criteria = state.get("evaluation_criteria")
    if not criteria:
        # Fallback to default child_safety criteria
        logger.warning("No evaluation_criteria in state, using defaults")
        from app.evaluation.criteria import CHILD_SAFETY_CRITERIA
        criteria = CHILD_SAFETY_CRITERIA
    
    # Build pipeline from criteria
    stages = build_pipeline_from_criteria(criteria)
    logger.info(f"Built pipeline with {len(stages)} stages: {[s.type for s in stages]}")
    
    if not stages:
        logger.warning("No stages to run - skipping detector pipeline")
        return state
    
    # Create runner with progress callback
    runner = PipelineRunner(
        progress_callback=state.get("progress_callback"),
        video_id=state.get("video_id"),
        stop_on_error=False,  # Continue on errors, collect all results
    )
    
    # Run the pipeline (sync wrapper for async runner)
    # The runner's stages are async, but LangGraph nodes are sync
    # We need to run the async runner in an event loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're already in an async context (e.g., from ainvoke)
            # Create a new task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    runner.run(stages, dict(state))
                )
                result = future.result()
        else:
            result = loop.run_until_complete(runner.run(stages, dict(state)))
    except RuntimeError:
        # No event loop - create one
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
    
    send_progress(
        state.get("progress_callback"),
        "run_pipeline",
        f"Detector pipeline complete ({successful} stages)",
        75
    )
    
    return state


async def run_pipeline_node_async(state: PipelineState) -> PipelineState:
    """
    Async version of run_pipeline_node for direct async invocation.
    
    Use this when calling from an async context outside of LangGraph,
    or when the graph is compiled with async support.
    """
    logger.info("=== Run Pipeline Node (Async) ===")
    
    # Get criteria
    criteria = state.get("evaluation_criteria")
    if not criteria:
        from app.evaluation.criteria import CHILD_SAFETY_CRITERIA
        criteria = CHILD_SAFETY_CRITERIA
    
    # Build and run pipeline
    stages = build_pipeline_from_criteria(criteria)
    
    runner = PipelineRunner(
        progress_callback=state.get("progress_callback"),
        video_id=state.get("video_id"),
        stop_on_error=False,
    )
    
    result = await runner.run(stages, dict(state))
    
    # Merge results
    for key, value in result.final_state.items():
        state[key] = value
    
    return state
