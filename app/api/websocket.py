"""
WebSocket manager for real-time pipeline progress updates.
"""
from typing import Set, Optional
from fastapi import WebSocket
from app.core.logging import get_logger

logger = get_logger("websocket")


class ConnectionManager:
    """Manage WebSocket connections for progress updates."""
    
    def __init__(self):
        self.active_connections: dict[str, Set[WebSocket]] = {}
        # Store video metadata for checkpoint saving
        self.video_metadata: dict[str, dict] = {}
    
    async def connect(self, websocket: WebSocket, video_id: str):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        if video_id not in self.active_connections:
            self.active_connections[video_id] = set()
        self.active_connections[video_id].add(websocket)
        logger.info(f"WebSocket connected for video {video_id}")
    
    def disconnect(self, websocket: WebSocket, video_id: str):
        """Remove a WebSocket connection."""
        if video_id in self.active_connections:
            self.active_connections[video_id].discard(websocket)
            if not self.active_connections[video_id]:
                del self.active_connections[video_id]
        logger.info(f"WebSocket disconnected for video {video_id}")
    
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
        if video_id not in self.active_connections:
            return
        
        data = {
            "stage": stage,
            "message": message,
            "progress": progress
        }
        
        # Optimize checkpoint saving: only save at stage boundaries or significant progress
        # This reduces disk I/O from ~20 checkpoints to ~10 per video
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
        
        disconnected = set()
        for connection in self.active_connections[video_id]:
            try:
                await connection.send_json(data)
            except Exception as e:
                logger.error(f"Failed to send progress: {e}")
                disconnected.add(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn, video_id)
    
    async def send_complete(self, video_id: str):
        """Send completion message. Keep checkpoint for stage output viewing."""
        await self.send_progress(video_id, "complete", "Analysis complete", 100, save_checkpoint=False)
        
        # Don't delete checkpoint - keep stage outputs for later viewing
        logger.debug(f"Video {video_id} completed - checkpoint preserved for stage output viewing")
        
        # Clean up metadata
        if video_id in self.video_metadata:
            del self.video_metadata[video_id]
    
    async def send_batch_update(self, batch_id: str, batch_data: dict):
        """Send batch status update to all clients watching this batch."""
        if batch_id not in self.active_connections:
            return
        
        disconnected = set()
        for connection in self.active_connections[batch_id]:
            try:
                await connection.send_json({
                    "type": "batch_update",
                    "batch_id": batch_id,
                    "data": batch_data
                })
            except Exception as e:
                logger.error(f"Failed to send batch update: {e}")
                disconnected.add(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn, batch_id)


# Global connection manager instance
manager = ConnectionManager()

