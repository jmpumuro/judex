"""
Violence detection stage plugin - wraps the existing violence_video node (X-CLIP).

VIDEO ONLY: Requires temporal context (multiple frames) for action recognition.
"""
import asyncio
from typing import Any, Dict, Set

from app.pipeline.stages.base import StagePlugin, StageSpec, VIDEO_ONLY, MediaType
from app.core.logging import get_logger

logger = get_logger("stages.violence")


class ViolenceStagePlugin(StagePlugin):
    """
    Violence detection stage using X-CLIP.
    
    Wraps the existing run_violence_model node function.
    The node handles detection and stage output saving.
    
    VIDEO ONLY: X-CLIP requires 16+ frames for temporal action recognition.
    """
    
    @property
    def stage_type(self) -> str:
        return "xclip"  # Matches detector ID in routing
    
    @property
    def display_name(self) -> str:
        return "Action Recognition"
    
    @property
    def supported_media_types(self) -> Set[MediaType]:
        """X-CLIP requires video (temporal context)."""
        return VIDEO_ONLY
    
    @property
    def input_keys(self) -> Set[str]:
        return {"video_path", "segments"}
    
    @property
    def output_keys(self) -> Set[str]:
        return {"violence_segments"}
    
    async def run(
        self, 
        state: Dict[str, Any], 
        spec: StageSpec
    ) -> Dict[str, Any]:
        """Execute violence detection by calling the existing node."""
        from app.pipeline.nodes.violence_video import run_violence_model
        
        logger.info(f"Running violence/X-CLIP stage (id={spec.id})")
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, run_violence_model, state)
