"""
Pipeline runner for dynamic stage execution.

The PipelineRunner executes a sequence of stages based on a pipeline definition.
This is the core orchestration layer that:
- Resolves stage plugins from the registry
- Executes stages in order
- Manages state updates and progress callbacks
- Handles errors consistently
- Tracks skipped stages explicitly

The runner is called from within a single LangGraph node (run_pipeline),
keeping the LangGraph structure stable while allowing dynamic stage execution.
"""
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from app.pipeline.stages.base import StageSpec, StageStatus, StageImpact
from app.pipeline.stages.registry import get_stage_registry
from app.core.logging import get_logger

logger = get_logger("pipeline.runner")


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
        
        for idx, spec in enumerate(stages):
            # Calculate overall progress
            base_progress = int((idx / total_stages) * 100)
            stage_progress = int(((idx + 1) / total_stages) * 100)
            
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
