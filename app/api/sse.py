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
        # Map video_id -> set of queues (one queue per connected client)
        self.connections: Dict[str, Set[Queue]] = {}
        # Store video metadata for checkpoint saving
        self.video_metadata: Dict[str, dict] = {}
    
    async def connect(self, video_id: str) -> Queue:
        """
        Register a new SSE connection for a video.
        Returns a queue that will receive progress updates.
        """
        queue = Queue(maxsize=100)  # Limit queue size to prevent memory issues
        
        if video_id not in self.connections:
            self.connections[video_id] = set()
        
        self.connections[video_id].add(queue)
        logger.info(f"SSE connected for video {video_id} (total: {len(self.connections[video_id])})")
        
        return queue
    
    def disconnect(self, video_id: str, queue: Queue):
        """Remove an SSE connection."""
        if video_id in self.connections:
            self.connections[video_id].discard(queue)
            
            # Clean up if no more connections for this video
            if not self.connections[video_id]:
                del self.connections[video_id]
                logger.info(f"All SSE connections closed for video {video_id}")
            else:
                logger.info(f"SSE disconnected for video {video_id} (remaining: {len(self.connections[video_id])})")
    
    def set_video_metadata(self, video_id: str, metadata: dict):
        """Store video metadata for checkpoint saving."""
        self.video_metadata[video_id] = metadata
    
    async def send_progress(self, video_id: str, stage: str, message: str, progress: int, 
                           save_checkpoint: bool = True):
        """
        Send progress update to all clients watching this video.
        
        Args:
            video_id: Video identifier
            stage: Current pipeline stage
            message: Progress message
            progress: Progress percentage (0-100)
            save_checkpoint: Whether to save checkpoint (default: True)
        """
        if video_id not in self.connections:
            return
        
        data = {
            "stage": stage,
            "message": message,
            "progress": progress
        }
        
        # Optimize checkpoint saving: only save at stage boundaries or significant progress
        should_save = False
        if save_checkpoint and progress < 100:
            # Save at major progress milestones
            milestone_progresses = [10, 20, 30, 40, 50, 60, 70, 80, 85, 92, 98]
            if progress in milestone_progresses:
                should_save = True
        
        # Save checkpoint if needed
        if should_save:
            try:
                from app.utils.checkpoints import get_checkpoint_manager
                checkpoint_manager = get_checkpoint_manager()
                
                # Get stored metadata for this video
                metadata = self.video_metadata.get(video_id, {})
                
                checkpoint_data = {
                    "video_id": video_id,
                    "batch_video_id": metadata.get("batch_video_id"),
                    "filename": metadata.get("filename"),
                    "progress": progress,
                    "stage": stage,
                    "status": "processing",
                    "duration": metadata.get("duration")
                }
                
                checkpoint_manager.save_checkpoint(video_id, checkpoint_data)
                logger.debug(f"Checkpoint saved for {video_id}: {stage} ({progress}%)")
                
            except Exception as e:
                logger.error(f"Failed to save checkpoint for {video_id}: {e}")
        
        # Send to all connected clients
        disconnected = set()
        for queue in self.connections[video_id]:
            try:
                # Non-blocking put with timeout
                queue.put_nowait(data)
            except asyncio.QueueFull:
                logger.warning(f"Queue full for video {video_id}, client may be slow")
                disconnected.add(queue)
            except Exception as e:
                logger.error(f"Failed to send progress: {e}")
                disconnected.add(queue)
        
        # Clean up disconnected clients
        for queue in disconnected:
            self.disconnect(video_id, queue)
    
    async def send_complete(self, video_id: str):
        """Send completion message and clear checkpoint."""
        await self.send_progress(video_id, "complete", "Analysis complete", 100, save_checkpoint=False)
        
        # Delete checkpoint on completion
        try:
            from app.utils.checkpoints import get_checkpoint_manager
            checkpoint_manager = get_checkpoint_manager()
            checkpoint_manager.delete_checkpoint(video_id)
            logger.debug(f"Checkpoint cleared for completed video {video_id}")
        except Exception as e:
            logger.error(f"Failed to clear checkpoint for {video_id}: {e}")
        
        # Clean up metadata
        if video_id in self.video_metadata:
            del self.video_metadata[video_id]


# Global SSE manager instance
sse_manager = SSEManager()


async def event_generator(video_id: str):
    """
    Generator for SSE events.
    Yields formatted SSE messages for a specific video.
    """
    queue = await sse_manager.connect(video_id)
    
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
        logger.info(f"SSE stream cancelled for video {video_id}")
    finally:
        sse_manager.disconnect(video_id, queue)
