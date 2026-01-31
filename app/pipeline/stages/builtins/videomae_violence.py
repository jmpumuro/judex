"""
VideoMAE Violence Detection stage plugin.

This stage runs VideoMAE-based violence classification on candidate windows
or full segments if no windows are available. It runs parallel to X-CLIP
as a specialist violence detector.

VIDEO ONLY: Requires temporal context (video transformer needs multiple frames).

Industry Standard:
- Uses candidate windows from window mining stage (or falls back to segments)
- Produces per-window violence scores with labels
- Configurable max windows and threshold profiles
"""
import asyncio
from typing import Any, Dict, List, Set

from app.pipeline.stages.base import StagePlugin, StageSpec, StageImpact, STAGE_IMPACT_DEFAULTS, VIDEO_ONLY, MediaType
from app.core.logging import get_logger
from app.utils.progress import save_stage_output, format_stage_output

logger = get_logger("stages.videomae")

# Register default impact
STAGE_IMPACT_DEFAULTS["videomae_violence"] = StageImpact.SUPPORTING


class VideoMAEViolenceStagePlugin(StagePlugin):
    """
    VideoMAE-based violence detection stage.
    
    This stage complements X-CLIP by using a video transformer model
    specialized in action recognition. It analyzes candidate windows
    to detect violence-related actions.
    
    VIDEO ONLY: VideoMAE requires temporal context (16+ frames).
    """
    
    @property
    def stage_type(self) -> str:
        return "videomae_violence"
    
    @property
    def display_name(self) -> str:
        return "VideoMAE Violence"
    
    @property
    def supported_media_types(self) -> Set[MediaType]:
        """VideoMAE requires video (temporal context)."""
        return VIDEO_ONLY
    
    @property
    def input_keys(self) -> Set[str]:
        return {"video_path", "candidate_windows", "segments"}
    
    @property
    def output_keys(self) -> Set[str]:
        return {"videomae_scores"}
    
    async def run(
        self,
        state: Dict[str, Any],
        spec: StageSpec
    ) -> Dict[str, Any]:
        """Execute VideoMAE violence detection."""
        logger.info(f"Running VideoMAE violence stage (id={spec.id})")
        
        video_id = state.get("video_id")
        video_path = state.get("video_path")
        candidate_windows = state.get("candidate_windows", [])
        segments = state.get("segments", [])
        
        # Get configuration
        config = spec.config or {}
        max_windows = config.get("max_windows", 10)
        threshold_profile = config.get("threshold_profile", "balanced")
        use_segments_fallback = config.get("use_segments_fallback", True)
        
        # Determine windows to analyze
        windows_to_analyze = []
        source = "candidate_windows"
        
        if candidate_windows:
            # Use candidate windows from mining stage
            windows_to_analyze = candidate_windows[:max_windows]
            source = "candidate_windows"
            logger.info(f"Using {len(windows_to_analyze)} candidate windows")
        elif use_segments_fallback and segments:
            # Fall back to segments
            windows_to_analyze = [
                {
                    "start_time": seg.get("start_time", 0),
                    "end_time": seg.get("end_time", 0),
                }
                for seg in segments[:max_windows]
            ]
            source = "segments"
            logger.info(f"Falling back to {len(windows_to_analyze)} segments")
        else:
            logger.warning("No windows or segments available for VideoMAE analysis")
            
            if video_id:
                save_stage_output(video_id, "videomae_violence", format_stage_output(
                    "videomae_violence",
                    status="skipped",
                    reason="No windows or segments available",
                    scores=[],
                ))
            
            return {"videomae_scores": []}
        
        # Run in thread pool
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            self._run_videomae,
            video_path,
            windows_to_analyze,
            max_windows,
        )
        
        # Convert to dicts
        scores_dicts = [r.to_dict() for r in results]
        
        # Compute summary stats
        violence_scores = [r.violence_score for r in results]
        max_violence = max(violence_scores) if violence_scores else 0.0
        avg_violence = sum(violence_scores) / len(violence_scores) if violence_scores else 0.0
        high_violence_windows = sum(1 for s in violence_scores if s >= 0.5)
        
        # Save stage output
        if video_id:
            save_stage_output(video_id, "videomae_violence", format_stage_output(
                "videomae_violence",
                windows_analyzed=len(results),
                source=source,
                max_violence_score=round(max_violence, 3),
                avg_violence_score=round(avg_violence, 3),
                high_violence_windows=high_violence_windows,
                threshold_profile=threshold_profile,
                scores=scores_dicts[:5],  # Preview
            ))
        
        logger.info(
            f"VideoMAE analyzed {len(results)} windows: "
            f"max={max_violence:.3f}, avg={avg_violence:.3f}, high={high_violence_windows}"
        )
        
        return {"videomae_scores": scores_dicts}
    
    def _run_videomae(
        self,
        video_path: str,
        windows: List[Dict],
        max_windows: int,
    ) -> List:
        """Run VideoMAE model on windows."""
        try:
            from app.models.videomae_violence import get_videomae_model
            
            model = get_videomae_model()
            results = model.classify_windows(video_path, windows, max_windows)
            
            return results
            
        except ImportError as e:
            logger.error(f"VideoMAE model import failed: {e}")
            return []
        except Exception as e:
            logger.error(f"VideoMAE inference failed: {e}")
            return []
