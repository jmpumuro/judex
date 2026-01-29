"""
OCR stage plugin - wraps the existing ocr node.
"""
import asyncio
from typing import Any, Dict, Set

from app.pipeline.stages.base import StagePlugin, StageSpec
from app.core.logging import get_logger

logger = get_logger("stages.ocr")


class OcrStagePlugin(StagePlugin):
    """
    OCR text extraction stage.
    
    Wraps the existing run_ocr node function.
    The node handles text extraction and stage output saving.
    """
    
    @property
    def stage_type(self) -> str:
        return "ocr"
    
    @property
    def display_name(self) -> str:
        return "Text Recognition"
    
    @property
    def input_keys(self) -> Set[str]:
        return {"sampled_frames"}
    
    @property
    def output_keys(self) -> Set[str]:
        return {"ocr_results"}
    
    async def run(
        self, 
        state: Dict[str, Any], 
        spec: StageSpec
    ) -> Dict[str, Any]:
        """Execute OCR by calling the existing node."""
        from app.pipeline.nodes.ocr import run_ocr
        
        logger.info(f"Running OCR stage (id={spec.id})")
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, run_ocr, state)
