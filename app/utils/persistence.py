"""
Result persistence utilities for SafeVid.
"""
import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
from app.core.logging import get_logger
from app.core.config import settings

logger = get_logger("persistence")


class ResultStore:
    """Manages persistent storage of video analysis results."""
    
    def __init__(self, data_dir: str = None):
        self.data_dir = Path(data_dir or settings.data_dir)
        self.results_file = self.data_dir / "results.json"
        self._ensure_data_dir()
    
    def _ensure_data_dir(self):
        """Create data directory if it doesn't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Data directory: {self.data_dir}")
    
    def save_results(self, results: List[Dict[str, Any]]) -> bool:
        """Save batch results to JSON file."""
        try:
            # Add timestamp
            data = {
                "last_updated": datetime.utcnow().isoformat(),
                "version": "1.0",
                "results": results
            }
            
            with open(self.results_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Saved {len(results)} results to {self.results_file}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            return False
    
    def load_results(self) -> List[Dict[str, Any]]:
        """Load results from JSON file."""
        try:
            if not self.results_file.exists():
                logger.info("No saved results found")
                return []
            
            with open(self.results_file, 'r') as f:
                data = json.load(f)
            
            results = data.get("results", [])
            logger.info(f"Loaded {len(results)} results from {self.results_file}")
            return results
        
        except Exception as e:
            logger.error(f"Failed to load results: {e}")
            return []
    
    def delete_result(self, video_id: str) -> bool:
        """Delete a specific result by video ID."""
        try:
            results = self.load_results()
            original_count = len(results)
            
            # Filter out the video to delete
            results = [r for r in results if r.get('id') != video_id]
            
            if len(results) < original_count:
                self.save_results(results)
                logger.info(f"Deleted result for video {video_id}")
                return True
            
            logger.warning(f"Video {video_id} not found in results")
            return False
        
        except Exception as e:
            logger.error(f"Failed to delete result: {e}")
            return False
    
    def clear_all(self) -> bool:
        """Delete all saved results."""
        try:
            if self.results_file.exists():
                self.results_file.unlink()
                logger.info("Cleared all saved results")
            return True
        
        except Exception as e:
            logger.error(f"Failed to clear results: {e}")
            return False


# Global store instance
_store = None


def get_store() -> ResultStore:
    """Get or create global result store instance."""
    global _store
    if _store is None:
        _store = ResultStore()
    return _store
