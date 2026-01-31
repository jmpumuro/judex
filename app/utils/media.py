"""
Media type detection and utilities.

Scalable abstraction for handling both images and videos in the pipeline.
Industry standard: Single source of truth for media type handling.
"""
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import mimetypes

from app.core.logging import get_logger

logger = get_logger("utils.media")


class MediaType(str, Enum):
    """Supported media types for pipeline processing."""
    VIDEO = "video"
    IMAGE = "image"
    UNKNOWN = "unknown"


# File extension mappings
VIDEO_EXTENSIONS = {
    ".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", 
    ".wmv", ".m4v", ".mpeg", ".mpg", ".3gp"
}

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", 
    ".tiff", ".tif", ".heic", ".heif"
}

# MIME type mappings
VIDEO_MIMES = {
    "video/mp4", "video/avi", "video/quicktime", "video/x-matroska",
    "video/webm", "video/x-flv", "video/x-ms-wmv", "video/mpeg"
}

IMAGE_MIMES = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "image/bmp", "image/tiff", "image/heic", "image/heif"
}


def detect_media_type(file_path: str) -> MediaType:
    """
    Detect media type from file path.
    
    Uses extension first, falls back to MIME type detection.
    
    Args:
        file_path: Path to the media file
        
    Returns:
        MediaType enum value
    """
    path = Path(file_path)
    ext = path.suffix.lower()
    
    # Check by extension first (most reliable)
    if ext in VIDEO_EXTENSIONS:
        return MediaType.VIDEO
    if ext in IMAGE_EXTENSIONS:
        return MediaType.IMAGE
    
    # Fallback to MIME type detection
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type:
        if mime_type in VIDEO_MIMES or mime_type.startswith("video/"):
            return MediaType.VIDEO
        if mime_type in IMAGE_MIMES or mime_type.startswith("image/"):
            return MediaType.IMAGE
    
    logger.warning(f"Unknown media type for file: {file_path}")
    return MediaType.UNKNOWN


def is_video(file_path: str) -> bool:
    """Check if file is a video."""
    return detect_media_type(file_path) == MediaType.VIDEO


def is_image(file_path: str) -> bool:
    """Check if file is an image."""
    return detect_media_type(file_path) == MediaType.IMAGE


def get_image_metadata(file_path: str) -> Dict[str, Any]:
    """
    Extract metadata from an image file.
    
    Args:
        file_path: Path to image file
        
    Returns:
        Metadata dict with width, height, format, etc.
    """
    try:
        from PIL import Image
        
        with Image.open(file_path) as img:
            metadata = {
                "width": img.width,
                "height": img.height,
                "format": img.format,
                "mode": img.mode,
                "duration": 0,  # Images have no duration
                "fps": 1,  # Treat as single frame
                "frame_count": 1,
                "has_audio": False,
                "media_type": MediaType.IMAGE.value,
            }
            
            # Extract EXIF data if available
            exif = img.getexif()
            if exif:
                metadata["exif"] = {
                    k: v for k, v in exif.items() 
                    if isinstance(v, (str, int, float))
                }
            
            return metadata
            
    except Exception as e:
        logger.error(f"Failed to get image metadata: {e}")
        return {
            "width": 0,
            "height": 0,
            "format": "unknown",
            "duration": 0,
            "fps": 1,
            "frame_count": 1,
            "has_audio": False,
            "media_type": MediaType.IMAGE.value,
            "error": str(e),
        }


def get_supported_extensions() -> Tuple[set, set]:
    """Get supported video and image extensions."""
    return VIDEO_EXTENSIONS, IMAGE_EXTENSIONS


def get_all_supported_extensions() -> set:
    """Get all supported media extensions."""
    return VIDEO_EXTENSIONS | IMAGE_EXTENSIONS


def validate_media_file(file_path: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that a file is a supported media type.
    
    Args:
        file_path: Path to media file
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    path = Path(file_path)
    
    if not path.exists():
        return False, f"File not found: {file_path}"
    
    if not path.is_file():
        return False, f"Not a file: {file_path}"
    
    media_type = detect_media_type(file_path)
    if media_type == MediaType.UNKNOWN:
        return False, f"Unsupported media type: {path.suffix}"
    
    # Validate file is readable
    try:
        if media_type == MediaType.IMAGE:
            from PIL import Image
            with Image.open(file_path) as img:
                img.verify()
        else:
            # Video validation handled by ffmpeg in ingest
            pass
        return True, None
    except Exception as e:
        return False, f"Invalid media file: {str(e)}"


# Stage compatibility matrix
# Defines which stages apply to which media types
STAGE_MEDIA_SUPPORT = {
    # Core stages - work on both
    "ingest": {MediaType.VIDEO, MediaType.IMAGE},
    "segment": {MediaType.VIDEO, MediaType.IMAGE},
    "yolo26": {MediaType.VIDEO, MediaType.IMAGE},
    "yoloworld": {MediaType.VIDEO, MediaType.IMAGE},
    "ocr": {MediaType.VIDEO, MediaType.IMAGE},
    "nsfw_detection": {MediaType.VIDEO, MediaType.IMAGE},
    "text_moderation": {MediaType.VIDEO, MediaType.IMAGE},
    "policy_fusion": {MediaType.VIDEO, MediaType.IMAGE},
    "report": {MediaType.VIDEO, MediaType.IMAGE},
    
    # Video-only stages (require temporal context)
    "violence": {MediaType.VIDEO},  # X-CLIP needs 16+ frames
    "xclip": {MediaType.VIDEO},
    "videomae_violence": {MediaType.VIDEO},  # VideoMAE needs temporal
    "window_mining": {MediaType.VIDEO},  # Motion detection
    "pose_heuristics": {MediaType.VIDEO},  # Needs motion patterns
    "whisper": {MediaType.VIDEO},  # Audio transcription
    "audio_asr": {MediaType.VIDEO},
}


def stage_supports_media_type(stage_id: str, media_type: MediaType) -> bool:
    """
    Check if a stage supports a given media type.
    
    Args:
        stage_id: The stage identifier
        media_type: The media type to check
        
    Returns:
        True if stage supports the media type
    """
    supported = STAGE_MEDIA_SUPPORT.get(stage_id, {MediaType.VIDEO, MediaType.IMAGE})
    return media_type in supported


def get_stages_for_media_type(media_type: MediaType) -> set:
    """Get all stages that support a given media type."""
    return {
        stage_id for stage_id, types in STAGE_MEDIA_SUPPORT.items()
        if media_type in types
    }
