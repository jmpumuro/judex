"""
Pipeline nodes package.

Contains individual node functions for the LangGraph pipeline.
Each node represents a processing step that transforms PipelineState.
"""
from app.pipeline.nodes.ingest_video import ingest_video
from app.pipeline.nodes.segment_video import segment_video
from app.pipeline.nodes.run_pipeline import run_pipeline_node
from app.pipeline.nodes.yolo26_vision import run_yolo26_vision
from app.pipeline.nodes.yoloworld_vision import run_yoloworld_vision
from app.pipeline.nodes.violence_video import run_violence_model
from app.pipeline.nodes.audio_asr import run_audio_asr
from app.pipeline.nodes.ocr import run_ocr
from app.pipeline.nodes.text_moderation import run_text_moderation
from app.pipeline.nodes.llm_report import generate_llm_report

__all__ = [
    # Core pipeline nodes (stable graph)
    "ingest_video",
    "segment_video",
    "run_pipeline_node",  # Orchestrates detector stages
    "generate_llm_report",
    
    # Individual detector nodes (used by stage plugins)
    "run_yolo26_vision",
    "run_yoloworld_vision",
    "run_violence_model",
    "run_audio_asr",
    "run_ocr",
    "run_text_moderation",
]
