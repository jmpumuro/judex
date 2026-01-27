"""
Progress callback helper for synchronous nodes.
"""
import asyncio
from typing import Callable, Optional


def send_progress(callback: Optional[Callable], stage: str, message: str, progress: int):
    """Send progress update from sync context."""
    if not callback:
        return
    
    try:
        # Try to get the current event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create a task in the running loop
            asyncio.create_task(callback(stage, message, progress))
        else:
            # Run in the loop
            loop.run_until_complete(callback(stage, message, progress))
    except RuntimeError:
        # No event loop available, try to run directly
        try:
            asyncio.run(callback(stage, message, progress))
        except:
            pass  # Skip if unable to send progress
