"""
Database seeds - Initialize built-in data.

This module seeds the database with:
- Built-in criteria presets (child_safety, brand_safety, etc.)

Run on application startup to ensure presets are always available.
"""
from sqlalchemy.orm import Session
from app.db.models import Criteria
from app.evaluation.criteria import BUILT_IN_PRESETS
from app.core.logging import get_logger

logger = get_logger("db.seeds")


def seed_criteria_presets(session: Session) -> None:
    """
    Seed built-in criteria presets into the database.
    
    - Creates presets if they don't exist
    - Updates existing presets if schema version changed
    - Marks them with is_preset=True
    """
    for preset_id, preset in BUILT_IN_PRESETS.items():
        existing = session.query(Criteria).filter(Criteria.id == preset_id).first()
        
        if existing:
            # Update if version changed
            current_version = existing.config.get("version", "0") if existing.config else "0"
            if current_version != preset.version:
                logger.info(f"Updating preset '{preset_id}' from v{current_version} to v{preset.version}")
                existing.name = preset.name
                existing.description = preset.description
                existing.config = preset.model_dump()
                existing.version = preset.version
        else:
            # Create new preset
            logger.info(f"Creating preset '{preset_id}'")
            db_preset = Criteria(
                id=preset_id,
                name=preset.name,
                description=preset.description,
                is_preset=True,
                config=preset.model_dump(),
                version=preset.version
            )
            session.add(db_preset)
    
    session.commit()
    logger.info(f"Seeded {len(BUILT_IN_PRESETS)} criteria presets")


def run_all_seeds(session: Session) -> None:
    """Run all database seeds."""
    seed_criteria_presets(session)
