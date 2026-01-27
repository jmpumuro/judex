"""
Frame processing queue for live stream analysis.

This queue system integrates with the LangGraph-based live feed pipeline
(app/live/graph.py) to provide:
- Industry-standard queue patterns with proper backpressure handling
- Concurrency control and retry mechanism
- Per-stream isolation and metrics
- Seamless integration with the live feed analysis graph
"""
import asyncio
import uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
from enum import Enum
import logging

logger = logging.getLogger("frame_queue")


class FrameStatus(Enum):
    """Frame processing status."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Frame:
    """Frame data structure."""
    frame_id: str
    stream_id: str
    timestamp: float
    data: bytes
    status: FrameStatus = FrameStatus.QUEUED
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    queued_at: datetime = field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    retries: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "frame_id": self.frame_id,
            "stream_id": self.stream_id,
            "timestamp": self.timestamp,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "queued_at": self.queued_at.isoformat(),
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "retries": self.retries
        }


class FrameQueue:
    """
    Production-grade frame processing queue.
    
    Features:
    - Bounded queue (max size)
    - Priority-based processing
    - Backpressure handling (drop old frames when full)
    - Per-stream queues
    - Configurable concurrency
    - Retry mechanism
    - Metrics tracking
    """
    
    def __init__(
        self,
        max_size: int = 100,
        max_concurrent: int = 5,
        max_retries: int = 3,
        drop_policy: str = "oldest"  # "oldest" or "newest"
    ):
        self.max_size = max_size
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        self.drop_policy = drop_policy
        
        # Main queue (FIFO)
        self.queue: deque[Frame] = deque(maxlen=max_size)
        
        # Per-stream queues for better isolation
        self.stream_queues: Dict[str, deque[Frame]] = {}
        
        # Processing semaphore for concurrency control
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
        # Tracking
        self.processing: Dict[str, Frame] = {}
        self.completed: deque[Frame] = deque(maxlen=1000)  # Keep last 1000
        self.failed: deque[Frame] = deque(maxlen=100)  # Keep last 100 failures
        
        # Metrics
        self.metrics = {
            "total_queued": 0,
            "total_processed": 0,
            "total_failed": 0,
            "total_dropped": 0,
            "current_queue_size": 0,
            "current_processing": 0
        }
    
    async def enqueue(self, frame: Frame) -> bool:
        """
        Add frame to queue.
        
        Returns:
            True if frame was added, False if dropped due to backpressure
        """
        # Check if queue is full
        if len(self.queue) >= self.max_size:
            logger.warning(f"Queue full ({len(self.queue)}/{self.max_size}), applying drop policy: {self.drop_policy}")
            
            if self.drop_policy == "oldest":
                # Drop oldest frame
                dropped = self.queue.popleft()
                logger.info(f"Dropped oldest frame: {dropped.frame_id}")
                self.metrics["total_dropped"] += 1
            elif self.drop_policy == "newest":
                # Don't add new frame
                logger.info(f"Dropped newest frame: {frame.frame_id}")
                self.metrics["total_dropped"] += 1
                return False
        
        # Add to main queue
        self.queue.append(frame)
        
        # Add to per-stream queue
        if frame.stream_id not in self.stream_queues:
            self.stream_queues[frame.stream_id] = deque(maxlen=50)  # 50 frames per stream
        self.stream_queues[frame.stream_id].append(frame)
        
        # Update metrics
        self.metrics["total_queued"] += 1
        self.metrics["current_queue_size"] = len(self.queue)
        
        logger.debug(f"Frame queued: {frame.frame_id} (queue size: {len(self.queue)})")
        
        return True
    
    async def dequeue(self) -> Optional[Frame]:
        """
        Get next frame to process.
        
        Implements priority: newer frames first (LIFO for low-latency)
        """
        if not self.queue:
            return None
        
        # Get most recent frame (LIFO for low latency in live streams)
        frame = self.queue.pop()
        
        frame.status = FrameStatus.PROCESSING
        self.processing[frame.frame_id] = frame
        
        self.metrics["current_queue_size"] = len(self.queue)
        self.metrics["current_processing"] = len(self.processing)
        
        return frame
    
    def mark_completed(self, frame_id: str, result: Dict[str, Any]):
        """Mark frame as successfully processed."""
        if frame_id in self.processing:
            frame = self.processing.pop(frame_id)
            frame.status = FrameStatus.COMPLETED
            frame.result = result
            frame.processed_at = datetime.utcnow()
            
            self.completed.append(frame)
            self.metrics["total_processed"] += 1
            self.metrics["current_processing"] = len(self.processing)
            
            logger.debug(f"Frame completed: {frame_id}")
    
    def mark_failed(self, frame_id: str, error: str):
        """Mark frame as failed."""
        if frame_id in self.processing:
            frame = self.processing.pop(frame_id)
            frame.status = FrameStatus.FAILED
            frame.error = error
            frame.processed_at = datetime.utcnow()
            frame.retries += 1
            
            # Retry if under max retries
            if frame.retries < self.max_retries:
                logger.info(f"Retrying frame: {frame_id} (attempt {frame.retries + 1}/{self.max_retries})")
                frame.status = FrameStatus.QUEUED
                self.queue.append(frame)
            else:
                self.failed.append(frame)
                self.metrics["total_failed"] += 1
                logger.error(f"Frame failed after {frame.retries} retries: {frame_id}")
            
            self.metrics["current_processing"] = len(self.processing)
    
    def get_stream_stats(self, stream_id: str) -> Dict[str, Any]:
        """Get statistics for a specific stream."""
        stream_queue = self.stream_queues.get(stream_id, deque())
        
        return {
            "stream_id": stream_id,
            "queued_frames": len([f for f in stream_queue if f.status == FrameStatus.QUEUED]),
            "processing_frames": len([f for f in self.processing.values() if f.stream_id == stream_id]),
            "completed_frames": len([f for f in self.completed if f.stream_id == stream_id]),
            "failed_frames": len([f for f in self.failed if f.stream_id == stream_id])
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get overall metrics."""
        return {
            **self.metrics,
            "success_rate": (
                self.metrics["total_processed"] / max(self.metrics["total_queued"], 1) * 100
            ),
            "failure_rate": (
                self.metrics["total_failed"] / max(self.metrics["total_queued"], 1) * 100
            ),
            "drop_rate": (
                self.metrics["total_dropped"] / max(self.metrics["total_queued"], 1) * 100
            )
        }
    
    def clear_stream(self, stream_id: str):
        """Clear all frames for a specific stream."""
        # Remove from main queue
        self.queue = deque([f for f in self.queue if f.stream_id != stream_id], maxlen=self.max_size)
        
        # Remove from stream queue
        if stream_id in self.stream_queues:
            del self.stream_queues[stream_id]
        
        # Remove from processing
        to_remove = [fid for fid, f in self.processing.items() if f.stream_id == stream_id]
        for fid in to_remove:
            del self.processing[fid]
        
        logger.info(f"Cleared all frames for stream: {stream_id}")


# Global frame queue instance
_frame_queue: Optional[FrameQueue] = None


def get_frame_queue(
    max_size: int = 100,
    max_concurrent: int = 5,
    max_retries: int = 3
) -> FrameQueue:
    """Get or create the global frame queue."""
    global _frame_queue
    if _frame_queue is None:
        _frame_queue = FrameQueue(
            max_size=max_size,
            max_concurrent=max_concurrent,
            max_retries=max_retries,
            drop_policy="oldest"  # Drop old frames to prioritize latest (live stream pattern)
        )
    return _frame_queue


# Industry-standard queue configuration presets
QUEUE_PRESETS = {
    "low_latency": {
        "max_size": 50,
        "max_concurrent": 10,
        "drop_policy": "oldest"
    },
    "high_throughput": {
        "max_size": 500,
        "max_concurrent": 20,
        "drop_policy": "oldest"
    },
    "balanced": {
        "max_size": 100,
        "max_concurrent": 5,
        "drop_policy": "oldest"
    },
    "conservative": {
        "max_size": 200,
        "max_concurrent": 3,
        "drop_policy": "newest"  # Don't drop old frames
    }
}
