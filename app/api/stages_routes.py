"""
External Stages API - CRUD operations for pipeline stages.

Endpoints:
- GET /v1/stages - List all available stages (builtin + external)
- POST /v1/stages/{stage_id}/toggle - Enable/disable any stage
- GET /v1/stages/settings - Get stage settings
- GET /v1/stages/external - List external stage configs
- POST /v1/stages/external - Create/update external stage config
- GET /v1/stages/external/{config_id} - Get specific config
- DELETE /v1/stages/external/{config_id} - Delete config
- POST /v1/stages/external/validate - Validate YAML without saving
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.db.connection import get_db_session
from app.db.models import ExternalStageConfig as ExternalStageModel, StageSettings
from app.external_stages import (
    parse_stage_yaml,
    validate_stage_config,
    get_external_stage_registry,
)
from app.external_stages.schema import ValidationError
from app.pipeline.stages.registry import get_stage_registry
from app.pipeline.stages.base import StageImpact, STAGE_IMPACT_DEFAULTS

logger = get_logger("api.stages")

router = APIRouter(prefix="/v1/stages", tags=["stages"])


# =============================================================================
# Pydantic Models
# =============================================================================

class StageInfoDTO(BaseModel):
    """Stage information for UI display."""
    type: str
    display_name: str
    description: Optional[str] = None
    is_external: bool = False
    is_builtin: bool = False
    enabled: bool = True
    impact: str = "supporting"  # critical, supporting, advisory
    required: bool = False  # If true, cannot be disabled
    input_keys: List[str] = []
    output_keys: List[str] = []
    display_color: Optional[str] = None
    icon: Optional[str] = None
    endpoint_url: Optional[str] = None  # Only for external stages
    last_toggled_at: Optional[str] = None
    toggle_reason: Optional[str] = None


class StagesListResponse(BaseModel):
    """Response for listing all stages."""
    stages: List[StageInfoDTO]
    builtin_count: int
    external_count: int


class ExternalConfigDTO(BaseModel):
    """External stage config for API responses."""
    id: str
    name: str
    description: Optional[str] = None
    yaml_content: str
    stage_ids: List[str] = []
    enabled: bool = True
    validated: bool = False
    validation_error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CreateExternalConfigRequest(BaseModel):
    """Request to create/update external stage config."""
    id: str = Field(..., min_length=1, max_length=64, pattern="^[a-z][a-z0-9_]*$")
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    yaml_content: str = Field(..., min_length=10)
    enabled: bool = True


class ValidationRequest(BaseModel):
    """Request to validate YAML without saving."""
    yaml_content: str


class ValidationResponse(BaseModel):
    """Validation result."""
    valid: bool
    error: Optional[str] = None
    stages: List[Dict[str, Any]] = []


# =============================================================================
# Endpoints
# =============================================================================

def get_or_create_stage_settings(session, stage_id: str, is_builtin: bool, display_name: str) -> StageSettings:
    """Get existing stage settings or create with defaults."""
    settings = session.query(StageSettings).filter(StageSettings.id == stage_id).first()
    if not settings:
        # Create with defaults
        default_impact = STAGE_IMPACT_DEFAULTS.get(stage_id, StageImpact.SUPPORTING)
        settings = StageSettings(
            id=stage_id,
            enabled=True,
            impact=default_impact.value,
            required=False,
            display_name=display_name,
            is_builtin=is_builtin,
            is_external=not is_builtin,
        )
        session.add(settings)
        session.commit()
    return settings


@router.get("", response_model=StagesListResponse)
async def list_all_stages():
    """
    List all available pipeline stages (builtin + external).
    
    This is the primary endpoint for UI to discover what stages are available.
    Stage enable/disable state is loaded from the database.
    """
    stages = []
    
    # Get builtin stages from main registry
    registry = get_stage_registry()
    # All builtin detector stage types (including new safety stack)
    builtin_types = {
        "yolo26", "yoloworld", "xclip", "violence", "whisper", "ocr", "text_moderation",
        # New safety stack stages
        "window_mining", "videomae_violence", "pose_heuristics",
        # NSFW visual detection (reduces sexual false positives)
        "nsfw_detection"
    }
    
    with get_db_session() as session:
        # Only add builtin stages from the registry (external stages added separately below)
        for stage_type in registry.list_stages():
            if stage_type not in builtin_types:
                continue  # Skip external stages here, they're added below with proper metadata
            
            try:
                plugin = registry.get(stage_type)
                
                # Get persisted settings
                settings = get_or_create_stage_settings(
                    session, stage_type, is_builtin=True, display_name=plugin.display_name
                )
                
                stages.append(StageInfoDTO(
                    type=stage_type,
                    display_name=plugin.display_name,
                    description="",
                    is_external=False,
                    is_builtin=True,
                    enabled=settings.enabled,
                    impact=settings.impact,
                    required=settings.required,
                    input_keys=list(plugin.input_keys),
                    output_keys=list(plugin.output_keys),
                    last_toggled_at=settings.last_toggled_at.isoformat() if settings.last_toggled_at else None,
                    toggle_reason=settings.toggle_reason,
                ))
            except Exception as e:
                logger.warning(f"Could not get info for stage {stage_type}: {e}")
        
        # Add external stages metadata
        ext_registry = get_external_stage_registry()
        for info in ext_registry.get_stage_info():
            # Check if already added (via main registry sync)
            if not any(s.type == info["type"] for s in stages):
                # Get persisted settings
                settings = get_or_create_stage_settings(
                    session, info["type"], is_builtin=False, display_name=info["display_name"]
                )
                
                stages.append(StageInfoDTO(
                    type=info["type"],
                    display_name=info["display_name"],
                    description=info.get("description", ""),
                    is_external=True,
                    is_builtin=False,
                    enabled=settings.enabled and info.get("enabled", True),  # Both must be enabled
                    impact=settings.impact,
                    required=settings.required,
                    input_keys=info.get("input_keys", []),
                    output_keys=info.get("output_keys", []),
                    display_color=info.get("display_color"),
                    icon=info.get("icon"),
                    endpoint_url=info.get("endpoint_url"),
                    last_toggled_at=settings.last_toggled_at.isoformat() if settings.last_toggled_at else None,
                    toggle_reason=settings.toggle_reason,
                ))
    
    builtin_count = sum(1 for s in stages if s.is_builtin)
    external_count = sum(1 for s in stages if s.is_external)
    
    return StagesListResponse(
        stages=stages,
        builtin_count=builtin_count,
        external_count=external_count,
    )


class ToggleStageRequest(BaseModel):
    """Request to toggle a stage's enabled state."""
    enabled: bool
    reason: Optional[str] = None  # Optional audit reason


class ToggleStageResponse(BaseModel):
    """Response from toggling a stage."""
    stage_id: str
    enabled: bool
    was_enabled: bool
    impact: str
    required: bool
    warning: Optional[str] = None  # Warning if disabling high-impact stage


@router.post("/{stage_id}/toggle", response_model=ToggleStageResponse)
async def toggle_stage(stage_id: str, request: ToggleStageRequest):
    """
    Enable or disable any stage (builtin or external).
    
    - Required stages cannot be disabled
    - Disabling critical/supporting stages generates a warning
    - Changes are persisted and auditable
    """
    with get_db_session() as session:
        # Get or create settings
        settings = session.query(StageSettings).filter(StageSettings.id == stage_id).first()
        
        if not settings:
            # Check if this is a valid stage
            registry = get_stage_registry()
            ext_registry = get_external_stage_registry()
            
            is_builtin = registry.has(stage_id)
            is_external = ext_registry.has_config(stage_id)
            
            if not is_builtin and not is_external:
                raise HTTPException(404, f"Stage '{stage_id}' not found")
            
            # Create settings
            default_impact = STAGE_IMPACT_DEFAULTS.get(stage_id, StageImpact.SUPPORTING)
            settings = StageSettings(
                id=stage_id,
                enabled=True,
                impact=default_impact.value,
                required=False,
                is_builtin=is_builtin,
                is_external=is_external,
                display_name=stage_id,
            )
            session.add(settings)
        
        # Check if stage is required
        if settings.required and not request.enabled:
            raise HTTPException(
                400, 
                f"Stage '{stage_id}' is required and cannot be disabled"
            )
        
        # Generate warning for high-impact stages
        warning = None
        if not request.enabled:
            if settings.impact == StageImpact.CRITICAL.value:
                raise HTTPException(
                    400,
                    f"Stage '{stage_id}' has CRITICAL impact and cannot be disabled. "
                    f"Mark it as non-critical first if you really need to disable it."
                )
            elif settings.impact == StageImpact.SUPPORTING.value:
                warning = (
                    f"Warning: '{stage_id}' is a SUPPORTING stage. "
                    f"Disabling it may significantly reduce evaluation accuracy."
                )
        
        was_enabled = settings.enabled
        settings.enabled = request.enabled
        settings.last_toggled_at = datetime.utcnow()
        settings.toggle_reason = request.reason
        
        session.commit()
        
        logger.info(
            f"Stage '{stage_id}' toggled: {was_enabled} → {request.enabled} "
            f"(reason: {request.reason})"
        )
        
        # If external stage, also update the external config
        if settings.is_external:
            try:
                ext_registry = get_external_stage_registry()
                # This also updates the external stage config in DB
                ext_config = session.query(ExternalStageModel).filter(
                    ExternalStageModel.id == stage_id
                ).first()
                if ext_config:
                    ext_config.enabled = request.enabled
                    session.commit()
            except Exception as e:
                logger.warning(f"Could not sync external stage config: {e}")
        
        return ToggleStageResponse(
            stage_id=stage_id,
            enabled=settings.enabled,
            was_enabled=was_enabled,
            impact=settings.impact,
            required=settings.required,
            warning=warning,
        )


@router.get("/settings")
async def get_all_stage_settings():
    """
    Get all stage settings for admin/debugging.
    
    Returns the persisted enable/disable state for all known stages.
    """
    with get_db_session() as session:
        settings = session.query(StageSettings).all()
        return {
            "settings": [s.to_dict() for s in settings],
            "count": len(settings),
        }


@router.get("/external", response_model=List[ExternalConfigDTO])
async def list_external_configs():
    """
    List all external stage configurations.
    """
    with get_db_session() as session:
        configs = session.query(ExternalStageModel).order_by(
            ExternalStageModel.created_at.desc()
        ).all()
        
        return [ExternalConfigDTO(**c.to_dict()) for c in configs]


@router.post("/external", response_model=ExternalConfigDTO)
async def create_or_update_external_config(request: CreateExternalConfigRequest):
    """
    Create or update an external stage configuration.
    
    The YAML is validated before saving. If valid, stages are immediately
    registered and available for use in evaluations.
    """
    # Validate YAML
    validation = validate_stage_config(request.yaml_content)
    
    with get_db_session() as session:
        # Check if exists
        existing = session.query(ExternalStageModel).filter(
            ExternalStageModel.id == request.id
        ).first()
        
        if existing:
            # Update
            existing.name = request.name
            existing.description = request.description
            existing.yaml_content = request.yaml_content
            existing.enabled = request.enabled
            existing.validated = validation["valid"]
            existing.validation_error = validation.get("error")
            existing.stage_ids = ",".join(s["id"] for s in validation.get("stages", []))
            config = existing
        else:
            # Create
            config = ExternalStageModel(
                id=request.id,
                name=request.name,
                description=request.description,
                yaml_content=request.yaml_content,
                enabled=request.enabled,
                validated=validation["valid"],
                validation_error=validation.get("error"),
                stage_ids=",".join(s["id"] for s in validation.get("stages", [])),
            )
            session.add(config)
        
        session.commit()
        session.refresh(config)
        result = config.to_dict()
    
    # If valid and enabled, register the stages
    if validation["valid"] and request.enabled:
        try:
            registry = get_external_stage_registry()
            registry.register_from_yaml(request.yaml_content, request.id)
            logger.info(f"Registered external stages from config: {request.id}")
        except Exception as e:
            logger.error(f"Failed to register stages from config {request.id}: {e}")
    
    return ExternalConfigDTO(**result)


@router.get("/external/{config_id}", response_model=ExternalConfigDTO)
async def get_external_config(config_id: str):
    """
    Get a specific external stage configuration.
    """
    with get_db_session() as session:
        config = session.query(ExternalStageModel).filter(
            ExternalStageModel.id == config_id
        ).first()
        
        if not config:
            raise HTTPException(404, f"Config '{config_id}' not found")
        
        return ExternalConfigDTO(**config.to_dict())


@router.delete("/external/{config_id}")
async def delete_external_config(config_id: str):
    """
    Delete an external stage configuration.
    
    This unregisters all stages defined in the config.
    """
    with get_db_session() as session:
        config = session.query(ExternalStageModel).filter(
            ExternalStageModel.id == config_id
        ).first()
        
        if not config:
            raise HTTPException(404, f"Config '{config_id}' not found")
        
        # Unregister stages
        stage_ids = config.stage_ids.split(",") if config.stage_ids else []
        registry = get_external_stage_registry()
        for stage_id in stage_ids:
            registry.unregister(stage_id)
        
        session.delete(config)
        session.commit()
    
    return {"status": "deleted", "config_id": config_id}


@router.post("/external/validate", response_model=ValidationResponse)
async def validate_yaml(request: ValidationRequest):
    """
    Validate YAML without saving.
    
    Use this for real-time validation in the UI editor.
    """
    result = validate_stage_config(request.yaml_content)
    return ValidationResponse(**result)


@router.post("/external/{config_id}/toggle")
async def toggle_external_config(config_id: str, enabled: bool = Body(..., embed=True)):
    """
    Enable or disable an external stage configuration.
    """
    with get_db_session() as session:
        config = session.query(ExternalStageModel).filter(
            ExternalStageModel.id == config_id
        ).first()
        
        if not config:
            raise HTTPException(404, f"Config '{config_id}' not found")
        
        config.enabled = enabled
        session.commit()
        
        # Register or unregister based on enabled state
        registry = get_external_stage_registry()
        stage_ids = config.stage_ids.split(",") if config.stage_ids else []
        
        if enabled and config.validated:
            try:
                registry.register_from_yaml(config.yaml_content, config.id)
            except Exception as e:
                logger.error(f"Failed to register stages: {e}")
        else:
            for stage_id in stage_ids:
                registry.unregister(stage_id)
    
    return {"status": "updated", "config_id": config_id, "enabled": enabled}
