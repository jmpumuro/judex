"""
Whisper ASR stage plugin - wraps the existing audio_asr node.
"""
import asyncio
from typing import Any, Dict, Set

from app.pipeline.stages.base import StagePlugin, StageSpec
from app.core.logging import get_logger

logger = get_logger("stages.whisper")


class WhisperStagePlugin(StagePlugin):
    """
    Audio transcription stage using Whisper.
    
    Wraps the existing run_audio_asr node function.
    The node handles transcription and stage output saving.
    """
    
    @property
    def stage_type(self) -> str:
        return "whisper"  # Matches detector ID in routing
    
    @property
    def display_name(self) -> str:
        return "Speech Analysis"
    
    @property
    def input_keys(self) -> Set[str]:
        return {"video_path", "work_dir", "has_audio"}
    
    @property
    def output_keys(self) -> Set[str]:
        return {"transcript", "audio_path"}
    
    async def run(
        self, 
        state: Dict[str, Any], 
        spec: StageSpec
    ) -> Dict[str, Any]:
        """Execute Whisper ASR by calling the existing node."""
        from app.pipeline.nodes.audio_asr import run_audio_asr
        
        logger.info(f"Running Whisper ASR stage (id={spec.id})")
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, run_audio_asr, state)
