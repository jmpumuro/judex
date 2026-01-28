"""
Server-Sent Events (SSE) manager for real-time pipeline progress updates.
SSE is better than WebSocket for one-directional updates: simpler, auto-reconnects, HTTP-based.
"""
import asyncio
import json
from typing import Dict, Set
from asyncio import Queue
from app.core.logging import get_logger

logger = get_logger("sse")


class SSEManager:
    """Manage SSE connections for progress updates."""
    
    def __init__(self):
        # Map evaluation_id -> set of queues (one queue per connected client)
        self.connections: Dict[str, Set[Queue]] = {}
    
    async def connect(self, evaluation_id: str) -> Queue:
        """
        Register a new SSE connection for an evaluation.
        Returns a queue that will receive progress updates.
        """
        queue = Queue(maxsize=100)  # Limit queue size to prevent memory issues
        
        if evaluation_id not in self.connections:
            self.connections[evaluation_id] = set()
        
        self.connections[evaluation_id].add(queue)
        logger.info(f"SSE connected for evaluation {evaluation_id} (total: {len(self.connections[evaluation_id])})")
        
        return queue
    
    def disconnect(self, evaluation_id: str, queue: Queue):
        """Remove an SSE connection."""
        if evaluation_id in self.connections:
            self.connections[evaluation_id].discard(queue)
            
            # Clean up if no more connections for this evaluation
            if not self.connections[evaluation_id]:
                del self.connections[evaluation_id]
                logger.info(f"All SSE connections closed for evaluation {evaluation_id}")
            else:
                logger.info(f"SSE disconnected for evaluation {evaluation_id} (remaining: {len(self.connections[evaluation_id])})")
    
    async def send_progress(self, evaluation_id: str, stage: str, message: str, progress: int):
        """
        Send progress update to all clients watching this evaluation.
        
        Args:
            evaluation_id: Evaluation identifier
            stage: Current pipeline stage
            message: Progress message
            progress: Progress percentage (0-100)
        """
        if evaluation_id not in self.connections:
            return
        
        data = {
            "stage": stage,
            "message": message,
            "progress": progress
        }
        
        # Send to all connected clients
        disconnected = set()
        for queue in self.connections[evaluation_id]:
            try:
                # Non-blocking put with timeout
                queue.put_nowait(data)
            except asyncio.QueueFull:
                logger.warning(f"Queue full for evaluation {evaluation_id}, client may be slow")
                disconnected.add(queue)
            except Exception as e:
                logger.error(f"Failed to send progress: {e}")
                disconnected.add(queue)
        
        # Clean up disconnected clients
        for queue in disconnected:
            self.disconnect(evaluation_id, queue)
    
    async def send_complete(self, evaluation_id: str):
        """Send completion message."""
        await self.send_progress(evaluation_id, "complete", "Analysis complete", 100)


# Global SSE manager instance
sse_manager = SSEManager()


async def event_generator(evaluation_id: str):
    """
    Generator for SSE events.
    Yields formatted SSE messages for a specific evaluation.
    """
    queue = await sse_manager.connect(evaluation_id)
    
    try:
        while True:
            # Wait for next progress update
            data = await queue.get()
            
            # Format as SSE message
            # SSE format: "data: {json}\n\n"
            yield f"data: {json.dumps(data)}\n\n"
            
            # Check if complete
            if data.get("stage") == "complete":
                break
                
    except asyncio.CancelledError:
        logger.info(f"SSE stream cancelled for evaluation {evaluation_id}")
    finally:
        sse_manager.disconnect(evaluation_id, queue)


async def broadcast_progress(evaluation_id: str, data: dict):
    """
    Broadcast progress update to all clients watching an evaluation.
    Used by the evaluation pipeline.
    
    Data should include:
    - stage: Current processing stage
    - message: Human readable message
    - progress: Progress percentage (0-100)
    - item_id: (optional) ID of specific item being processed
    """
    if evaluation_id not in sse_manager.connections:
        # No clients are listening - this is normal when no frontend is connected
        return
    
    logger.debug(f"SSE broadcast ({evaluation_id}): {data.get('stage')} to {len(sse_manager.connections[evaluation_id])} clients")
    
    # Include item_id in the broadcast if present
    broadcast_data = {
        "stage": data.get("stage", "processing"),
        "message": data.get("message", "Processing..."),
        "progress": data.get("progress", 0),
    }
    
    if data.get("item_id"):
        broadcast_data["item_id"] = data["item_id"]
    
    # Send to all connected clients
    disconnected = set()
    for queue in sse_manager.connections[evaluation_id]:
        try:
            queue.put_nowait(broadcast_data)
        except Exception:
            disconnected.add(queue)
    
    for queue in disconnected:
        sse_manager.disconnect(evaluation_id, queue)


def create_sse_response(evaluation_id: str):
    """
    Create an SSE StreamingResponse for an evaluation.
    """
    from fastapi.responses import StreamingResponse
    
    return StreamingResponse(
        event_generator(evaluation_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
