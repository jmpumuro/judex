"""
Generic LangGraph pipeline that builds dynamically from EvaluationCriteria.

This module provides a proper LangGraph pipeline like graph.py but:
- Dynamically selects detectors based on criteria (via routing)
- Uses FusionEngine for per-criterion scores using the configured strategy
- Supports user-defined criteria without hardcoded logic
"""
import asyncio
from typing import Dict, Any, Optional, List, Callable
from langgraph.graph import StateGraph, END

from app.pipeline.state import PipelineState
from app.pipeline.nodes.ingest_video import ingest_video
from app.pipeline.nodes.segment_video import segment_video
from app.pipeline.nodes.yolo26_vision import run_yolo26_vision
from app.pipeline.nodes.yoloworld_vision import run_yoloworld_vision
from app.pipeline.nodes.violence_video import run_violence_model
from app.pipeline.nodes.audio_asr import run_audio_asr
from app.pipeline.nodes.ocr import run_ocr
from app.pipeline.nodes.text_moderation import run_text_moderation
from app.pipeline.nodes.llm_report import generate_llm_report
from app.evaluation.criteria import EvaluationCriteria
from app.evaluation.routing import route_criteria_to_detectors
from app.core.logging import get_logger
from app.utils.timing import TimingTracker

logger = get_logger("generic_graph")


# ===== GENERIC FUSION NODE =====

def generic_fuse_policy(state: PipelineState) -> PipelineState:
    """
    Fuse evidence into criterion scores using Strategy/Factory patterns.
    
    Uses unified result format from app.evaluation.result.
    """
    from app.utils.progress import save_stage_output
    from app.fusion.scorers import DetectorSignals, compute_criterion_score, ScorerRegistry
    from app.fusion.verdict import get_verdict_strategy, list_verdict_strategies
    from app.evaluation.result import create_criterion_score, Violation
    
    criteria: EvaluationCriteria = state.get("evaluation_criteria")
    if not criteria:
        logger.warning("No evaluation_criteria in state, using defaults")
        from app.evaluation.criteria import CHILD_SAFETY_CRITERIA
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
    verdict_strategy = get_verdict_strategy(criteria.options.verdict_strategy if criteria.options else None)
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


# ===== DYNAMIC GRAPH BUILDER =====

def build_generic_graph(detectors_to_run: List[str]) -> StateGraph:
    """
    Build a LangGraph pipeline with only the specified detectors.
    
    Args:
        detectors_to_run: List of detector IDs to include (e.g., ["yolo26", "xclip", "whisper"])
        
    Returns:
        Compiled StateGraph
    """
    workflow = StateGraph(PipelineState)
    
    # Always add ingest and segment
    workflow.add_node("ingest_video", ingest_video)
    workflow.add_node("segment_video", segment_video)
    
    # Map detector IDs to nodes
    detector_nodes = {
        "yolo26": ("run_yolo26_vision", run_yolo26_vision),
        "yoloworld": ("run_yoloworld_vision", run_yoloworld_vision),
        "xclip": ("run_violence_model", run_violence_model),
        "whisper": ("run_audio_asr", run_audio_asr),
        "ocr": ("run_ocr", run_ocr),
        "text_moderation": ("run_text_moderation", run_text_moderation),
    }
    
    # Add required detector nodes
    active_nodes = []
    for detector_id in detectors_to_run:
        if detector_id in detector_nodes:
            node_name, node_func = detector_nodes[detector_id]
            workflow.add_node(node_name, node_func)
            active_nodes.append(node_name)
    
    # Always add fusion and report (finalize removed - result built in run_generic_pipeline)
    workflow.add_node("generic_fuse_policy", generic_fuse_policy)
    workflow.add_node("generate_llm_report", generate_llm_report)
    
    # Set entry point
    workflow.set_entry_point("ingest_video")
    
    # Build edges: ingest -> segment -> detectors (in order) -> fusion -> report -> END
    workflow.add_edge("ingest_video", "segment_video")
    
    # Chain detector nodes in order
    prev_node = "segment_video"
    for node_name in active_nodes:
        workflow.add_edge(prev_node, node_name)
        prev_node = node_name
    
    # Connect last detector to fusion, then report, then END
    workflow.add_edge(prev_node, "generic_fuse_policy")
    workflow.add_edge("generic_fuse_policy", "generate_llm_report")
    workflow.add_edge("generate_llm_report", END)
    
    logger.info(f"Built graph with detectors: {detectors_to_run}")
    logger.info(f"Node order: ingest_video -> segment_video -> {' -> '.join(active_nodes)} -> generic_fuse_policy -> generate_llm_report -> END")
    
    return workflow.compile()


# ===== MAIN ENTRY POINT =====

async def run_generic_pipeline(
    video_path: str,
    criteria: EvaluationCriteria,
    video_id: Optional[str] = None,
    progress_callback: Optional[Callable] = None
) -> Dict[str, Any]:
    """
    Run the generic pipeline with user-defined criteria.
    
    This is the main entry point that:
    1. Routes criteria to detectors
    2. Builds a dynamic LangGraph with only needed detectors
    3. Runs the pipeline
    4. Returns results with per-criterion scores
    
    Args:
        video_path: Path to video file
        criteria: User-defined EvaluationCriteria
        video_id: Optional ID for progress tracking and checkpointing
        progress_callback: Optional async callback for progress updates
        
    Returns:
        Evaluation result dictionary
    """
    logger.info(f"Starting generic pipeline for: {video_path}")
    logger.info(f"Using criteria: {criteria.name}")
    
    # Route criteria to detectors
    detectors_to_run = route_criteria_to_detectors(criteria)
    logger.info(f"Auto-routed to detectors: {detectors_to_run}")
    
    # Build dynamic graph
    graph = build_generic_graph(detectors_to_run)
    
    # Create progress callback wrapper
    async def wrapped_progress_callback(stage: str, message: str, progress: int):
        """
        Send progress updates.
        
        If a progress_callback is provided, use it exclusively (it handles SSE/WebSocket).
        Otherwise, send via SSE/WebSocket directly using video_id.
        This avoids channel mismatch (video_id vs evaluation_id).
        """
        if progress_callback:
            # Caller handles SSE broadcasting (e.g., evaluations API sends to evaluation_id)
            try:
                result = progress_callback(stage, message, progress)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")
        elif video_id:
            # Legacy: direct SSE/WebSocket for non-evaluation flows
            from app.api.websocket import manager
            from app.api.sse import sse_manager
            await asyncio.gather(
                manager.send_progress(video_id, stage, message, progress),
                sse_manager.send_progress(video_id, stage, message, progress),
                return_exceptions=True
            )
    
    # Initialize state with criteria
    initial_state = PipelineState(
        video_path=video_path,
        policy_config={},  # Not used with generic fusion
        progress_callback=wrapped_progress_callback,
        video_id=video_id,
        evaluation_criteria=criteria  # Pass criteria for fusion
    )
    
    # Track timing
    tracker = TimingTracker()
    tracker.start("total")
    
    try:
        # Run pipeline
        final_state = await graph.ainvoke(initial_state)
        
        tracker.end("total")
        
        # Send completion (only if no progress_callback, otherwise caller handles it)
        if video_id and not progress_callback:
            from app.api.websocket import manager
            from app.api.sse import sse_manager
            await asyncio.gather(
                manager.send_complete(video_id),
                sse_manager.send_complete(video_id),
                return_exceptions=True
            )
        
        # Build result directly from state (more reliable than finalize node packaging)
        # This ensures criteria_scores from generic_fuse_policy is correctly captured
        result = {
            "verdict": final_state.get("verdict", "UNKNOWN"),
            "confidence": final_state.get("confidence", 0.0),
            "criteria": final_state.get("criteria_scores", {}),  # Direct from fusion
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
            "detectors_run": detectors_to_run,
            "labeled_video_path": final_state.get("labeled_video_path"),
        }
        
        logger.info(f"Generic pipeline complete: verdict={result['verdict']}, criteria_count={len(result['criteria'])}")
        return result
    
    except Exception as e:
        logger.error(f"Generic pipeline failed: {e}", exc_info=True)
        tracker.end("total")
        
        return {
            "verdict": "NEEDS_REVIEW",
            "criteria": {},
            "violations": [],
            "evidence": {},
            "report": f"Pipeline execution failed: {str(e)}",
            "error": str(e),
            "timings": tracker.get_summary(),
            "criteria_name": criteria.name,
            "detectors_run": detectors_to_run
        }


# ===== BACKWARD COMPATIBILITY =====

async def run_pipeline_with_criteria(
    video_path: str,
    preset_id: str = "child_safety",
    video_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convenience function to run pipeline with a preset.
    
    Args:
        video_path: Path to video file
        preset_id: Preset ID ("child_safety", "brand_safety", "general_moderation")
        video_id: Optional video ID for progress tracking
        
    Returns:
        Evaluation result
    """
    from app.evaluation.criteria import get_preset
    
    criteria = get_preset(preset_id)
    return await run_generic_pipeline(video_path, criteria, video_id)
