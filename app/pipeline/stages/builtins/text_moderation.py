"""
Text moderation stage plugin - wraps the existing text_moderation node.
"""
import asyncio
from typing import Any, Dict, Set

from app.pipeline.stages.base import StagePlugin, StageSpec
from app.core.logging import get_logger

logger = get_logger("stages.text_moderation")


class TextModerationStagePlugin(StagePlugin):
    """
    Text moderation stage for transcript and OCR text.
    
    Wraps the existing run_text_moderation node function.
    The node handles moderation and stage output saving.
    """
    
    @property
    def stage_type(self) -> str:
        return "text_moderation"
    
    @property
    def display_name(self) -> str:
        return "Content Filter"
    
    @property
    def input_keys(self) -> Set[str]:
        return {"transcript", "ocr_results"}
    
    @property
    def output_keys(self) -> Set[str]:
        return {"transcript_moderation", "ocr_moderation"}
    
    async def run(
        self, 
        state: Dict[str, Any], 
        spec: StageSpec
    ) -> Dict[str, Any]:
        """Execute text moderation by calling the existing node."""
        from app.pipeline.nodes.text_moderation import run_text_moderation
        
        logger.info(f"Running text moderation stage (id={spec.id})")
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, run_text_moderation, state)
