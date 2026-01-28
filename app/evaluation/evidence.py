"""
Standardized evidence model for detector outputs.

All detectors produce EvidenceItem objects that follow a common schema,
enabling consistent routing, fusion, and reporting.
"""
from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
import uuid


class MediaType(str, Enum):
    """Types of media evidence can reference."""
    FRAME = "frame"
    VIDEO_SEGMENT = "video_segment"
    AUDIO_SEGMENT = "audio_segment"
    TEXT = "text"


class BoundingBox(BaseModel):
    """Bounding box for spatial localization."""
    x1: float = Field(ge=0.0, le=1.0, description="Left edge (normalized 0-1)")
    y1: float = Field(ge=0.0, le=1.0, description="Top edge (normalized 0-1)")
    x2: float = Field(ge=0.0, le=1.0, description="Right edge (normalized 0-1)")
    y2: float = Field(ge=0.0, le=1.0, description="Bottom edge (normalized 0-1)")
    
    @property
    def width(self) -> float:
        return self.x2 - self.x1
    
    @property
    def height(self) -> float:
        return self.y2 - self.y1
    
    @property
    def area(self) -> float:
        return self.width * self.height


class TimeRange(BaseModel):
    """Time range for temporal localization."""
    start: float = Field(ge=0.0, description="Start time in seconds")
    end: float = Field(ge=0.0, description="End time in seconds")
    
    @property
    def duration(self) -> float:
        return self.end - self.start


class MediaReference(BaseModel):
    """Reference to source media for evidence."""
    type: MediaType
    path: Optional[str] = Field(default=None, description="Path to media file")
    frame_index: Optional[int] = Field(default=None, ge=0)
    time_range: Optional[TimeRange] = Field(default=None)
    bbox: Optional[BoundingBox] = Field(default=None)


class EvidenceItem(BaseModel):
    """
    A single piece of evidence produced by a detector.
    
    This is the standardized output format for all detectors.
    Evidence items can be routed to criteria and fused into scores.
    """
    # Identification
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    detector_id: str = Field(..., description="ID of the detector that produced this")
    
    # Optional criterion association (can be set during routing)
    criterion_id: Optional[str] = Field(
        default=None,
        description="Criterion this evidence applies to"
    )
    
    # Temporal localization
    timestamp: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Point-in-time timestamp (seconds)"
    )
    time_ranges: List[TimeRange] = Field(
        default_factory=list,
        description="Time ranges where evidence is present"
    )
    
    # Classification
    label: str = Field(..., description="What was detected (e.g., 'weapon', 'profanity')")
    category: Optional[str] = Field(
        default=None,
        description="Higher-level category (e.g., 'violence', 'adult')"
    )
    
    # Confidence/scoring
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Detection confidence (0-1)"
    )
    score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Severity/relevance score for criterion (0-1)"
    )
    
    # Payload (detector-specific data)
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional detector-specific data"
    )
    
    # Media references
    media_refs: List[MediaReference] = Field(
        default_factory=list,
        description="References to source media"
    )
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    model_version: Optional[str] = Field(default=None)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.model_dump(exclude_none=True)
    
    @classmethod
    def from_yolo_detection(
        cls,
        detector_id: str,
        label: str,
        confidence: float,
        bbox: Dict[str, float],
        timestamp: float,
        frame_path: Optional[str] = None,
        category: Optional[str] = None,
        **extra
    ) -> 'EvidenceItem':
        """Create evidence from YOLO detection output."""
        media_ref = MediaReference(
            type=MediaType.FRAME,
            path=frame_path,
            bbox=BoundingBox(**bbox) if bbox else None
        )
        
        return cls(
            detector_id=detector_id,
            label=label,
            confidence=confidence,
            timestamp=timestamp,
            category=category,
            payload=extra,
            media_refs=[media_ref] if frame_path or bbox else []
        )
    
    @classmethod
    def from_violence_segment(
        cls,
        detector_id: str,
        violence_score: float,
        start_time: float,
        end_time: float,
        label: str = "violence",
        **extra
    ) -> 'EvidenceItem':
        """Create evidence from violence detection output."""
        return cls(
            detector_id=detector_id,
            label=label,
            category="violence",
            confidence=violence_score,
            score=violence_score,
            time_ranges=[TimeRange(start=start_time, end=end_time)],
            payload=extra
        )
    
    @classmethod
    def from_text_moderation(
        cls,
        detector_id: str,
        text: str,
        scores: Dict[str, float],
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        **extra
    ) -> List['EvidenceItem']:
        """
        Create evidence items from text moderation output.
        
        Returns multiple evidence items, one per detected category.
        """
        items = []
        
        for category, score in scores.items():
            if score > 0.1:  # Only include if score is meaningful
                item = cls(
                    detector_id=detector_id,
                    label=category,
                    category=category,
                    confidence=score,
                    score=score,
                    time_ranges=[TimeRange(start=start_time, end=end_time)] if start_time is not None else [],
                    payload={
                        "text": text[:200],  # Truncate for storage
                        **extra
                    }
                )
                items.append(item)
        
        return items
    
    @classmethod
    def from_ocr_result(
        cls,
        detector_id: str,
        text: str,
        confidence: float,
        timestamp: float,
        bbox: Optional[Dict[str, float]] = None,
        **extra
    ) -> 'EvidenceItem':
        """Create evidence from OCR output."""
        media_refs = []
        if bbox:
            media_refs.append(MediaReference(
                type=MediaType.FRAME,
                bbox=BoundingBox(**bbox)
            ))
        
        return cls(
            detector_id=detector_id,
            label="text",
            category="ocr",
            confidence=confidence,
            timestamp=timestamp,
            payload={"text": text, **extra},
            media_refs=media_refs
        )
    
    @classmethod
    def from_asr_chunk(
        cls,
        detector_id: str,
        text: str,
        start_time: float,
        end_time: float,
        confidence: float = 1.0,
        **extra
    ) -> 'EvidenceItem':
        """Create evidence from ASR transcript chunk."""
        return cls(
            detector_id=detector_id,
            label="speech",
            category="transcript",
            confidence=confidence,
            time_ranges=[TimeRange(start=start_time, end=end_time)],
            payload={"text": text, **extra}
        )


class EvidenceCollection(BaseModel):
    """
    Collection of evidence items with filtering and aggregation utilities.
    """
    items: List[EvidenceItem] = Field(default_factory=list)
    
    def add(self, item: EvidenceItem) -> None:
        """Add an evidence item."""
        self.items.append(item)
    
    def add_many(self, items: List[EvidenceItem]) -> None:
        """Add multiple evidence items."""
        self.items.extend(items)
    
    def filter_by_detector(self, detector_id: str) -> 'EvidenceCollection':
        """Filter to items from a specific detector."""
        return EvidenceCollection(
            items=[i for i in self.items if i.detector_id == detector_id]
        )
    
    def filter_by_criterion(self, criterion_id: str) -> 'EvidenceCollection':
        """Filter to items for a specific criterion."""
        return EvidenceCollection(
            items=[i for i in self.items if i.criterion_id == criterion_id]
        )
    
    def filter_by_category(self, category: str) -> 'EvidenceCollection':
        """Filter to items of a specific category."""
        return EvidenceCollection(
            items=[i for i in self.items if i.category == category]
        )
    
    def filter_by_confidence(self, min_confidence: float) -> 'EvidenceCollection':
        """Filter to items above a confidence threshold."""
        return EvidenceCollection(
            items=[i for i in self.items if i.confidence >= min_confidence]
        )
    
    def filter_by_time_range(
        self,
        start: float,
        end: float
    ) -> 'EvidenceCollection':
        """Filter to items within a time range."""
        filtered = []
        for item in self.items:
            # Check timestamp
            if item.timestamp is not None:
                if start <= item.timestamp <= end:
                    filtered.append(item)
                    continue
            
            # Check time ranges
            for tr in item.time_ranges:
                if tr.start <= end and tr.end >= start:
                    filtered.append(item)
                    break
        
        return EvidenceCollection(items=filtered)
    
    def max_confidence(self) -> float:
        """Get maximum confidence across all items."""
        if not self.items:
            return 0.0
        return max(i.confidence for i in self.items)
    
    def max_score(self) -> float:
        """Get maximum score across all items."""
        if not self.items:
            return 0.0
        scores = [i.score for i in self.items if i.score is not None]
        return max(scores) if scores else 0.0
    
    def avg_confidence(self) -> float:
        """Get average confidence across all items."""
        if not self.items:
            return 0.0
        return sum(i.confidence for i in self.items) / len(self.items)
    
    def count_by_label(self) -> Dict[str, int]:
        """Count items by label."""
        counts: Dict[str, int] = {}
        for item in self.items:
            counts[item.label] = counts.get(item.label, 0) + 1
        return counts
    
    def count_by_category(self) -> Dict[str, int]:
        """Count items by category."""
        counts: Dict[str, int] = {}
        for item in self.items:
            if item.category:
                counts[item.category] = counts.get(item.category, 0) + 1
        return counts
    
    def get_time_ranges(self) -> List[TimeRange]:
        """Get all time ranges from items."""
        ranges = []
        for item in self.items:
            ranges.extend(item.time_ranges)
        return ranges
    
    def to_list(self) -> List[Dict[str, Any]]:
        """Convert to list of dictionaries."""
        return [item.to_dict() for item in self.items]
    
    def __len__(self) -> int:
        return len(self.items)
    
    def __iter__(self):
        return iter(self.items)
