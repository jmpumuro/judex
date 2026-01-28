"""
YOLO26 stage plugin - wraps the existing yolo26_vision node.
"""
import asyncio
from typing import Any, Dict, Set

from app.pipeline.stages.base import StagePlugin, StageSpec
from app.core.logging import get_logger

logger = get_logger("stages.yolo26")


class Yolo26StagePlugin(StagePlugin):
    """
    YOLO26 object detection stage.
    
    Wraps the existing run_yolo26_vision node function.
    The node handles detection, labeled video creation, and stage output saving.
    """
    
    @property
    def stage_type(self) -> str:
        return "yolo26"
    
    @property
    def display_name(self) -> str:
        return "YOLO26 Object Detection"
    
    @property
    def input_keys(self) -> Set[str]:
        return {"sampled_frames", "video_path", "work_dir"}
    
    @property
    def output_keys(self) -> Set[str]:
        return {"vision_detections", "labeled_video_path"}
    
    async def run(
        self, 
        state: Dict[str, Any], 
        spec: StageSpec
    ) -> Dict[str, Any]:
        """Execute YOLO26 detection by calling the existing node."""
        from app.pipeline.nodes.yolo26_vision import run_yolo26_vision
        
        logger.info(f"Running YOLO26 stage (id={spec.id})")
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, run_yolo26_vision, state)
