"""
Stable LangGraph pipeline definition.

This module provides a STABLE graph structure that does not change per-request.
Dynamic detector selection happens inside the run_pipeline node via PipelineRunner.

Graph structure:
  ingest_video -> segment_video -> run_pipeline -> fuse_policy -> llm_report -> END
                                        |
                                        └─> (dynamic stages via PipelineRunner)

The run_pipeline node:
1. Reads evaluation_criteria from state
2. Routes criteria to detectors (or uses explicit pipeline definition)
3. Executes stages dynamically via PipelineRunner
4. Returns state with all detector outputs merged

This design:
- Avoids graph-per-request compilation overhead
- Supports pluggable stages without changing graph structure
- Maintains backward compatibility with existing criteria/presets
"""
import asyncio
from langgraph.graph import StateGraph, END
from app.pipeline.state import PipelineState
from app.pipeline.nodes.ingest_video import ingest_video
from app.pipeline.nodes.segment_video import segment_video
from app.pipeline.nodes.run_pipeline import run_pipeline_node
from app.pipeline.nodes.llm_report import generate_llm_report
from app.core.logging import get_logger
from app.utils.timing import TimingTracker

logger = get_logger("graph")


# ===== FUSION NODE =====

def fuse_policy_generic(state: PipelineState) -> PipelineState:
    """
    Fuse evidence into criterion scores using Strategy/Factory patterns.
    
    Uses unified result format from app.evaluation.result.
    """
    from app.utils.progress import save_stage_output
    from app.fusion.scorers import DetectorSignals, compute_criterion_score
    from app.fusion.verdict import get_verdict_strategy
    from app.evaluation.result import create_criterion_score, Violation
    from app.evaluation.criteria import EvaluationCriteria, CHILD_SAFETY_CRITERIA
    
    criteria: EvaluationCriteria = state.get("evaluation_criteria")
    if not criteria:
        logger.warning("No evaluation_criteria in state, using defaults")
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
    
    # Build stage output
    stage_output = {
        "verdict": final_verdict,
        "confidence": round(confidence, 3),
        "criteria": criteria_scores,
        "violations": violations,
        "criteria_evaluated": len(criteria_scores),
        "verdict_strategy": verdict_strategy.__class__.__name__
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
    
    logger.info(f"Fusion complete: {final_verdict} (confidence: {confidence:.2f})")
    
    return state


# ===== STABLE GRAPH BUILDER =====

def build_stable_graph() -> StateGraph:
    """
    Build the stable LangGraph pipeline.
    
    This graph is compiled ONCE and reused for all evaluations.
    Dynamic detector selection happens inside run_pipeline node.
    
    Returns:
        Compiled StateGraph
    """
    workflow = StateGraph(PipelineState)
    
    # Add nodes (fixed set)
    workflow.add_node("ingest_video", ingest_video)
    workflow.add_node("segment_video", segment_video)
    workflow.add_node("run_pipeline", run_pipeline_node)  # Dynamic stages inside
    workflow.add_node("fuse_policy", fuse_policy_generic)
    workflow.add_node("generate_llm_report", generate_llm_report)
    
    # Set entry point
    workflow.set_entry_point("ingest_video")
    
    # Add edges (fixed)
    workflow.add_edge("ingest_video", "segment_video")
    workflow.add_edge("segment_video", "run_pipeline")
    workflow.add_edge("run_pipeline", "fuse_policy")
    workflow.add_edge("fuse_policy", "generate_llm_report")
    workflow.add_edge("generate_llm_report", END)
    
    logger.info("Built stable graph: ingest -> segment -> run_pipeline -> fuse_policy -> llm_report -> END")
    
    return workflow.compile()


# Cached compiled graph (singleton)
_stable_graph = None


def get_stable_graph() -> StateGraph:
    """Get the cached stable graph (compile once, reuse)."""
    global _stable_graph
    if _stable_graph is None:
        _stable_graph = build_stable_graph()
    return _stable_graph


# ===== MAIN ENTRY POINT =====

async def run_pipeline(
    video_path: str,
    criteria=None,
    video_id: str = None,
    progress_callback=None,
) -> dict:
    """
    Run the complete stable pipeline.
    
    This is the main entry point for video evaluation.
    Uses the stable graph with dynamic stage execution.
    
    Args:
        video_path: Path to video file
        criteria: EvaluationCriteria object (or None for default)
        video_id: Optional video ID for progress tracking
        progress_callback: Optional async callback for progress updates
        
    Returns:
        Evaluation result dictionary
    """
    logger.info(f"Starting pipeline for video: {video_path}")
    
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
    
    # Initialize state
    initial_state = PipelineState(
        video_path=video_path,
        policy_config={},
        progress_callback=wrapped_progress_callback,
        video_id=video_id,
        evaluation_criteria=criteria,
    )
    
    # Track timing
    tracker = TimingTracker()
    tracker.start("total")
    
    try:
        # Get stable graph and run
        graph = get_stable_graph()
        final_state = await graph.ainvoke(initial_state)
        
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
                "text": final_state.get("transcript", {}).get("full_text", ""),
                "chunks": final_state.get("transcript", {}).get("chunks", [])
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


def run_pipeline_sync(video_path: str, criteria=None, video_id: str = None) -> dict:
    """Run pipeline synchronously (for non-async contexts)."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(run_pipeline(video_path, criteria, video_id))
