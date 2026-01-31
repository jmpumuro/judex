"""
NSFW Visual Detection stage plugin.

Industry Standard: Dedicated visual NSFW classification to provide visual
confirmation for sexual content scoring. This separates:
- Profanity (text-based) → profanity_score
- Sexual content (visual) → requires nsfw_visual + optional text confirmation

Key principle: Profanity alone ≠ Sexual content
"""
import asyncio
from typing import Any, Dict, List, Set

from app.pipeline.stages.base import StagePlugin, StageSpec, StageImpact, STAGE_IMPACT_DEFAULTS
from app.core.logging import get_logger
from app.utils.progress import save_stage_output, format_stage_output

logger = get_logger("stages.nsfw")

# Register default impact
STAGE_IMPACT_DEFAULTS["nsfw_detection"] = StageImpact.SUPPORTING


class NSFWDetectionStagePlugin(StagePlugin):
    """
    NSFW visual content detection stage.
    
    Analyzes sampled frames using a dedicated NSFW classifier to provide
    visual confirmation for sexual content scoring. This helps reduce
    false positives from profanity-only text.
    """
    
    @property
    def stage_type(self) -> str:
        return "nsfw_detection"
    
    @property
    def display_name(self) -> str:
        return "NSFW Visual Detection"
    
    @property
    def input_keys(self) -> Set[str]:
        return {"sampled_frames"}
    
    @property
    def output_keys(self) -> Set[str]:
        return {"nsfw_results"}
    
    async def run(
        self,
        state: Dict[str, Any],
        spec: StageSpec
    ) -> Dict[str, Any]:
        """Execute NSFW visual detection."""
        logger.info(f"Running NSFW detection stage (id={spec.id})")
        
        video_id = state.get("video_id")
        sampled_frames = state.get("sampled_frames", [])
        
        if not sampled_frames:
            logger.warning("No sampled frames available for NSFW detection")
            
            if video_id:
                save_stage_output(video_id, "nsfw_detection", format_stage_output(
                    "nsfw_detection",
                    status="skipped",
                    reason="No frames available",
                    nsfw_results={},
                ))
            
            return {"nsfw_results": {}}
        
        # Get configuration
        config = spec.config or {}
        sample_rate = config.get("sample_rate", 2)  # Analyze every 2nd frame by default
        
        # Run in thread pool
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            self._run_nsfw_detection,
            sampled_frames,
            sample_rate,
        )
        
        # Save stage output
        if video_id:
            save_stage_output(video_id, "nsfw_detection", format_stage_output(
                "nsfw_detection",
                analyzed_frames=results.get("analyzed_frames", 0),
                nsfw_frames=results.get("nsfw_frames", 0),
                max_nsfw_score=results.get("max_nsfw_score", 0),
                avg_nsfw_score=results.get("avg_nsfw_score", 0),
                is_nsfw=results.get("is_nsfw", False),
                detections=results.get("detections", [])[:5],  # Preview
            ))
        
        logger.info(
            f"NSFW detection complete: {results.get('analyzed_frames', 0)} frames analyzed, "
            f"{results.get('nsfw_frames', 0)} NSFW, max={results.get('max_nsfw_score', 0):.3f}"
        )
        
        return {"nsfw_results": results}
    
    def _run_nsfw_detection(
        self,
        sampled_frames: List[Dict],
        sample_rate: int,
    ) -> Dict[str, Any]:
        """Run NSFW detection on frames."""
        try:
            from app.models.nsfw_detector import get_nsfw_detector
            import cv2
            import numpy as np
            
            detector = get_nsfw_detector()
            
            # Extract frame data and timestamps
            frames = []
            timestamps = []
            
            for frame_info in sampled_frames:
                frame_path = frame_info.get("path")
                timestamp = frame_info.get("timestamp", 0)
                
                if frame_path:
                    try:
                        frame = cv2.imread(frame_path)
                        if frame is not None:
                            frames.append(frame)
                            timestamps.append(timestamp)
                    except Exception as e:
                        logger.warning(f"Failed to load frame {frame_path}: {e}")
            
            if not frames:
                logger.warning("No valid frames to analyze")
                return {
                    "analyzed_frames": 0,
                    "nsfw_frames": 0,
                    "max_nsfw_score": 0.0,
                    "avg_nsfw_score": 0.0,
                    "is_nsfw": False,
                    "detections": [],
                }
            
            # Run detection
            results = detector.classify_frames(
                frames,
                timestamps=timestamps,
                sample_rate=sample_rate,
            )
            
            return results
            
        except ImportError as e:
            logger.error(f"NSFW detector import failed: {e}")
            return {
                "analyzed_frames": 0,
                "nsfw_frames": 0,
                "max_nsfw_score": 0.0,
                "avg_nsfw_score": 0.0,
                "is_nsfw": False,
                "detections": [],
                "error": str(e),
            }
        except Exception as e:
            logger.error(f"NSFW detection failed: {e}")
            return {
                "analyzed_frames": 0,
                "nsfw_frames": 0,
                "max_nsfw_score": 0.0,
                "avg_nsfw_score": 0.0,
                "is_nsfw": False,
                "detections": [],
                "error": str(e),
            }
