"""
Policy presets and preset management.

Presets are pre-configured EvaluationSpecs for common use cases.
The "child_safety" preset provides backward compatibility with the original API.
"""
from app.policies.presets import (
    get_preset,
    list_presets,
    DEFAULT_PRESET,
    CHILD_SAFETY_PRESET,
    PresetNotFoundError
)

__all__ = [
    "get_preset",
    "list_presets", 
    "DEFAULT_PRESET",
    "CHILD_SAFETY_PRESET",
    "PresetNotFoundError"
]
