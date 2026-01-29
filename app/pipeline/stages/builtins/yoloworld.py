"""
YOLO-World stage plugin - wraps the existing yoloworld_vision node.
"""
import asyncio
from typing import Any, Dict, Set

from app.pipeline.stages.base import StagePlugin, StageSpec
from app.core.logging import get_logger

logger = get_logger("stages.yoloworld")


class YoloWorldStagePlugin(StagePlugin):
    """
    YOLO-World open-vocabulary detection stage.
    
    Wraps the existing run_yoloworld_vision node function.
    The node handles detection and stage output saving.
    """
    
    @property
    def stage_type(self) -> str:
        return "yoloworld"
    
    @property
    def display_name(self) -> str:
        return "Scene Analysis"
    
    @property
    def input_keys(self) -> Set[str]:
        return {"sampled_frames"}
    
    @property
    def output_keys(self) -> Set[str]:
        return {"yoloworld_detections"}
    
    async def run(
        self, 
        state: Dict[str, Any], 
        spec: StageSpec
    ) -> Dict[str, Any]:
        """Execute YOLO-World detection by calling the existing node."""
        from app.pipeline.nodes.yoloworld_vision import run_yoloworld_vision
        
        logger.info(f"Running YOLO-World stage (id={spec.id})")
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, run_yoloworld_vision, state)
