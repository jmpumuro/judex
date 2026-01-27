"""
LangGraph definition for live feed analysis.

This graph defines the real-time frame analysis pipeline,
following the same pattern as the batch video pipeline.
"""
from langgraph.graph import StateGraph, END
from app.live.state import LiveFeedState, create_initial_state
from app.live.nodes.capture_frame import capture_frame
from app.live.nodes.detect_objects_yoloe import detect_objects_yoloe  # CHANGED: Using YOLOE
from app.live.nodes.detect_violence import detect_violence
from app.live.nodes.moderate_content import moderate_content
from app.live.nodes.emit_result import emit_result
from app.core.logging import get_logger
from app.utils.timing import TimingTracker
from typing import Dict, Any
import time

logger = get_logger("live.graph")


def should_continue(state: LiveFeedState) -> str:
    """
    Check if graph should continue or stop due to errors.
    
    For live feed, we always continue even with errors,
    but emit a NEEDS_REVIEW verdict.
    """
    errors = state.get("errors", [])
    if errors:
        logger.warning(f"Frame {state['frame_id']} has errors: {errors}")
        # Continue to emit anyway
    return "continue"


def build_live_graph() -> StateGraph:
    """
    Build the LangGraph for live feed analysis.
    
    Graph flow:
    capture_frame → detect_objects_yoloe → detect_violence → moderate_content → emit_result → END
    
    Returns:
        Compiled StateGraph
    """
    
    # Create graph
    workflow = StateGraph(LiveFeedState)
    
    # Add nodes (using YOLOE for live feed)
    workflow.add_node("capture_frame", capture_frame)
    workflow.add_node("detect_objects_yoloe", detect_objects_yoloe)  # CHANGED: YOLOE
    workflow.add_node("detect_violence", detect_violence)
    workflow.add_node("moderate_content", moderate_content)
    workflow.add_node("emit_result", emit_result)
    
    # Set entry point
    workflow.set_entry_point("capture_frame")
    
    # Add edges (linear flow for now, can add conditionals later)
    workflow.add_edge("capture_frame", "detect_objects_yoloe")  # CHANGED
    workflow.add_edge("detect_objects_yoloe", "detect_violence")  # CHANGED
    workflow.add_edge("detect_violence", "moderate_content")
    workflow.add_edge("moderate_content", "emit_result")
    workflow.add_edge("emit_result", END)
    
    return workflow.compile()


# Singleton graph instance (cached for performance)
_graph_instance = None


def get_live_graph() -> StateGraph:
    """Get or create compiled graph instance."""
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = build_live_graph()
        logger.info("Live feed graph compiled and cached")
    return _graph_instance


async def analyze_frame_async(
    frame_id: str,
    frame_data: bytes,
    stream_id: str = "default",
    stream_metadata: Dict[str, Any] = None,
    progress_callback = None
) -> Dict[str, Any]:
    """
    Analyze a single frame asynchronously.
    
    Args:
        frame_id: Unique frame identifier
        frame_data: Raw frame bytes (JPEG/PNG)
        stream_id: Stream identifier
        stream_metadata: Optional stream configuration
        progress_callback: Optional callback for progress updates
        
    Returns:
        Analysis result dictionary
    """
    logger.debug(f"Starting analysis for frame {frame_id}")
    
    # Create initial state
    initial_state = create_initial_state(
        frame_id=frame_id,
        frame_data=frame_data,
        stream_id=stream_id,
        stream_metadata=stream_metadata or {}
    )
    
    if progress_callback:
        initial_state["progress_callback"] = progress_callback
    
    # Track timing
    tracker = TimingTracker()
    tracker.start("total")
    tracker.start("capture")
    
    try:
        # Get graph
        graph = get_live_graph()
        
        # Run graph
        final_state = await graph.ainvoke(initial_state)
        
        tracker.end("capture")
        tracker.end("total")
        
        # Add timing to result
        result = final_state.get("result", {})
        result["timings"] = tracker.get_summary()
        
        logger.info(
            f"Frame {frame_id} analysis complete: "
            f"verdict={result.get('verdict')}, "
            f"time={tracker.get_summary().get('total_seconds', 0):.3f}s"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Frame analysis failed: {e}", exc_info=True)
        tracker.end("capture")
        tracker.end("total")
        
        # Return error result
        return {
            "frame_id": frame_id,
            "stream_id": stream_id,
            "verdict": "NEEDS_REVIEW",
            "errors": [str(e)],
            "objects": [],
            "violence_score": 0.0,
            "processing_time_ms": tracker.get_summary().get("total_seconds", 0) * 1000,
            "error": str(e),
            "timings": tracker.get_summary()
        }


def analyze_frame_sync(
    frame_id: str,
    frame_data: bytes,
    stream_id: str = "default",
    stream_metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Analyze a single frame synchronously.
    
    This is a blocking wrapper around analyze_frame_async.
    Use this for non-async contexts.
    
    Args:
        frame_id: Unique frame identifier
        frame_data: Raw frame bytes
        stream_id: Stream identifier
        stream_metadata: Optional stream configuration
        
    Returns:
        Analysis result dictionary
    """
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(
        analyze_frame_async(frame_id, frame_data, stream_id, stream_metadata)
    )
