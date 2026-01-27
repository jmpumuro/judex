"""
LangGraph pipeline definition.
"""
import asyncio
from langgraph.graph import StateGraph, END
from app.pipeline.state import PipelineState
from app.pipeline.nodes.ingest_video import ingest_video
from app.pipeline.nodes.segment_video import segment_video
from app.pipeline.nodes.yolo26_vision import run_yolo26_vision
from app.pipeline.nodes.yoloworld_vision import run_yoloworld_vision  # NEW
from app.pipeline.nodes.violence_video import run_violence_model
from app.pipeline.nodes.audio_asr import run_audio_asr
from app.pipeline.nodes.ocr import run_ocr
from app.pipeline.nodes.text_moderation import run_text_moderation
from app.pipeline.nodes.fuse_policy import fuse_evidence_policy
from app.pipeline.nodes.llm_report import generate_llm_report
from app.pipeline.nodes.finalize import finalize
from app.core.logging import get_logger
from app.utils.timing import TimingTracker

logger = get_logger("graph")


def should_continue(state: PipelineState) -> str:
    """Check if pipeline should continue or stop due to errors."""
    errors = state.get("errors", [])
    if errors:
        logger.error(f"Pipeline stopped due to errors: {errors}")
        return "finalize"
    return "continue"


def build_graph() -> StateGraph:
    """Build the LangGraph pipeline."""
    
    # Create graph
    workflow = StateGraph(PipelineState)
    
    # Add nodes
    workflow.add_node("ingest_video", ingest_video)
    workflow.add_node("segment_video", segment_video)
    workflow.add_node("run_yolo26_vision", run_yolo26_vision)
    workflow.add_node("run_yoloworld_vision", run_yoloworld_vision)  # NEW
    workflow.add_node("run_violence_model", run_violence_model)
    workflow.add_node("run_audio_asr", run_audio_asr)
    workflow.add_node("run_ocr", run_ocr)
    workflow.add_node("run_text_moderation", run_text_moderation)
    workflow.add_node("fuse_evidence_policy", fuse_evidence_policy)
    workflow.add_node("generate_llm_report", generate_llm_report)
    workflow.add_node("finalize", finalize)
    
    # Set entry point
    workflow.set_entry_point("ingest_video")
    
    # Add edges
    workflow.add_edge("ingest_video", "segment_video")
    workflow.add_edge("segment_video", "run_yolo26_vision")
    workflow.add_edge("run_yolo26_vision", "run_yoloworld_vision")  # NEW: Run YOLO-World after YOLO26
    workflow.add_edge("run_yoloworld_vision", "run_violence_model")  # CHANGED
    workflow.add_edge("run_violence_model", "run_audio_asr")
    workflow.add_edge("run_audio_asr", "run_ocr")
    workflow.add_edge("run_ocr", "run_text_moderation")
    workflow.add_edge("run_text_moderation", "fuse_evidence_policy")
    workflow.add_edge("fuse_evidence_policy", "generate_llm_report")
    workflow.add_edge("generate_llm_report", "finalize")
    workflow.add_edge("finalize", END)
    
    return workflow.compile()


async def run_pipeline(video_path: str, policy_config: dict = None, video_id: str = None) -> dict:
    """Run the complete pipeline."""
    logger.info(f"Starting pipeline for video: {video_path}")
    
    if policy_config is None:
        from app.core.config import get_policy_config
        policy_config = get_policy_config()
    
    # Progress callback for WebSocket/SSE updates
    async def progress_callback(stage: str, message: str, progress: int):
        if video_id:
            from app.api.websocket import manager
            from app.api.sse import sse_manager
            
            # Send to both WebSocket (backward compatibility) and SSE (new)
            await asyncio.gather(
                manager.send_progress(video_id, stage, message, progress),
                sse_manager.send_progress(video_id, stage, message, progress),
                return_exceptions=True  # Don't fail if one fails
            )
    
    # Initialize state
    initial_state = PipelineState(
        video_path=video_path,
        policy_config=policy_config,
        progress_callback=progress_callback
    )
    
    # Build graph
    graph = build_graph()
    
    # Track timing
    tracker = TimingTracker()
    tracker.start("total")
    
    # Run pipeline
    try:
        final_state = await graph.ainvoke(initial_state)
        
        tracker.end("total")
        
        # Send completion
        if video_id:
            from app.api.websocket import manager
            from app.api.sse import sse_manager
            await asyncio.gather(
                manager.send_complete(video_id),
                sse_manager.send_complete(video_id),
                return_exceptions=True
            )
        
        # Add timing to result
        if "result" in final_state:
            final_state["result"]["timings"] = tracker.get_summary()
        
        return final_state.get("result", {})
    
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
            "timings": tracker.get_summary()
        }


def run_pipeline_sync(video_path: str, policy_config: dict = None) -> dict:
    """Run pipeline synchronously (for non-async contexts)."""
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(run_pipeline(video_path, policy_config))
