"""
Timing utilities for performance tracking.
"""
import time
from contextlib import contextmanager
from typing import Dict, Any
from app.core.logging import get_logger

logger = get_logger("timing")


@contextmanager
def timer(operation_name: str):
    """Context manager for timing operations."""
    start = time.time()
    try:
        yield
    finally:
        duration = time.time() - start
        logger.info(f"{operation_name} took {duration:.2f}s")


class TimingTracker:
    """Track timing for multiple operations."""
    
    def __init__(self):
        self.timings: Dict[str, float] = {}
        self._starts: Dict[str, float] = {}
    
    def start(self, operation_name: str):
        """Start timing an operation."""
        self._starts[operation_name] = time.time()
    
    def end(self, operation_name: str):
        """End timing an operation."""
        if operation_name in self._starts:
            duration = time.time() - self._starts[operation_name]
            self.timings[operation_name] = duration
            logger.info(f"{operation_name} took {duration:.2f}s")
            del self._starts[operation_name]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get timing summary."""
        total = sum(self.timings.values())
        return {
            "total_seconds": round(total, 2),
            "operations": {k: round(v, 2) for k, v in self.timings.items()}
        }
