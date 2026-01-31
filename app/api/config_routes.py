"""
Configuration API Routes - Schema, Validation, and Versioning.

Industry Standard: Schema-driven configuration with versioning and rollback.
"""
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime
import uuid
import json

from app.core.logging import get_logger
from app.db.connection import get_db_session as get_session
from app.db.models import CriteriaConfig, CriteriaVersion
from app.evaluation.config_schema import (
    FusionSettings,
    StageKnobs,
    StageOverrides,
    ConfigSchemaResponse,
    ConfigValidationResult,
    get_config_schema,
    validate_fusion_settings,
    validate_stage_knobs,
)
from app.evaluation.criteria import EvaluationCriteria, BUILT_IN_PRESETS

logger = get_logger("api.config")
router = APIRouter(prefix="/v1/config", tags=["Configuration"])


# =============================================================================
# Request/Response DTOs
# =============================================================================

class FusionSettingsDTO(BaseModel):
    """DTO for fusion settings update."""
    verdict_strategy: Optional[str] = None
    top_n_count: Optional[int] = None
    criterion_overrides: Optional[Dict[str, Dict[str, Any]]] = None
    confidence_floor: Optional[float] = None
    escalation_threshold: Optional[float] = None


class StageKnobsDTO(BaseModel):
    """DTO for stage knobs update - all fields optional for partial updates."""
    # Common settings
    sensitivity: Optional[str] = None
    confidence_threshold: Optional[float] = None
    max_detections: Optional[int] = None
    include_classes: Optional[List[str]] = None
    exclude_classes: Optional[List[str]] = None
    quality_mode: Optional[str] = None
    # Violence detection (X-CLIP, VideoMAE)
    temporal_window: Optional[int] = None
    # Window mining
    motion_threshold: Optional[float] = None
    # Pose heuristics
    interaction_distance: Optional[float] = None
    # NSFW detection
    nsfw_threshold: Optional[float] = None
    # Text moderation
    profanity_threshold: Optional[float] = None


class ConfigUpdateRequest(BaseModel):
    """Request to update configuration."""
    fusion_settings: Optional[FusionSettingsDTO] = None
    stage_overrides: Optional[Dict[str, StageKnobsDTO]] = None
    change_summary: Optional[str] = Field(None, description="Description of changes")


class ConfigVersionDTO(BaseModel):
    """DTO for config version."""
    version_id: str
    criteria_id: str
    created_at: datetime
    created_by: Optional[str]
    change_summary: Optional[str]
    is_current: bool


class ConfigPreviewDTO(BaseModel):
    """Preview of config changes vs defaults."""
    field: str
    label: str
    current_value: Any
    new_value: Any
    changed: bool


# =============================================================================
# Schema Endpoints
# =============================================================================

@router.get("/schema", response_model=ConfigSchemaResponse)
async def get_configuration_schema():
    """
    Get configuration schema for UI rendering.
    
    This endpoint returns all available knobs with their types, bounds,
    and metadata. The frontend uses this to render configuration controls
    dynamically without hardcoding.
    """
    return get_config_schema()


@router.get("/schema/fusion")
async def get_fusion_schema():
    """Get fusion/policy settings schema only."""
    schema = get_config_schema()
    return {"knobs": schema.fusion_knobs}


@router.get("/schema/stages")
async def get_stage_schema():
    """Get stage knobs schema only."""
    schema = get_config_schema()
    return {
        "knobs": schema.stage_knobs,
        "supported_stages": schema.supported_stages,
    }


# =============================================================================
# Validation Endpoints
# =============================================================================

@router.post("/validate/fusion", response_model=ConfigValidationResult)
async def validate_fusion_config(settings: FusionSettingsDTO):
    """
    Validate fusion settings before saving.
    
    Returns validation errors and warnings with user-friendly messages.
    """
    try:
        # Convert DTO to model
        fusion = FusionSettings(**settings.model_dump(exclude_none=True))
        return validate_fusion_settings(fusion)
    except Exception as e:
        return ConfigValidationResult(
            valid=False,
            errors=[{"field": "root", "message": str(e), "value": None}]
        )


@router.post("/validate/stage/{stage_type}", response_model=ConfigValidationResult)
async def validate_stage_config(stage_type: str, knobs: StageKnobsDTO):
    """
    Validate stage knobs before saving.
    
    Args:
        stage_type: The stage type (e.g., yolo26, yoloworld)
        knobs: The knob values to validate
    """
    schema = get_config_schema()
    if stage_type not in schema.supported_stages:
        raise HTTPException(
            status_code=400,
            detail=f"Stage type '{stage_type}' does not support knobs. Supported: {schema.supported_stages}"
        )
    
    try:
        stage_knobs = StageKnobs(**knobs.model_dump(exclude_none=True))
        return validate_stage_knobs(stage_knobs, stage_type)
    except Exception as e:
        return ConfigValidationResult(
            valid=False,
            errors=[{"field": "root", "message": str(e), "value": None}]
        )


# =============================================================================
# Configuration CRUD
# =============================================================================

@router.get("/criteria/{criteria_id}")
async def get_criteria_config(criteria_id: str):
    """
    Get full configuration for a criteria preset.
    
    Includes fusion settings, stage overrides, and metadata.
    """
    # Check if it's a built-in preset
    if criteria_id in BUILT_IN_PRESETS:
        preset = BUILT_IN_PRESETS[criteria_id]
        return {
            "id": criteria_id,
            "name": preset.name,
            "description": preset.description,
            "is_builtin": True,
            "criteria": {k: v.model_dump() for k, v in preset.criteria.items()},
            "options": preset.options.model_dump(),
            "fusion_settings": FusionSettings().model_dump(),  # Defaults
            "stage_overrides": {},
        }
    
    # Look up custom criteria in database
    with get_session() as session:
        config = session.query(CriteriaConfig).filter(
            CriteriaConfig.id == criteria_id
        ).first()
        
        if not config:
            raise HTTPException(404, f"Criteria '{criteria_id}' not found")
        
        return {
            "id": config.id,
            "name": config.name,
            "description": config.description,
            "is_builtin": False,
            "criteria": config.criteria_data,
            "options": config.options_data or {},
            "fusion_settings": config.fusion_settings or FusionSettings().model_dump(),
            "stage_overrides": config.stage_overrides or {},
            "current_version": config.current_version,
            "updated_at": config.updated_at,
        }


@router.put("/criteria/{criteria_id}")
async def update_criteria_config(criteria_id: str, request: ConfigUpdateRequest):
    """
    Update configuration for a criteria preset.
    
    Creates a new version for rollback capability.
    """
    if criteria_id in BUILT_IN_PRESETS:
        raise HTTPException(
            400,
            "Cannot modify built-in presets. Create a custom preset instead."
        )
    
    with get_session() as session:
        config = session.query(CriteriaConfig).filter(
            CriteriaConfig.id == criteria_id
        ).first()
        
        if not config:
            raise HTTPException(404, f"Criteria '{criteria_id}' not found")
        
        # Validate fusion settings if provided
        if request.fusion_settings:
            fusion = FusionSettings(**request.fusion_settings.model_dump(exclude_none=True))
            validation = validate_fusion_settings(fusion)
            if not validation.valid:
                raise HTTPException(400, detail={
                    "message": "Fusion settings validation failed",
                    "errors": [e.model_dump() for e in validation.errors]
                })
            config.fusion_settings = fusion.model_dump()
        
        # Validate stage overrides if provided
        if request.stage_overrides:
            validated_overrides = {}
            for stage_type, knobs_dto in request.stage_overrides.items():
                knobs = StageKnobs(**knobs_dto.model_dump(exclude_none=True))
                validation = validate_stage_knobs(knobs, stage_type)
                if not validation.valid:
                    raise HTTPException(400, detail={
                        "message": f"Stage '{stage_type}' knobs validation failed",
                        "errors": [e.model_dump() for e in validation.errors]
                    })
                validated_overrides[stage_type] = knobs.model_dump()
            config.stage_overrides = validated_overrides
        
        # Create new version
        new_version_id = str(uuid.uuid4())[:8]
        version = CriteriaVersion(
            id=new_version_id,
            criteria_id=criteria_id,
            version_data={
                "fusion_settings": config.fusion_settings,
                "stage_overrides": config.stage_overrides,
                "criteria_data": config.criteria_data,
            },
            change_summary=request.change_summary,
        )
        session.add(version)
        
        config.current_version = new_version_id
        config.updated_at = datetime.utcnow()
        session.commit()
        
        logger.info(f"Updated criteria '{criteria_id}' to version {new_version_id}")
        
        return {
            "id": criteria_id,
            "version_id": new_version_id,
            "message": "Configuration updated successfully",
        }


@router.post("/criteria/{criteria_id}/preview")
async def preview_config_changes(criteria_id: str, request: ConfigUpdateRequest):
    """
    Preview config changes without saving.
    
    Returns a diff showing current vs new values.
    """
    # Get current config
    current = await get_criteria_config(criteria_id)
    current_fusion = current.get("fusion_settings", FusionSettings().model_dump())
    
    changes = []
    
    if request.fusion_settings:
        new_fusion = {**current_fusion, **request.fusion_settings.model_dump(exclude_none=True)}
        
        for key, new_val in new_fusion.items():
            old_val = current_fusion.get(key)
            if old_val != new_val:
                changes.append(ConfigPreviewDTO(
                    field=f"fusion.{key}",
                    label=key.replace("_", " ").title(),
                    current_value=old_val,
                    new_value=new_val,
                    changed=True,
                ))
    
    return {"changes": changes, "change_count": len(changes)}


# =============================================================================
# Versioning Endpoints
# =============================================================================

@router.get("/criteria/{criteria_id}/versions", response_model=List[ConfigVersionDTO])
async def list_criteria_versions(
    criteria_id: str,
    limit: int = Query(10, ge=1, le=50),
):
    """
    List version history for a criteria preset.
    """
    if criteria_id in BUILT_IN_PRESETS:
        # Built-in presets have no versions
        return []
    
    with get_session() as session:
        config = session.query(CriteriaConfig).filter(
            CriteriaConfig.id == criteria_id
        ).first()
        
        if not config:
            raise HTTPException(404, f"Criteria '{criteria_id}' not found")
        
        versions = session.query(CriteriaVersion).filter(
            CriteriaVersion.criteria_id == criteria_id
        ).order_by(
            CriteriaVersion.created_at.desc()
        ).limit(limit).all()
        
        return [
            ConfigVersionDTO(
                version_id=v.id,
                criteria_id=v.criteria_id,
                created_at=v.created_at,
                created_by=v.created_by,
                change_summary=v.change_summary,
                is_current=(v.id == config.current_version),
            )
            for v in versions
        ]


@router.post("/criteria/{criteria_id}/rollback")
async def rollback_criteria(criteria_id: str, version_id: str):
    """
    Rollback criteria config to a previous version.
    """
    if criteria_id in BUILT_IN_PRESETS:
        raise HTTPException(400, "Cannot rollback built-in presets")
    
    with get_session() as session:
        config = session.query(CriteriaConfig).filter(
            CriteriaConfig.id == criteria_id
        ).first()
        
        if not config:
            raise HTTPException(404, f"Criteria '{criteria_id}' not found")
        
        version = session.query(CriteriaVersion).filter(
            CriteriaVersion.id == version_id,
            CriteriaVersion.criteria_id == criteria_id,
        ).first()
        
        if not version:
            raise HTTPException(404, f"Version '{version_id}' not found")
        
        # Restore version data
        version_data = version.version_data
        config.fusion_settings = version_data.get("fusion_settings")
        config.stage_overrides = version_data.get("stage_overrides")
        if "criteria_data" in version_data:
            config.criteria_data = version_data["criteria_data"]
        
        # Create a rollback version entry
        rollback_version_id = str(uuid.uuid4())[:8]
        rollback_version = CriteriaVersion(
            id=rollback_version_id,
            criteria_id=criteria_id,
            version_data=version_data,
            change_summary=f"Rolled back to version {version_id}",
        )
        session.add(rollback_version)
        
        config.current_version = rollback_version_id
        config.updated_at = datetime.utcnow()
        session.commit()
        
        logger.info(f"Rolled back criteria '{criteria_id}' to version {version_id}")
        
        return {
            "message": f"Rolled back to version {version_id}",
            "new_version_id": rollback_version_id,
        }


@router.post("/criteria/{criteria_id}/reset")
async def reset_to_defaults(criteria_id: str):
    """
    Reset criteria config to preset defaults.
    """
    if criteria_id in BUILT_IN_PRESETS:
        return {"message": "Built-in preset is already at defaults"}
    
    with get_session() as session:
        config = session.query(CriteriaConfig).filter(
            CriteriaConfig.id == criteria_id
        ).first()
        
        if not config:
            raise HTTPException(404, f"Criteria '{criteria_id}' not found")
        
        # Reset to defaults
        config.fusion_settings = FusionSettings().model_dump()
        config.stage_overrides = {}
        
        # Create reset version
        reset_version_id = str(uuid.uuid4())[:8]
        version = CriteriaVersion(
            id=reset_version_id,
            criteria_id=criteria_id,
            version_data={
                "fusion_settings": config.fusion_settings,
                "stage_overrides": config.stage_overrides,
            },
            change_summary="Reset to defaults",
        )
        session.add(version)
        
        config.current_version = reset_version_id
        config.updated_at = datetime.utcnow()
        session.commit()
        
        return {"message": "Reset to defaults", "version_id": reset_version_id}
