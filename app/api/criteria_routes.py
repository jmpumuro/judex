"""
Criteria API - Unified criteria/preset management.

Consolidates all preset and criteria logic under /v1/criteria:
- GET /v1/criteria/presets - List built-in presets
- GET /v1/criteria/presets/{id} - Get preset details
- POST /v1/criteria/validate - Validate custom criteria
- POST /v1/criteria - Save custom criteria
- GET /v1/criteria/{id} - Get saved criteria
- DELETE /v1/criteria/{id} - Delete saved criteria
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional, List
from pydantic import BaseModel, Field
import yaml

from app.evaluation.criteria import (
    EvaluationCriteria, 
    Criterion, 
    Thresholds,
    Severity,
    BUILT_IN_PRESETS,
    get_preset,
    list_presets
)
from app.evaluation.routing import route_criteria_to_detectors
from app.db.connection import get_db_session as get_session
from app.db.models import Criteria as CriteriaModel
from app.core.logging import get_logger

logger = get_logger("api.criteria")
router = APIRouter(prefix="/v1/criteria", tags=["criteria"])


# ===== Response Models =====

class PresetSummary(BaseModel):
    id: str
    name: str
    description: Optional[str]
    criteria_count: int
    is_preset: bool = True


class CriterionResponse(BaseModel):
    id: str
    label: str
    description: Optional[str]
    severity: str
    enabled: bool
    thresholds: dict


class CriteriaResponse(BaseModel):
    id: Optional[str] = None
    name: str
    description: Optional[str]
    criteria: List[CriterionResponse]
    options: dict
    detectors_required: List[str] = Field(description="Auto-determined detectors")
    is_preset: bool = False


class ValidationResult(BaseModel):
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    detectors_required: List[str] = []


# ===== Helper Functions =====

def criteria_to_response(
    criteria: EvaluationCriteria,
    criteria_id: str = None,
    is_preset: bool = False
) -> CriteriaResponse:
    """Convert EvaluationCriteria to response model."""
    detectors = route_criteria_to_detectors(criteria)
    
    return CriteriaResponse(
        id=criteria_id,
        name=criteria.name,
        description=criteria.description,
        criteria=[
            CriterionResponse(
                id=cid,
                label=c.label,
                description=c.description,
                severity=c.severity.value,
                enabled=c.enabled,
                thresholds={
                    "safe": c.thresholds.safe,
                    "caution": c.thresholds.caution,
                    "unsafe": c.thresholds.unsafe
                }
            )
            for cid, c in criteria.criteria.items()
        ],
        options=criteria.options.model_dump(),
        detectors_required=detectors,
        is_preset=is_preset
    )


# ===== Preset Endpoints =====

@router.get("/presets", response_model=List[PresetSummary])
async def list_presets_endpoint():
    """
    List available built-in evaluation presets.
    
    Presets are seeded into the database on startup.
    """
    with get_session() as session:
        presets = session.query(CriteriaModel).filter(CriteriaModel.is_preset == True).all()
        return [
            PresetSummary(
                id=p.id,
                name=p.name,
                description=p.description,
                criteria_count=len(p.config.get("criteria", {})) if p.config else 0,
                is_preset=True
            )
            for p in presets
        ]


@router.get("/presets/{preset_id}", response_model=CriteriaResponse)
async def get_preset_endpoint(preset_id: str):
    """
    Get full details of a built-in preset.
    """
    with get_session() as session:
        db_preset = session.query(CriteriaModel).filter(
            CriteriaModel.id == preset_id,
            CriteriaModel.is_preset == True
        ).first()
        
        if not db_preset:
            raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found")
        
        criteria = EvaluationCriteria(**db_preset.config)
        return criteria_to_response(criteria, preset_id, is_preset=True)


@router.get("/presets/{preset_id}/export")
async def export_preset(preset_id: str, format: str = "yaml"):
    """
    Export a preset as YAML or JSON for customization.
    """
    with get_session() as session:
        db_preset = session.query(CriteriaModel).filter(
            CriteriaModel.id == preset_id,
            CriteriaModel.is_preset == True
        ).first()
        
        if not db_preset:
            raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found")
        
        criteria = EvaluationCriteria(**db_preset.config)
        
        if format.lower() == "json":
            content = criteria.to_json()
            filename = f"{preset_id}_criteria.json"
        else:
            content = criteria.to_yaml()
            filename = f"{preset_id}_criteria.yaml"
        
        return {
            "format": format,
            "content": content,
            "filename": filename
        }


# ===== Validation Endpoint =====

@router.post("/validate", response_model=ValidationResult)
async def validate_criteria(
    content: str = Form(..., description="YAML or JSON criteria configuration"),
    format: str = Form("yaml", description="Format: 'yaml' or 'json'")
):
    """
    Validate a criteria configuration without saving it.
    """
    errors = []
    warnings = []
    detectors = []
    
    try:
        if format.lower() == "yaml":
            criteria = EvaluationCriteria.from_yaml(content)
        else:
            criteria = EvaluationCriteria.from_json(content)
        
        enabled = criteria.get_enabled_criteria()
        if len(enabled) == 0:
            warnings.append("No criteria are enabled - nothing will be evaluated")
        
        for cid, c in enabled.items():
            if c.thresholds.safe >= c.thresholds.caution:
                warnings.append(f"Criterion '{cid}': safe threshold >= caution threshold")
            if c.thresholds.caution >= c.thresholds.unsafe:
                warnings.append(f"Criterion '{cid}': caution threshold >= unsafe threshold")
        
        detectors = route_criteria_to_detectors(criteria)
        
        return ValidationResult(
            valid=True,
            errors=[],
            warnings=warnings,
            detectors_required=detectors
        )
        
    except Exception as e:
        return ValidationResult(
            valid=False,
            errors=[str(e)],
            warnings=[],
            detectors_required=[]
        )


# ===== Custom Criteria CRUD =====

@router.post("")
async def save_criteria(
    file: UploadFile = File(None, description="YAML or JSON criteria file"),
    content: str = Form(None, description="YAML or JSON content directly"),
    format: str = Form("yaml", description="Format when using content param"),
    criteria_id: str = Form(..., description="ID to save as")
):
    """
    Save a custom criteria configuration.
    """
    # Get content from file or form
    if file:
        content_bytes = await file.read()
        content_str = content_bytes.decode('utf-8')
        filename = file.filename or "criteria.yaml"
        is_yaml = filename.endswith(('.yml', '.yaml'))
    elif content:
        content_str = content
        is_yaml = format.lower() == "yaml"
    else:
        raise HTTPException(400, "Either file or content must be provided")
    
    # Parse and validate
    try:
        if is_yaml:
            criteria = EvaluationCriteria.from_yaml(content_str)
        else:
            criteria = EvaluationCriteria.from_json(content_str)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid criteria: {e}")
    
    # Save to database
    with get_session() as session:
        existing = session.query(CriteriaModel).filter(CriteriaModel.id == criteria_id).first()
        
        if existing:
            existing.name = criteria.name
            existing.description = criteria.description
            existing.config = criteria.model_dump()
        else:
            db_criteria = CriteriaModel(
                id=criteria_id,
                name=criteria.name,
                description=criteria.description,
                is_preset=False,
                config=criteria.model_dump()
            )
            session.add(db_criteria)
        
        session.commit()
    
    detectors = route_criteria_to_detectors(criteria)
    
    return {
        "id": criteria_id,
        "name": criteria.name,
        "criteria_count": len(criteria.get_enabled_criteria()),
        "detectors_required": detectors
    }


@router.get("", response_model=List[PresetSummary])
async def list_saved_criteria():
    """
    List all saved custom criteria.
    """
    with get_session() as session:
        saved = session.query(CriteriaModel).filter(CriteriaModel.is_preset == False).all()
        
        return [
            PresetSummary(
                id=c.id,
                name=c.name,
                description=c.description,
                criteria_count=len(c.config.get("criteria", {})),
                is_preset=False
            )
            for c in saved
        ]


@router.get("/custom", response_model=List[PresetSummary])
async def list_custom_criteria():
    """
    List all saved custom criteria (alias for GET /criteria).
    """
    return await list_saved_criteria()


@router.get("/custom/{criteria_id}", response_model=CriteriaResponse)
async def get_custom_criteria(criteria_id: str):
    """
    Get a custom criteria configuration by ID.
    """
    with get_session() as session:
        db_criteria = session.query(CriteriaModel).filter(
            CriteriaModel.id == criteria_id,
            CriteriaModel.is_preset == False
        ).first()
        
        if not db_criteria:
            raise HTTPException(404, f"Custom criteria '{criteria_id}' not found")
        
        criteria = EvaluationCriteria(**db_criteria.config)
        return criteria_to_response(criteria, criteria_id, is_preset=False)


@router.get("/custom/{criteria_id}/export")
async def export_custom_criteria(criteria_id: str, format: str = "yaml"):
    """
    Export a custom criteria as YAML or JSON.
    """
    with get_session() as session:
        db_criteria = session.query(CriteriaModel).filter(
            CriteriaModel.id == criteria_id,
            CriteriaModel.is_preset == False
        ).first()
        
        if not db_criteria:
            raise HTTPException(status_code=404, detail=f"Custom criteria '{criteria_id}' not found")
        
        criteria = EvaluationCriteria(**db_criteria.config)
        
        if format.lower() == "json":
            content = criteria.to_json()
            filename = f"{criteria_id}_criteria.json"
        else:
            content = criteria.to_yaml()
            filename = f"{criteria_id}_criteria.yaml"
        
        return {
            "format": format,
            "content": content,
            "filename": filename
        }


@router.delete("/custom/{criteria_id}")
async def delete_custom_criteria(criteria_id: str):
    """
    Delete a custom criteria configuration (alias for DELETE /{criteria_id}).
    """
    return await delete_criteria(criteria_id)


@router.get("/{criteria_id}", response_model=CriteriaResponse)
async def get_saved_criteria(criteria_id: str):
    """
    Get a saved criteria configuration by ID.
    
    Checks both presets and custom criteria.
    """
    # Check database (presets are also in DB now)
    with get_session() as session:
        db_criteria = session.query(CriteriaModel).filter(CriteriaModel.id == criteria_id).first()
        
        if not db_criteria:
            raise HTTPException(404, f"Criteria '{criteria_id}' not found")
        
        criteria = EvaluationCriteria(**db_criteria.config)
        return criteria_to_response(criteria, criteria_id, is_preset=db_criteria.is_preset)


@router.delete("/{criteria_id}")
async def delete_criteria(criteria_id: str):
    """
    Delete a saved custom criteria configuration.
    """
    if criteria_id in BUILT_IN_PRESETS:
        raise HTTPException(400, "Cannot delete built-in presets")
    
    with get_session() as session:
        db_criteria = session.query(CriteriaModel).filter(CriteriaModel.id == criteria_id).first()
        
        if not db_criteria:
            raise HTTPException(404, f"Criteria '{criteria_id}' not found")
        
        session.delete(db_criteria)
        session.commit()
    
    return {"status": "deleted", "id": criteria_id}


# ===== Helper for other modules =====

def get_criteria_by_id(criteria_id: str) -> Optional[EvaluationCriteria]:
    """
    Get criteria by ID (preset or custom).
    
    All criteria (including presets) are in the database.
    Returns None if not found.
    """
    with get_session() as session:
        db_criteria = session.query(CriteriaModel).filter(CriteriaModel.id == criteria_id).first()
        if db_criteria:
            return EvaluationCriteria(**db_criteria.config)
    return None
