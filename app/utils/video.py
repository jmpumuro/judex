"""
Video utility functions.
"""
import shutil
from pathlib import Path
from typing import Optional
from app.core.logging import get_logger

logger = get_logger("video")


ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"}
MAX_VIDEO_SIZE_MB = 500


def validate_video_file(file_path: str) -> bool:
    """Validate video file."""
    path = Path(file_path)
    
    # Check file exists
    if not path.exists():
        logger.error(f"File does not exist: {file_path}")
        return False
    
    # Check extension
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        logger.error(f"Unsupported file extension: {path.suffix}")
        return False
    
    # Check file size
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_VIDEO_SIZE_MB:
        logger.error(f"File too large: {size_mb:.2f}MB (max {MAX_VIDEO_SIZE_MB}MB)")
        return False
    
    return True


def create_working_directory(base_dir: str, video_id: str) -> str:
    """Create a working directory for video processing."""
    work_dir = Path(base_dir) / video_id
    work_dir.mkdir(parents=True, exist_ok=True)
    
    # Create subdirectories
    (work_dir / "frames").mkdir(exist_ok=True)
    (work_dir / "segments").mkdir(exist_ok=True)
    (work_dir / "audio").mkdir(exist_ok=True)
    
    logger.info(f"Created working directory: {work_dir}")
    return str(work_dir)


def cleanup_working_directory(work_dir: str):
    """Clean up working directory."""
    try:
        path = Path(work_dir)
        if path.exists():
            shutil.rmtree(path)
            logger.info(f"Cleaned up working directory: {work_dir}")
    except Exception as e:
        logger.warning(f"Failed to clean up directory {work_dir}: {e}")
