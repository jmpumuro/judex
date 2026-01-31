"""
Pipeline runner for dynamic stage execution.

The PipelineRunner executes a sequence of stages based on a pipeline definition.
This is the core orchestration layer that:
- Resolves stage plugins from the registry
- Executes stages in order (or in parallel phases)
- Manages state updates and progress callbacks
- Handles errors consistently
- Tracks skipped stages explicitly
- Respects media type compatibility (video vs image)

Industry Standard Architecture:
- Plugin Pattern: Stages are self-contained plugins with defined interfaces
- Registry Pattern: Dynamic stage discovery and resolution
- Phase-based Execution: Independent stages can run in parallel
- Dependency Declaration: Stages declare inputs/outputs for automatic ordering
- Media Type Awareness: Stages declare supported media types
"""
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum

from app.pipeline.stages.base import StageSpec, StageStatus, StageImpact, MediaType
from app.pipeline.stages.registry import get_stage_registry
from app.core.logging import get_logger

logger = get_logger("pipeline.runner")


# ============================================================================
# Phase Definitions for Parallel Execution
# ============================================================================

class ExecutionPhase(str, Enum):
    """
    Execution phases for stage grouping.
    
    Stages in the same phase can run in parallel if they don't have
    data dependencies. Phases execute sequentially.
    """
    INGEST = "ingest"           # Video ingestion and normalization
    EXTRACT = "extract"         # Frame extraction, segmentation
    PREPROCESS = "preprocess"   # Window mining, quick detection passes
    DETECT = "detect"           # Main detection (can run in parallel)
    ANALYZE = "analyze"         # Text analysis, moderation
    FUSE = "fuse"               # Score fusion and verdict
    REPORT = "report"           # Report generation


# Stage to phase mapping
STAGE_PHASES: Dict[str, ExecutionPhase] = {
    # Ingest phase
    "ingest": ExecutionPhase.INGEST,
    
    # Extract phase
    "segment": ExecutionPhase.EXTRACT,
    
    # Preprocess phase (quick passes for window mining)
    "yolo26": ExecutionPhase.PREPROCESS,
    "window_mining": ExecutionPhase.PREPROCESS,
    
    # Detect phase (parallel detection)
    "yoloworld": ExecutionPhase.DETECT,
    "xclip": ExecutionPhase.DETECT,
    "videomae_violence": ExecutionPhase.DETECT,
    "pose_heuristics": ExecutionPhase.DETECT,
    "whisper": ExecutionPhase.DETECT,
    "ocr": ExecutionPhase.DETECT,
    
    # Analyze phase
    "text_moderation": ExecutionPhase.ANALYZE,
    
    # Fuse phase
    "policy_fusion": ExecutionPhase.FUSE,
    
    # Report phase
    "report": ExecutionPhase.REPORT,
}


def get_stage_phase(stage_type: str) -> ExecutionPhase:
    """Get the execution phase for a stage type."""
    return STAGE_PHASES.get(stage_type, ExecutionPhase.DETECT)


@dataclass
class StageRun:
    """Record of a stage execution."""
    stage_id: str
    stage_type: str
    status: StageStatus
    started_at: float
    ended_at: Optional[float] = None
    duration_ms: float = 0.0
    outputs: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    skip_reason: Optional[str] = None  # If skipped, why
    impact: str = "supporting"  # Stage impact level
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "stage_type": self.stage_type,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "skip_reason": self.skip_reason,
            "impact": self.impact,
        }


@dataclass
class PipelineRunResult:
    """Result of running the full pipeline."""
    stages_run: List[StageRun]
    final_state: Dict[str, Any]
    total_duration_ms: float
    success: bool
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "stages_run": [s.to_dict() for s in self.stages_run],
            "total_duration_ms": self.total_duration_ms,
            "success": self.success,
            "errors": self.errors,
        }


class PipelineRunner:
    """
    Executes a pipeline of stages dynamically.
    
    The runner:
    1. Takes a list of StageSpec (stage definitions)
    2. Resolves each stage from the registry
    3. Executes stages sequentially
    4. Calls progress_callback for UI updates
    5. Merges stage outputs into state
    6. Handles errors (append to state["errors"], optionally abort)
    """
    
    def __init__(
        self,
        progress_callback: Optional[Callable] = None,
        video_id: Optional[str] = None,
        stop_on_error: bool = False,
    ):
        """
        Initialize the runner.
        
        Args:
            progress_callback: Async callback(stage, message, progress) for UI updates
            video_id: Video ID for stage output persistence
            stop_on_error: If True, abort pipeline on first error
        """
        self.progress_callback = progress_callback
        self.video_id = video_id
        self.stop_on_error = stop_on_error
        self.registry = get_stage_registry()
    
    async def run(
        self,
        stages: List[StageSpec],
        initial_state: Dict[str, Any],
    ) -> PipelineRunResult:
        """
        Execute the pipeline.
        
        Args:
            stages: List of stage specifications to execute
            initial_state: Initial pipeline state
            
        Returns:
            PipelineRunResult with execution details
        """
        state = dict(initial_state)
        stage_runs: List[StageRun] = []
        errors: List[str] = []
        
        pipeline_start = time.time()
        total_stages = len(stages)
        
        logger.info(f"Starting pipeline with {total_stages} stages")
        
        # Get media type from state (default to video for backward compatibility)
        media_type = state.get("media_type", "video")
        
        for idx, spec in enumerate(stages):
            # Calculate overall progress
            base_progress = int((idx / total_stages) * 100)
            stage_progress = int(((idx + 1) / total_stages) * 100)
            
            # Check media type compatibility first
            try:
                plugin = self.registry.get(spec.type)
                if not plugin.supports_media_type(media_type):
                    skip_reason = f"Not supported for {media_type} (requires video)"
                    logger.info(f"Skipping stage {spec.id}: {skip_reason}")
                    
                    skipped_run = StageRun(
                        stage_id=spec.id,
                        stage_type=spec.type,
                        status=StageStatus.SKIPPED,
                        started_at=time.time(),
                        ended_at=time.time(),
                        duration_ms=0.0,
                        skip_reason=skip_reason,
                        impact=spec.impact.value if isinstance(spec.impact, StageImpact) else spec.impact,
                    )
                    stage_runs.append(skipped_run)
                    
                    # Save skipped stage output
                    video_id = state.get("video_id")
                    if video_id:
                        from app.utils.progress import save_stage_output
                        save_stage_output(video_id, spec.id, {
                            "status": "skipped",
                            "skip_reason": skip_reason,
                            "media_type": media_type,
                            "impact": spec.impact.value if isinstance(spec.impact, StageImpact) else spec.impact,
                        })
                    continue
            except KeyError:
                # Plugin not found - will be handled later
                pass
            
            # Handle disabled stages explicitly - record them as SKIPPED
            if not spec.enabled:
                skip_reason = spec.skip_reason or "Disabled by configuration"
                logger.info(f"Skipping disabled stage: {spec.id} ({skip_reason})")
                
                skipped_run = StageRun(
                    stage_id=spec.id,
                    stage_type=spec.type,
                    status=StageStatus.SKIPPED,
                    started_at=time.time(),
                    ended_at=time.time(),
                    duration_ms=0.0,
                    skip_reason=skip_reason,
                    impact=spec.impact.value if isinstance(spec.impact, StageImpact) else spec.impact,
                )
                stage_runs.append(skipped_run)
                
                # Save skipped stage output for UI visibility
                video_id = state.get("video_id")
                if video_id:
                    from app.utils.progress import save_stage_output
                    save_stage_output(video_id, spec.id, {
                        "status": "skipped",
                        "skip_reason": skip_reason,
                        "impact": spec.impact.value if isinstance(spec.impact, StageImpact) else spec.impact,
                    })
                
                continue
            
            run = StageRun(
                stage_id=spec.id,
                stage_type=spec.type,
                status=StageStatus.RUNNING,
                started_at=time.time(),
                impact=spec.impact.value if isinstance(spec.impact, StageImpact) else spec.impact,
            )
            
            try:
                # Resolve plugin
                plugin = self.registry.get(spec.type)
                
                # Send progress: stage starting
                await self._send_progress(
                    spec.type, 
                    f"Starting {plugin.display_name}...",
                    base_progress
                )
                
                # Update state tracking
                state["current_stage"] = spec.type
                state["stage_progress"] = 0
                
                # Inject progress_callback for plugins (not saved in state for checkpoint)
                # This is a runtime-only value
                state["progress_callback"] = self.progress_callback
                
                # Validate state
                validation_error = plugin.validate_state(state, spec)
                if validation_error:
                    raise ValueError(f"Stage validation failed: {validation_error}")
                
                # Execute stage
                logger.info(f"Executing stage: {spec.id} ({spec.type})")
                updated_state = await plugin.run(state, spec)
                
                # Merge outputs into state
                if isinstance(updated_state, dict):
                    state.update(updated_state)
                
                # Get stage output for tracking
                stage_output = plugin.get_stage_output(state)
                run.outputs = stage_output
                
                # For external stages, save output to database 
                # (builtin stages save their own outputs via save_stage_output)
                video_id = state.get("video_id")
                if video_id and stage_output:
                    # Industry Standard: Use interface property instead of isinstance
                    # This follows the Template Method pattern - plugins declare their type
                    if plugin.is_external:
                        from app.utils.progress import save_stage_output, format_stage_output
                        logger.info(f"Saving external stage output for {spec.id}: {list(stage_output.keys())}")
                        
                        # Format and save external stage output
                        formatted_output = format_stage_output(
                            spec.id,
                            is_external=True,
                            endpoint_called=True,
                            **{k: v for k, v in stage_output.items() if not k.startswith('_')}
                        )
                        save_stage_output(video_id, spec.id, formatted_output)
                        logger.info(f"✓ Saved external stage output for {spec.id}")
                
                # Mark complete
                run.status = StageStatus.COMPLETED
                run.ended_at = time.time()
                run.duration_ms = (run.ended_at - run.started_at) * 1000
                
                logger.info(f"Stage {spec.id} completed in {run.duration_ms:.0f}ms")
                
                # Send progress: stage complete
                await self._send_progress(
                    spec.type,
                    f"{plugin.display_name} complete",
                    stage_progress
                )
                
            except KeyError as e:
                # Unknown stage type
                error_msg = f"Unknown stage type '{spec.type}': {e}"
                logger.error(error_msg)
                run.status = StageStatus.FAILED
                run.error = error_msg
                run.ended_at = time.time()
                run.duration_ms = (run.ended_at - run.started_at) * 1000
                errors.append(error_msg)
                
                if self.stop_on_error:
                    break
                    
            except Exception as e:
                error_msg = f"Stage {spec.id} failed: {str(e)}"
                logger.error(error_msg, exc_info=True)
                run.status = StageStatus.FAILED
                run.error = str(e)
                run.ended_at = time.time()
                run.duration_ms = (run.ended_at - run.started_at) * 1000
                errors.append(error_msg)
                
                # Append to state errors
                state.setdefault("errors", []).append(error_msg)
                
                if self.stop_on_error:
                    break
            
            finally:
                stage_runs.append(run)
        
        # Calculate total duration
        total_duration_ms = (time.time() - pipeline_start) * 1000
        
        # Store stage runs in state for later reference
        state["stage_runs"] = [r.to_dict() for r in stage_runs]
        
        # Remove non-serializable items before returning (for checkpointing)
        state.pop("progress_callback", None)
        
        logger.info(
            f"Pipeline complete: {len(stage_runs)} stages, "
            f"{sum(1 for r in stage_runs if r.status == StageStatus.COMPLETED)} succeeded, "
            f"{len(errors)} errors, "
            f"total time: {total_duration_ms:.0f}ms"
        )
        
        return PipelineRunResult(
            stages_run=stage_runs,
            final_state=state,
            total_duration_ms=total_duration_ms,
            success=len(errors) == 0,
            errors=errors,
        )
    
    async def run_parallel(
        self,
        stages: List[StageSpec],
        initial_state: Dict[str, Any],
        max_parallel: int = 3,
    ) -> PipelineRunResult:
        """
        Execute the pipeline with phase-based parallel execution.
        
        Industry Standard: Stages are grouped by phase. Stages within the same
        phase run in parallel (up to max_parallel), phases execute sequentially.
        
        This provides:
        - Faster execution for independent stages (e.g., xclip + videomae + pose)
        - Deterministic ordering via phase boundaries
        - Resource management via max_parallel limit
        
        Args:
            stages: List of stage specifications to execute
            initial_state: Initial pipeline state
            max_parallel: Max concurrent stages per phase (default 3)
            
        Returns:
            PipelineRunResult with execution details
        """
        state = dict(initial_state)
        all_stage_runs: List[StageRun] = []
        errors: List[str] = []
        
        pipeline_start = time.time()
        
        # Group stages by phase
        phase_groups: Dict[ExecutionPhase, List[StageSpec]] = {}
        for spec in stages:
            phase = get_stage_phase(spec.type)
            if phase not in phase_groups:
                phase_groups[phase] = []
            phase_groups[phase].append(spec)
        
        # Sort phases by enum order
        sorted_phases = sorted(
            phase_groups.keys(),
            key=lambda p: list(ExecutionPhase).index(p)
        )
        
        logger.info(
            f"Starting parallel pipeline: {len(stages)} stages in "
            f"{len(sorted_phases)} phases, max_parallel={max_parallel}"
        )
        
        total_completed = 0
        total_stages = len(stages)
        
        # Get media type for compatibility checks
        media_type = state.get("media_type", "video")
        
        for phase in sorted_phases:
            phase_stages = phase_groups[phase]
            logger.info(f"Phase {phase.value}: {len(phase_stages)} stages")
            
            # Handle disabled and incompatible stages first (no async needed)
            enabled_stages = []
            for spec in phase_stages:
                # Check media type compatibility
                try:
                    plugin = self.registry.get(spec.type)
                    if not plugin.supports_media_type(media_type):
                        skip_reason = f"Not supported for {media_type} (requires video)"
                        skipped_run = StageRun(
                            stage_id=spec.id,
                            stage_type=spec.type,
                            status=StageStatus.SKIPPED,
                            started_at=time.time(),
                            ended_at=time.time(),
                            duration_ms=0.0,
                            skip_reason=skip_reason,
                            impact=spec.impact.value if isinstance(spec.impact, StageImpact) else spec.impact,
                        )
                        all_stage_runs.append(skipped_run)
                        total_completed += 1
                        continue
                except KeyError:
                    pass  # Will fail later with proper error
                
                # Check if disabled
                if not spec.enabled:
                    skip_reason = spec.skip_reason or "Disabled by configuration"
                    skipped_run = StageRun(
                        stage_id=spec.id,
                        stage_type=spec.type,
                        status=StageStatus.SKIPPED,
                        started_at=time.time(),
                        ended_at=time.time(),
                        duration_ms=0.0,
                        skip_reason=skip_reason,
                        impact=spec.impact.value if isinstance(spec.impact, StageImpact) else spec.impact,
                    )
                    all_stage_runs.append(skipped_run)
                    total_completed += 1
                else:
                    enabled_stages.append(spec)
            
            if not enabled_stages:
                continue
            
            # Run enabled stages in parallel batches
            for batch_start in range(0, len(enabled_stages), max_parallel):
                batch = enabled_stages[batch_start:batch_start + max_parallel]
                
                # Create tasks for parallel execution
                tasks = [
                    self._run_single_stage(spec, state, total_completed, total_stages)
                    for spec in batch
                ]
                
                # Execute batch in parallel
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                for spec, result in zip(batch, batch_results):
                    if isinstance(result, Exception):
                        error_msg = f"Stage {spec.id} failed: {str(result)}"
                        logger.error(error_msg)
                        
                        failed_run = StageRun(
                            stage_id=spec.id,
                            stage_type=spec.type,
                            status=StageStatus.FAILED,
                            started_at=time.time(),
                            error=str(result),
                            impact=spec.impact.value if isinstance(spec.impact, StageImpact) else spec.impact,
                        )
                        all_stage_runs.append(failed_run)
                        errors.append(error_msg)
                        state.setdefault("errors", []).append(error_msg)
                        
                        if self.stop_on_error:
                            break
                    else:
                        stage_run, updated_state = result
                        all_stage_runs.append(stage_run)
                        # Merge state updates (parallel stages may write different keys)
                        state.update(updated_state)
                    
                    total_completed += 1
                
                if self.stop_on_error and errors:
                    break
            
            if self.stop_on_error and errors:
                break
        
        # Calculate total duration
        total_duration_ms = (time.time() - pipeline_start) * 1000
        
        # Store stage runs in state
        state["stage_runs"] = [r.to_dict() for r in all_stage_runs]
        state.pop("progress_callback", None)
        
        completed_count = sum(1 for r in all_stage_runs if r.status == StageStatus.COMPLETED)
        logger.info(
            f"Parallel pipeline complete: {len(all_stage_runs)} stages, "
            f"{completed_count} succeeded, {len(errors)} errors, "
            f"total time: {total_duration_ms:.0f}ms"
        )
        
        return PipelineRunResult(
            stages_run=all_stage_runs,
            final_state=state,
            total_duration_ms=total_duration_ms,
            success=len(errors) == 0,
            errors=errors,
        )
    
    async def _run_single_stage(
        self,
        spec: StageSpec,
        state: Dict[str, Any],
        completed_count: int,
        total_stages: int,
    ) -> tuple:
        """
        Run a single stage and return the result.
        
        Used by run_parallel for concurrent execution.
        
        Returns:
            Tuple of (StageRun, updated_state_dict)
        """
        run = StageRun(
            stage_id=spec.id,
            stage_type=spec.type,
            status=StageStatus.RUNNING,
            started_at=time.time(),
            impact=spec.impact.value if isinstance(spec.impact, StageImpact) else spec.impact,
        )
        
        # Copy state to avoid race conditions
        local_state = dict(state)
        local_state["progress_callback"] = self.progress_callback
        
        base_progress = int((completed_count / total_stages) * 100)
        
        try:
            plugin = self.registry.get(spec.type)
            
            await self._send_progress(
                spec.type,
                f"Starting {plugin.display_name}...",
                base_progress
            )
            
            local_state["current_stage"] = spec.type
            local_state["stage_progress"] = 0
            
            # Validate and execute
            validation_error = plugin.validate_state(local_state, spec)
            if validation_error:
                raise ValueError(f"Stage validation failed: {validation_error}")
            
            updated_state = await plugin.run(local_state, spec)
            
            if isinstance(updated_state, dict):
                local_state.update(updated_state)
            
            # Get stage output
            stage_output = plugin.get_stage_output(local_state)
            run.outputs = stage_output
            
            # Save external stage outputs
            video_id = local_state.get("video_id")
            if video_id and stage_output and plugin.is_external:
                from app.utils.progress import save_stage_output, format_stage_output
                formatted_output = format_stage_output(
                    spec.id,
                    is_external=True,
                    endpoint_called=True,
                    **{k: v for k, v in stage_output.items() if not k.startswith('_')}
                )
                save_stage_output(video_id, spec.id, formatted_output)
            
            run.status = StageStatus.COMPLETED
            run.ended_at = time.time()
            run.duration_ms = (run.ended_at - run.started_at) * 1000
            
            logger.info(f"Stage {spec.id} completed in {run.duration_ms:.0f}ms")
            
            await self._send_progress(
                spec.type,
                f"{plugin.display_name} complete",
                base_progress + int(100 / total_stages)
            )
            
            # Remove non-serializable items
            local_state.pop("progress_callback", None)
            
            return (run, local_state)
            
        except Exception as e:
            run.status = StageStatus.FAILED
            run.error = str(e)
            run.ended_at = time.time()
            run.duration_ms = (run.ended_at - run.started_at) * 1000
            raise
    
    async def _send_progress(
        self,
        stage: str,
        message: str,
        progress: int,
    ) -> None:
        """Send progress update via callback."""
        if not self.progress_callback:
            return
        
        try:
            result = self.progress_callback(stage, message, progress)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.warning(f"Progress callback failed: {e}")


def load_stage_settings() -> Dict[str, Dict[str, Any]]:
    """Load stage settings from database for all stages."""
    settings_map = {}
    try:
        from app.db.connection import get_db_session
        from app.db.models import StageSettings
        
        with get_db_session() as session:
            all_settings = session.query(StageSettings).all()
            for s in all_settings:
                settings_map[s.id] = {
                    "enabled": s.enabled,
                    "impact": s.impact,
                    "required": s.required,
                }
    except Exception as e:
        logger.warning(f"Could not load stage settings: {e}")
    
    return settings_map


def build_pipeline_from_detectors(detector_ids: List[str]) -> List[StageSpec]:
    """
    Build a pipeline definition from a list of detector IDs.
    
    This is the bridge between the existing routing logic
    (which returns detector IDs) and the new stage system.
    
    Args:
        detector_ids: List of detector IDs (e.g., ["yolo26", "xclip", "whisper"])
        
    Returns:
        List of StageSpec objects
    """
    # Load settings to apply enable/disable state
    settings_map = load_stage_settings()
    
    stages = []
    for detector_id in detector_ids:
        settings = settings_map.get(detector_id, {})
        enabled = settings.get("enabled", True)
        impact_str = settings.get("impact", "supporting")
        
        # Convert impact string to enum
        try:
            impact = StageImpact(impact_str)
        except ValueError:
            impact = StageImpact.SUPPORTING
        
        stage = StageSpec(
            type=detector_id,
            id=detector_id,
            enabled=enabled,
            impact=impact,
            required=settings.get("required", False),
            skip_reason="Disabled by user" if not enabled else None,
        )
        stages.append(stage)
    return stages


def build_pipeline_from_criteria(criteria) -> List[StageSpec]:
    """
    Build a pipeline definition from EvaluationCriteria.
    
    If criteria has an explicit pipeline definition, use it.
    Otherwise, use auto-routing to determine stages.
    
    External stages (YAML-defined) are automatically appended after
    the auto-routed stages if they are enabled.
    
    Stage enable/disable state is loaded from database.
    
    Args:
        criteria: EvaluationCriteria object
        
    Returns:
        List of StageSpec objects
    """
    # Load settings to apply enable/disable state
    settings_map = load_stage_settings()
    
    # Check for explicit pipeline definition
    if hasattr(criteria, 'pipeline') and criteria.pipeline:
        # criteria.pipeline is a list of stage definitions
        stages = []
        for stage_def in criteria.pipeline:
            stage_type = stage_def.get("type")
            settings = settings_map.get(stage_type, {})
            enabled = settings.get("enabled", stage_def.get("enabled", True))
            
            # Convert impact string to enum
            impact_str = settings.get("impact", "supporting")
            try:
                impact = StageImpact(impact_str)
            except ValueError:
                impact = StageImpact.SUPPORTING
            
            stages.append(StageSpec(
                type=stage_type,
                id=stage_def.get("id", stage_type),
                enabled=enabled,
                impact=impact,
                required=settings.get("required", False),
                config=stage_def.get("config", {}),
                skip_reason="Disabled by user" if not enabled else None,
            ))
    else:
        # Fall back to auto-routing
        from app.evaluation.routing import route_criteria_to_detectors
        detector_ids = route_criteria_to_detectors(criteria)
        stages = build_pipeline_from_detectors(detector_ids)
    
    # Log builtin stages before external
    enabled_builtin = [s.type for s in stages if s.enabled]
    disabled_builtin = [s.type for s in stages if not s.enabled]
    logger.info(f"Built {len(stages)} builtin stages: {len(enabled_builtin)} enabled, {len(disabled_builtin)} disabled")
    if disabled_builtin:
        logger.info(f"Disabled stages: {disabled_builtin}")
    
    # Append enabled external stages
    try:
        from app.external_stages import get_external_stage_registry
        ext_registry = get_external_stage_registry()
        
        external_stages = ext_registry.list_stages()
        logger.info(f"Found {len(external_stages)} external stage configs")
        
        for ext_config in external_stages:
            # Check both external config enabled and stage settings enabled
            settings = settings_map.get(ext_config.id, {})
            config_enabled = ext_config.enabled
            settings_enabled = settings.get("enabled", True)
            is_enabled = config_enabled and settings_enabled
            
            logger.info(f"External stage '{ext_config.id}': config={config_enabled}, settings={settings_enabled}, final={is_enabled}")
            
            # Convert impact string to enum
            impact_str = settings.get("impact", "advisory")
            try:
                impact = StageImpact(impact_str)
            except ValueError:
                impact = StageImpact.ADVISORY
            
            # Add external stage to pipeline (even if disabled, for tracking)
            stages.append(StageSpec(
                type=ext_config.id,
                id=ext_config.id,
                enabled=is_enabled,
                impact=impact,
                required=False,  # External stages are never required
                config={},
                skip_reason="Disabled by user" if not is_enabled else None,
            ))
            
            if is_enabled:
                logger.info(f"✓ Added external stage to pipeline: {ext_config.id}")
            else:
                logger.info(f"○ External stage will be skipped: {ext_config.id}")
                
    except Exception as e:
        logger.warning(f"Could not load external stages: {e}", exc_info=True)
    
    enabled_count = sum(1 for s in stages if s.enabled)
    disabled_count = sum(1 for s in stages if not s.enabled)
    logger.info(f"Final pipeline: {len(stages)} stages ({enabled_count} enabled, {disabled_count} disabled)")
    return stages
