"""
Hashing utilities for generating stable IDs.
"""
import hashlib
from typing import Any


def generate_evidence_id(prefix: str, data: Any) -> str:
    """Generate a stable evidence ID from data."""
    data_str = str(data).encode('utf-8')
    hash_suffix = hashlib.md5(data_str).hexdigest()[:8]
    return f"{prefix}_{hash_suffix}"


def generate_segment_id(segment_index: int) -> str:
    """Generate a segment ID."""
    return f"segment_{segment_index:03d}"


def generate_vision_id(frame_index: int, detection_index: int) -> str:
    """Generate a vision event ID."""
    return f"vision_event_{frame_index:04d}_{detection_index:03d}"


def generate_asr_id(chunk_index: int) -> str:
    """Generate an ASR span ID."""
    return f"asr_span_{chunk_index:03d}"


def generate_ocr_id(frame_index: int) -> str:
    """Generate an OCR hit ID."""
    return f"ocr_hit_{frame_index:04d}"


def generate_violence_id(segment_index: int) -> str:
    """Generate a violence segment ID."""
    return f"violence_segment_{segment_index:03d}"
