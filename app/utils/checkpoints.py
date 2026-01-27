"""
Checkpoint management for video processing.
Allows resuming interrupted video processing from the last successful stage.
"""
import json
import time
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("utils.checkpoints")


class CheckpointManager:
    """Singleton for managing processing checkpoints."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.checkpoints_dir = Path(settings.data_dir) / "checkpoints"
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        
        self._initialized = True
        logger.info(f"CheckpointManager initialized: {self.checkpoints_dir}")
    
    def _get_checkpoint_path(self, video_id: str) -> Path:
        """Get checkpoint file path for a video."""
        return self.checkpoints_dir / f"{video_id}_checkpoint.json"
    
    def save_checkpoint(self, video_id: str, checkpoint_data: Dict) -> bool:
        """
        Save checkpoint for a video.
        
        Args:
            video_id: Unique video identifier
            checkpoint_data: Dictionary containing checkpoint information
                - batch_video_id: Batch video ID
                - filename: Video filename
                - progress: Progress percentage
                - stage: Current pipeline stage
                - timestamp: When checkpoint was created
                - status: Current status
                - duration: Video duration (if known)
                
        Returns:
            True if successful, False otherwise
        """
        try:
            checkpoint_path = self._get_checkpoint_path(video_id)
            
            # Add metadata
            checkpoint_data['video_id'] = video_id
            checkpoint_data['last_updated'] = time.time()
            checkpoint_data['updated_at'] = datetime.now().isoformat()
            
            with open(checkpoint_path, 'w') as f:
                json.dump(checkpoint_data, f, indent=2)
            
            logger.debug(f"Checkpoint saved for {video_id}: {checkpoint_data.get('stage')} ({checkpoint_data.get('progress')}%)")
            return True
            
        except Exception as e:
            logger.error(f"Error saving checkpoint for {video_id}: {e}")
            return False
    
    def load_checkpoint(self, video_id: str) -> Optional[Dict]:
        """
        Load checkpoint for a video.
        
        Args:
            video_id: Unique video identifier
            
        Returns:
            Checkpoint data dictionary or None if not found
        """
        try:
            checkpoint_path = self._get_checkpoint_path(video_id)
            
            if not checkpoint_path.exists():
                return None
            
            with open(checkpoint_path, 'r') as f:
                checkpoint_data = json.load(f)
            
            logger.debug(f"Checkpoint loaded for {video_id}: {checkpoint_data.get('stage')} ({checkpoint_data.get('progress')}%)")
            return checkpoint_data
            
        except Exception as e:
            logger.error(f"Error loading checkpoint for {video_id}: {e}")
            return None
    
    def delete_checkpoint(self, video_id: str) -> bool:
        """
        Delete checkpoint for a video.
        
        Args:
            video_id: Unique video identifier
            
        Returns:
            True if successful or checkpoint doesn't exist, False on error
        """
        try:
            checkpoint_path = self._get_checkpoint_path(video_id)
            
            if checkpoint_path.exists():
                checkpoint_path.unlink()
                logger.debug(f"Checkpoint deleted for {video_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting checkpoint for {video_id}: {e}")
            return False
    
    def list_all_checkpoints(self) -> List[Dict]:
        """
        List all checkpoints.
        
        Returns:
            List of checkpoint dictionaries
        """
        try:
            checkpoints = []
            
            for checkpoint_file in self.checkpoints_dir.glob("*_checkpoint.json"):
                try:
                    with open(checkpoint_file, 'r') as f:
                        checkpoint_data = json.load(f)
                        checkpoints.append(checkpoint_data)
                except Exception as e:
                    logger.error(f"Error reading checkpoint {checkpoint_file}: {e}")
                    continue
            
            logger.debug(f"Found {len(checkpoints)} checkpoint(s)")
            return checkpoints
            
        except Exception as e:
            logger.error(f"Error listing checkpoints: {e}")
            return []
    
    def cleanup_old_checkpoints(self, max_age_hours: int = 24) -> int:
        """
        Clean up old checkpoints.
        
        Args:
            max_age_hours: Maximum age in hours before checkpoint is deleted
            
        Returns:
            Number of checkpoints deleted
        """
        try:
            deleted_count = 0
            cutoff_time = time.time() - (max_age_hours * 3600)
            
            for checkpoint_file in self.checkpoints_dir.glob("*_checkpoint.json"):
                try:
                    with open(checkpoint_file, 'r') as f:
                        checkpoint_data = json.load(f)
                    
                    last_updated = checkpoint_data.get('last_updated', 0)
                    
                    if last_updated < cutoff_time:
                        checkpoint_file.unlink()
                        deleted_count += 1
                        logger.info(f"Deleted old checkpoint: {checkpoint_file.name}")
                        
                except Exception as e:
                    logger.error(f"Error processing checkpoint {checkpoint_file}: {e}")
                    continue
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old checkpoint(s)")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up checkpoints: {e}")
            return 0
    
    def get_interrupted_videos(self) -> List[Dict]:
        """
        Get list of videos with checkpoints (interrupted processing).
        
        Returns:
            List of checkpoint dictionaries for interrupted videos
        """
        checkpoints = self.list_all_checkpoints()
        
        # Filter for checkpoints that are not at 100% (interrupted)
        interrupted = [
            cp for cp in checkpoints 
            if cp.get('progress', 0) < 100 and cp.get('status') != 'completed'
        ]
        
        logger.info(f"Found {len(interrupted)} interrupted video(s)")
        return interrupted
    
    def clear_all_checkpoints(self) -> int:
        """
        Delete all checkpoints.
        
        Returns:
            Number of checkpoints deleted
        """
        try:
            deleted_count = 0
            
            for checkpoint_file in self.checkpoints_dir.glob("*_checkpoint.json"):
                try:
                    checkpoint_file.unlink()
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Error deleting {checkpoint_file}: {e}")
            
            logger.info(f"Cleared {deleted_count} checkpoint(s)")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error clearing checkpoints: {e}")
            return 0


def get_checkpoint_manager() -> CheckpointManager:
    """Get the singleton checkpoint manager instance."""
    return CheckpointManager()
