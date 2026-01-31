"""
Stable LangGraph pipeline with PostgreSQL checkpointing.

This module provides a STABLE graph structure that:
- Uses proper LangGraph checkpointing for state persistence
- Uses LangGraph-native callbacks (industry standard)
- Enables resume from any node boundary
- Full state serialization (checkpoint-safe)

Graph structure:
  ingest_video -> segment_video -> run_pipeline -> fuse_policy -> llm_report -> END
                                        |
                                        └─> (dynamic stages via PipelineRunner)

Industry Standard Approach:
- Callbacks are passed via config["callbacks"], not state
- Evaluation criteria passed via config["configurable"]["evaluation_criteria"]
- State contains ONLY serializable data (checkpoint-safe)
"""
import asyncio
from typing import Optional, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig

from app.pipeline.state import PipelineState
from app.pipeline.callbacks import (
    create_pipeline_config,
    get_progress_callback,
    get_evaluation_criteria,
    send_progress,
)
from app.core.logging import get_logger
from app.utils.timing import TimingTracker

logger = get_logger("graph")


# ===== NODE WRAPPERS =====
# These wrap the actual node functions to inject config handling

def ingest_video_with_config(state: PipelineState, config: RunnableConfig) -> PipelineState:
    """Ingest video node with LangGraph config support."""
    from app.pipeline.nodes.ingest_video import ingest_video_impl
    return ingest_video_impl(state, config)


def segment_video_with_config(state: PipelineState, config: RunnableConfig) -> PipelineState:
    """Segment video node with LangGraph config support."""
    from app.pipeline.nodes.segment_video import segment_video_impl
    return segment_video_impl(state, config)


def run_pipeline_with_config(state: PipelineState, config: RunnableConfig) -> PipelineState:
    """Run pipeline node with LangGraph config support."""
    from app.pipeline.nodes.run_pipeline import run_pipeline_node_impl
    return run_pipeline_node_impl(state, config)


def fuse_policy_with_config(state: PipelineState, config: RunnableConfig) -> PipelineState:
    """
    Fuse evidence into criterion scores using Strategy/Factory patterns.
    
    Uses unified result format from app.evaluation.result.
    Industry standard: Gets criteria from config, not state.
    """
    from app.utils.progress import save_stage_output
    from app.fusion.scorers import DetectorSignals, compute_criterion_score
    from app.fusion.verdict import get_verdict_strategy
    from app.evaluation.result import create_criterion_score, Violation
    from app.evaluation.criteria import EvaluationCriteria, CHILD_SAFETY_CRITERIA
    
    # Send progress via config callbacks (industry standard)
    send_progress(config, "policy_fusion", "Computing safety scores", 85)
    
    # Get criteria from config (industry standard - not from state)
    criteria: EvaluationCriteria = get_evaluation_criteria(config)
    
    if not criteria:
        logger.warning("No evaluation_criteria in config, using defaults")
        criteria = CHILD_SAFETY_CRITERIA
    
    # Build signals from state
    signals = DetectorSignals.from_state(state)
    
    # Compute per-criterion scores using unified format
    criteria_scores = {}
    violations = []
    
    for criterion_id, criterion in criteria.get_enabled_criteria().items():
        score = compute_criterion_score(criterion_id, criterion, signals)
        thresholds = criterion.thresholds
        
        # Create unified CriterionScore
        criterion_score = create_criterion_score(
            score=score,
            label=criterion.label,
            severity=criterion.severity.value,
            safe_threshold=thresholds.safe,
            caution_threshold=thresholds.caution,
            unsafe_threshold=thresholds.unsafe
        )
        
        criteria_scores[criterion_id] = criterion_score.to_dict()
        
        # Track violations
        if criterion_score.verdict == "UNSAFE":
            violations.append(Violation(
                criterion=criterion_id,
                label=criterion.label,
                severity=criterion.severity.value,
                score=criterion_score.score
            ).to_dict())
    
    # Determine final verdict using configured strategy
    verdict_strategy = get_verdict_strategy(
        criteria.options.verdict_strategy if criteria.options else None
    )
    verdict_result = verdict_strategy.determine(criteria_scores)
    
    final_verdict = verdict_result.verdict.value
    confidence = verdict_result.confidence
    
    # Factor in external stage results
    if signals.external_verdicts:
        logger.info(f"External stage verdicts: {signals.external_verdicts}")
        
        # If any external stage says FAIL, escalate to UNSAFE
        if "FAIL" in signals.external_verdicts:
            if final_verdict == "SAFE":
                final_verdict = "UNSAFE"
                logger.info("External stage FAIL escalated verdict to UNSAFE")
        
        # If external stage says REVIEW and we're SAFE, escalate to NEEDS_REVIEW
        elif "REVIEW" in signals.external_verdicts:
            if final_verdict == "SAFE":
                final_verdict = "NEEDS_REVIEW"
                logger.info("External stage REVIEW escalated verdict to NEEDS_REVIEW")
        
        # Add external violations to the list
        for ext_violation in signals.external_violations:
            violations.append({
                "criterion": "external_policy",
                "label": ext_violation.get("policy_name", "External Policy"),
                "severity": ext_violation.get("severity", "medium"),
                "score": ext_violation.get("confidence", 0.5),
                "description": ext_violation.get("description", ""),
                "source": "external_stage"
            })
        
        # Adjust confidence based on external confidence
        if signals.external_confidence > 0:
            confidence = (confidence + signals.external_confidence) / 2
    
    # Reduce confidence if supporting stages were skipped
    if signals.skipped_supporting_count > 0:
        confidence_reduction = min(0.15 * signals.skipped_supporting_count, 0.3)
        confidence = max(0.1, confidence - confidence_reduction)
        logger.warning(
            f"Reduced confidence by {confidence_reduction:.2f} due to "
            f"{signals.skipped_supporting_count} skipped supporting stage(s)"
        )
    
    # Build stage output
    stage_output = {
        "verdict": final_verdict,
        "confidence": round(confidence, 3),
        "criteria": criteria_scores,
        "violations": violations,
        "criteria_evaluated": len(criteria_scores),
        "verdict_strategy": verdict_strategy.__class__.__name__,
        "skipped_stages": signals.skipped_stages,
        "skipped_supporting_count": signals.skipped_supporting_count,
    }
    
    # Save stage output for UI
    video_id = state.get("video_id")
    if video_id:
        save_stage_output(video_id, "policy_fusion", stage_output)
    
    # Update state with unified format
    state["criteria_scores"] = criteria_scores
    state["violations"] = violations
    state["verdict"] = final_verdict
    state["confidence"] = confidence
    state["skipped_stages"] = signals.skipped_stages
    
    if signals.skipped_stages:
        logger.info(f"Fusion complete: {final_verdict} (confidence: {confidence:.2f}) - {len(signals.skipped_stages)} stages skipped")
    else:
        logger.info(f"Fusion complete: {final_verdict} (confidence: {confidence:.2f})")
    
    return state


def generate_llm_report_with_config(state: PipelineState, config: RunnableConfig) -> PipelineState:
    """LLM report node with LangGraph config support."""
    from app.pipeline.nodes.llm_report import generate_llm_report_impl
    return generate_llm_report_impl(state, config)


# ===== GRAPH BUILDER =====

def build_graph_workflow() -> StateGraph:
    """
    Build the LangGraph workflow (uncompiled).
    
    All nodes receive (state, config) - the industry standard signature
    that allows callbacks and metadata to be passed via config.
    """
    workflow = StateGraph(PipelineState)
    
    # Add nodes with config support (industry standard)
    workflow.add_node("ingest_video", ingest_video_with_config)
    workflow.add_node("segment_video", segment_video_with_config)
    workflow.add_node("run_pipeline", run_pipeline_with_config)
    workflow.add_node("fuse_policy", fuse_policy_with_config)
    workflow.add_node("generate_llm_report", generate_llm_report_with_config)
    
    # Set entry point
    workflow.set_entry_point("ingest_video")
    
    # Add edges (fixed)
    workflow.add_edge("ingest_video", "segment_video")
    workflow.add_edge("segment_video", "run_pipeline")
    workflow.add_edge("run_pipeline", "fuse_policy")
    workflow.add_edge("fuse_policy", "generate_llm_report")
    workflow.add_edge("generate_llm_report", END)
    
    return workflow


# Cached compiled graphs
_graph_no_checkpoint = None
_graph_with_async_checkpoint = None


def get_graph_without_checkpointing():
    """Get compiled graph without checkpointing (for simple runs)."""
    global _graph_no_checkpoint
    if _graph_no_checkpoint is None:
        workflow = build_graph_workflow()
        _graph_no_checkpoint = workflow.compile()
        logger.info("Built graph without checkpointing")
    return _graph_no_checkpoint


async def get_graph_with_checkpointing():
    """
    Get compiled graph with async PostgreSQL checkpointing.
    
    This enables:
    - State persistence after each node
    - Resume from any checkpoint
    - Full state serialization
    
    Note: This is async because the checkpointer initialization is async.
    """
    global _graph_with_async_checkpoint
    if _graph_with_async_checkpoint is None:
        try:
            from app.pipeline.checkpointer import get_async_checkpointer
            
            workflow = build_graph_workflow()
            checkpointer = await get_async_checkpointer()
            _graph_with_async_checkpoint = workflow.compile(checkpointer=checkpointer)
            logger.info("Built graph with async PostgreSQL checkpointing")
            
        except Exception as e:
            logger.warning(f"Failed to initialize async checkpointing, falling back to no checkpoint: {e}")
            _graph_with_async_checkpoint = get_graph_without_checkpointing()
    
    return _graph_with_async_checkpoint


def reset_graphs():
    """Reset cached graphs (for testing)."""
    global _graph_no_checkpoint, _graph_with_async_checkpoint
    _graph_no_checkpoint = None
    _graph_with_async_checkpoint = None


# ===== MAIN ENTRY POINT =====

async def run_pipeline(
    video_path: str,
    criteria=None,
    video_id: str = None,
    progress_callback=None,
    resume_from_checkpoint: bool = False,
    existing_state: dict = None,
    media_type: str = None,  # "video" or "image" - auto-detected if None
) -> dict:
    """
    Run the complete pipeline with optional checkpointing.
    
    This is the main entry point for media evaluation (video or image).
    
    Industry Standard:
    - Callbacks passed via config["callbacks"]
    - Criteria passed via config["configurable"]["evaluation_criteria"]
    - State contains ONLY serializable data
    - Media type determines which stages run (images skip temporal stages)
    
    Args:
        video_path: Path to media file (video or image)
        criteria: EvaluationCriteria object (or None for default)
        video_id: Optional media ID for progress tracking and checkpointing
        progress_callback: Optional async callback for progress updates
        resume_from_checkpoint: If True, skip ingest/segment if existing_state provided
        existing_state: Pre-existing state from previous run (for reprocessing)
        media_type: Media type ("video" or "image"), auto-detected if None
        
    Returns:
        Evaluation result dictionary
    """
    # Auto-detect media type if not provided
    if media_type is None:
        from app.utils.media import detect_media_type
        detected = detect_media_type(video_path)
        media_type = detected.value
    
    logger.info(f"Starting pipeline for {media_type}: {video_path} (resume={resume_from_checkpoint}, has_existing_state={existing_state is not None})")
    
    # Default criteria
    if criteria is None:
        from app.evaluation.criteria import CHILD_SAFETY_CRITERIA
        criteria = CHILD_SAFETY_CRITERIA
    
    logger.info(f"Using criteria: {criteria.name}")
    
    # Create progress callback wrapper
    async def wrapped_progress_callback(stage: str, message: str, progress: int):
        if progress_callback:
            try:
                result = progress_callback(stage, message, progress)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")
        elif video_id:
            # Direct SSE for non-evaluation flows
            from app.api.sse import sse_manager
            await sse_manager.broadcast_progress(
                video_id,
                {"stage": stage, "message": message, "progress": progress}
            )
    
    # Initialize state - ONLY serializable data (industry standard)
    initial_state = PipelineState(
        video_path=video_path,
        media_path=video_path,  # Unified media path
        media_type=media_type,  # "video" or "image"
        policy_config={},
        video_id=video_id,
    )
    
    # Create config with callbacks and criteria (industry standard)
    # Non-serializable items go in config, NOT state
    config = create_pipeline_config(
        video_id=video_id or "default",
        progress_callback=wrapped_progress_callback,
        evaluation_criteria=criteria,
    )
    
    # Track timing
    tracker = TimingTracker()
    tracker.start("total")
    
    try:
        # Use checkpointing if video_id is provided
        if video_id:
            graph = await get_graph_with_checkpointing()
            # Merge thread_id into config (for checkpointing)
            config["configurable"]["thread_id"] = video_id
            
            # If existing_state is provided (reprocessing), merge it into initial_state
            if existing_state and resume_from_checkpoint:
                logger.info(f"Merging existing state for reprocessing (keys: {list(existing_state.keys())})")
                
                # Merge existing state values into initial state
                for key, value in existing_state.items():
                    if value is not None:
                        initial_state[key] = value
                
                # Mark that we're reprocessing so ingest/segment can be skipped
                initial_state["is_reprocessing"] = True
                
                logger.info(f"Merged existing state: duration={existing_state.get('duration')}, fps={existing_state.get('fps')}, has_audio={existing_state.get('has_audio')}")
            
            elif resume_from_checkpoint:
                # Legacy checkpoint-based resume
                logger.info(f"Resuming from checkpoint for {video_id}")
                
                # Get existing checkpoint state
                from app.pipeline.checkpointer import get_checkpoint_state
                checkpoint_state = await get_checkpoint_state(video_id)
                
                if checkpoint_state:
                    # Merge checkpoint state into initial state
                    for key, value in checkpoint_state.items():
                        if key not in initial_state or initial_state[key] is None:
                            initial_state[key] = value
                    
                    initial_state["is_reprocessing"] = True
                    logger.info(f"Loaded checkpoint with keys: {list(checkpoint_state.keys())[:10]}...")
                else:
                    logger.warning(f"No checkpoint found for {video_id}, running full pipeline")
                
                # Use a new thread_id for this reprocess run to avoid conflicts
                config["configurable"]["thread_id"] = f"{video_id}_reprocess"
            
            final_state = await graph.ainvoke(initial_state, config)
        else:
            # No video_id - run without checkpointing
            graph = get_graph_without_checkpointing()
            final_state = await graph.ainvoke(initial_state, config)
        
        tracker.end("total")
        
        # Build result
        result = {
            "verdict": final_state.get("verdict", "UNKNOWN"),
            "confidence": final_state.get("confidence", 0.0),
            "criteria": final_state.get("criteria_scores", {}),
            "violations": final_state.get("violations", []),
            "evidence": final_state.get("evidence", {}),
            "report": final_state.get("report", ""),
            "transcript": {
                "text": final_state.get("transcript", {}).get("full_text", "") if isinstance(final_state.get("transcript"), dict) else "",
                "chunks": final_state.get("transcript", {}).get("chunks", []) if isinstance(final_state.get("transcript"), dict) else []
            },
            "metadata": {
                "video_id": video_id,
                "duration": final_state.get("duration", 0),
                "fps": final_state.get("fps", 0),
                "width": final_state.get("width", 0),
                "height": final_state.get("height", 0),
                "has_audio": final_state.get("has_audio", False),
            },
            "timings": tracker.get_summary(),
            "criteria_name": criteria.name,
            "stage_runs": final_state.get("stage_runs", []),
            "labeled_video_path": final_state.get("labeled_video_path"),
        }
        
        logger.info(f"Pipeline complete: verdict={result['verdict']}")
        return result
        
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}", exc_info=True)
        tracker.end("total")
        
        return {
            "verdict": "NEEDS_REVIEW",
            "criteria": {},
            "violations": [],
            "evidence": {},
            "report": f"Pipeline execution failed: {str(e)}",
            "error": str(e),
            "timings": tracker.get_summary(),
            "criteria_name": criteria.name if criteria else "unknown",
        }


async def resume_pipeline(video_id: str, criteria=None) -> dict:
    """
    Resume a pipeline from its last checkpoint.
    
    This is a convenience wrapper for run_pipeline with resume=True.
    """
    from app.pipeline.checkpointer import get_checkpoint_state
    
    checkpoint_state = await get_checkpoint_state(video_id)
    if not checkpoint_state:
        raise ValueError(f"No checkpoint found for {video_id}")
    
    video_path = checkpoint_state.get("video_path")
    if not video_path:
        raise ValueError(f"Checkpoint for {video_id} has no video_path")
    
    return await run_pipeline(
        video_path=video_path,
        criteria=criteria,
        video_id=video_id,
        resume_from_checkpoint=True,
    )


def run_pipeline_sync(video_path: str, criteria=None, video_id: str = None) -> dict:
    """Run pipeline synchronously (for non-async contexts)."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(run_pipeline(video_path, criteria, video_id))


# Legacy aliases for backward compatibility
get_stable_graph = get_graph_without_checkpointing
build_stable_graph = build_graph_workflow
