"""
MinIO/S3 Object Storage Service.

Handles file uploads, downloads, and URL generation for:
- Uploaded videos (original)
- Labeled videos (processed)
- Thumbnails
- Checkpoints
"""
import io
import os
from pathlib import Path
from typing import Optional, BinaryIO, Union
from minio import Minio
from minio.error import S3Error
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("storage")


class StorageService:
    """MinIO/S3 storage service for file management."""
    
    # Folder prefixes for organization (checkpoints are in PostgreSQL only)
    UPLOADS_PREFIX = "uploads/"
    LABELED_PREFIX = "labeled/"
    THUMBNAILS_PREFIX = "thumbnails/"
    FRAMES_PREFIX = "frames/"  # Full-size keyframes from video segmentation
    FRAME_THUMBS_PREFIX = "frame_thumbs/"  # Small thumbnails for filmstrip display
    
    def __init__(self):
        self.client: Optional[Minio] = None
        self.external_client: Optional[Minio] = None  # For presigned URLs
        self.bucket = settings.minio_bucket
        self._initialized = False
        
    def _get_client(self) -> Minio:
        """Get or create MinIO client (internal endpoint for uploads/downloads)."""
        if self.client is None:
            self.client = Minio(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure
            )
        return self.client
    
    def _get_external_client(self) -> Minio:
        """Get or create MinIO client with external endpoint (for presigned URLs)."""
        if self.external_client is None:
            self.external_client = Minio(
                endpoint=settings.minio_external_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure
            )
        return self.external_client
    
    def initialize(self):
        """Initialize storage: ensure bucket exists."""
        if self._initialized:
            return
            
        try:
            client = self._get_client()
            
            # Create bucket if it doesn't exist
            if not client.bucket_exists(self.bucket):
                client.make_bucket(self.bucket)
                logger.info(f"Created MinIO bucket: {self.bucket}")
            else:
                logger.info(f"MinIO bucket exists: {self.bucket}")
            
            self._initialized = True
            
        except S3Error as e:
            logger.error(f"Failed to initialize MinIO: {e}")
            raise
    
    def upload_file(
        self,
        file_path: Union[str, Path],
        object_name: str,
        content_type: str = "application/octet-stream"
    ) -> str:
        """
        Upload a file to MinIO.
        
        Args:
            file_path: Local path to file
            object_name: Name/path in bucket (e.g., "uploads/video123.mp4")
            content_type: MIME type
            
        Returns:
            Object name (path in bucket)
        """
        self.initialize()
        client = self._get_client()
        
        file_path = Path(file_path)
        file_size = file_path.stat().st_size
        
        try:
            client.fput_object(
                bucket_name=self.bucket,
                object_name=object_name,
                file_path=str(file_path),
                content_type=content_type
            )
            logger.info(f"Uploaded {file_path.name} -> {object_name} ({file_size} bytes)")
            return object_name
            
        except S3Error as e:
            logger.error(f"Failed to upload {file_path}: {e}")
            raise
    
    def upload_bytes(
        self,
        data: bytes,
        object_name: str,
        content_type: str = "application/octet-stream"
    ) -> str:
        """
        Upload bytes directly to MinIO.
        
        Args:
            data: Bytes to upload
            object_name: Name/path in bucket
            content_type: MIME type
            
        Returns:
            Object name
        """
        self.initialize()
        client = self._get_client()
        
        try:
            data_stream = io.BytesIO(data)
            client.put_object(
                bucket_name=self.bucket,
                object_name=object_name,
                data=data_stream,
                length=len(data),
                content_type=content_type
            )
            logger.info(f"Uploaded bytes -> {object_name} ({len(data)} bytes)")
            return object_name
            
        except S3Error as e:
            logger.error(f"Failed to upload bytes to {object_name}: {e}")
            raise
    
    def download_file(self, object_name: str, file_path: Union[str, Path]) -> Path:
        """
        Download a file from MinIO.
        
        Args:
            object_name: Name/path in bucket
            file_path: Local path to save to
            
        Returns:
            Local file path
        """
        self.initialize()
        client = self._get_client()
        
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            client.fget_object(
                bucket_name=self.bucket,
                object_name=object_name,
                file_path=str(file_path)
            )
            logger.info(f"Downloaded {object_name} -> {file_path}")
            return file_path
            
        except S3Error as e:
            logger.error(f"Failed to download {object_name}: {e}")
            raise
    
    def get_bytes(self, object_name: str) -> bytes:
        """
        Get file contents as bytes.
        
        Args:
            object_name: Name/path in bucket
            
        Returns:
            File contents as bytes
        """
        self.initialize()
        client = self._get_client()
        
        try:
            response = client.get_object(self.bucket, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            return data
            
        except S3Error as e:
            logger.error(f"Failed to get bytes from {object_name}: {e}")
            raise
    
    def get_presigned_url(
        self,
        object_name: str,
        expires_hours: int = 24
    ) -> str:
        """
        Get a presigned URL for direct access.
        
        Generates URL with the internal client (which can connect to MinIO),
        then replaces the internal endpoint with the external one for browser access.
        
        Args:
            object_name: Name/path in bucket
            expires_hours: URL expiration time
            
        Returns:
            Presigned URL (with external endpoint for browser access)
        """
        self.initialize()
        # Use internal client which can connect to MinIO
        client = self._get_client()
        
        from datetime import timedelta
        
        try:
            url = client.presigned_get_object(
                bucket_name=self.bucket,
                object_name=object_name,
                expires=timedelta(hours=expires_hours)
            )
            
            # Replace internal endpoint with external endpoint for browser access
            # MinIO signs URLs based on the endpoint used, but S3-compatible storage
            # accepts requests to different hostnames as long as signature is valid
            # when path-style addressing is used
            internal_endpoint = settings.minio_endpoint
            external_endpoint = settings.minio_external_endpoint
            
            if internal_endpoint != external_endpoint:
                url = url.replace(internal_endpoint, external_endpoint, 1)
                logger.debug(f"Replaced endpoint in presigned URL: {internal_endpoint} -> {external_endpoint}")
            
            return url
            
        except S3Error as e:
            logger.error(f"Failed to get presigned URL for {object_name}: {e}")
            raise
    
    def delete_object(self, object_name: str) -> bool:
        """
        Delete an object from MinIO.
        
        Args:
            object_name: Name/path in bucket
            
        Returns:
            True if deleted
        """
        self.initialize()
        client = self._get_client()
        
        try:
            client.remove_object(self.bucket, object_name)
            logger.info(f"Deleted {object_name}")
            return True
            
        except S3Error as e:
            logger.error(f"Failed to delete {object_name}: {e}")
            return False
    
    def object_exists(self, object_name: str) -> bool:
        """Check if object exists."""
        self.initialize()
        client = self._get_client()
        
        try:
            client.stat_object(self.bucket, object_name)
            return True
        except S3Error:
            return False
    
    def list_objects(self, prefix: str = "") -> list:
        """List objects with given prefix."""
        self.initialize()
        client = self._get_client()
        
        try:
            objects = client.list_objects(self.bucket, prefix=prefix, recursive=True)
            return [obj.object_name for obj in objects]
        except S3Error as e:
            logger.error(f"Failed to list objects: {e}")
            return []
    
    # Convenience methods for specific file types
    
    def upload_video(self, file_path: Union[str, Path], video_id: str) -> str:
        """Upload original video."""
        object_name = f"{self.UPLOADS_PREFIX}{video_id}.mp4"
        return self.upload_file(file_path, object_name, "video/mp4")
    
    def upload_labeled_video(self, file_path: Union[str, Path], video_id: str) -> str:
        """Upload labeled/processed video."""
        object_name = f"{self.LABELED_PREFIX}{video_id}.mp4"
        return self.upload_file(file_path, object_name, "video/mp4")
    
    def upload_thumbnail(self, data: bytes, video_id: str) -> str:
        """Upload video thumbnail."""
        object_name = f"{self.THUMBNAILS_PREFIX}{video_id}.jpg"
        return self.upload_bytes(data, object_name, "image/jpeg")
    
    def upload_frame(
        self, 
        data: bytes, 
        video_id: str, 
        frame_index: int,
        timestamp: float
    ) -> str:
        """
        Upload a full-size keyframe from video segmentation.
        
        Args:
            data: Image bytes (JPEG)
            video_id: Video/item ID
            frame_index: Frame index in video
            timestamp: Timestamp in seconds
        
        Returns:
            Object path in MinIO
        """
        # Format: frames/{video_id}/frame_{index:04d}_{timestamp_ms}.jpg
        object_name = f"{self.FRAMES_PREFIX}{video_id}/frame_{frame_index:04d}_{int(timestamp*1000)}.jpg"
        return self.upload_bytes(data, object_name, "image/jpeg")
    
    def upload_frame_thumbnail(
        self, 
        data: bytes, 
        video_id: str, 
        frame_index: int,
        timestamp: float
    ) -> str:
        """
        Upload a small thumbnail for filmstrip display.
        
        Args:
            data: Image bytes (JPEG, small ~120px wide)
            video_id: Video/item ID
            frame_index: Frame index in video
            timestamp: Timestamp in seconds
        
        Returns:
            Object path in MinIO
        """
        # Format: frame_thumbs/{video_id}/thumb_{index:04d}_{timestamp_ms}.jpg
        object_name = f"{self.FRAME_THUMBS_PREFIX}{video_id}/thumb_{frame_index:04d}_{int(timestamp*1000)}.jpg"
        return self.upload_bytes(data, object_name, "image/jpeg")
    
    def list_frames(self, video_id: str) -> list:
        """List all full-size frames for a video."""
        prefix = f"{self.FRAMES_PREFIX}{video_id}/"
        return self.list_objects(prefix)
    
    def list_frame_thumbnails(self, video_id: str) -> list:
        """List all thumbnail frames for a video (for filmstrip)."""
        prefix = f"{self.FRAME_THUMBS_PREFIX}{video_id}/"
        return self.list_objects(prefix)
    
    def get_video_url(self, video_id: str) -> Optional[str]:
        """Get URL for original video."""
        object_name = f"{self.UPLOADS_PREFIX}{video_id}.mp4"
        if self.object_exists(object_name):
            return self.get_presigned_url(object_name)
        return None
    
    def get_labeled_video_url(self, video_id: str) -> Optional[str]:
        """Get URL for labeled video."""
        object_name = f"{self.LABELED_PREFIX}{video_id}.mp4"
        if self.object_exists(object_name):
            return self.get_presigned_url(object_name)
        return None
    
    def delete_video_files(self, video_id: str):
        """Delete all files associated with a video (checkpoints are in PostgreSQL)."""
        prefixes = [
            f"{self.UPLOADS_PREFIX}{video_id}",
            f"{self.LABELED_PREFIX}{video_id}",
            f"{self.THUMBNAILS_PREFIX}{video_id}",
            f"{self.FRAMES_PREFIX}{video_id}",
            f"{self.FRAME_THUMBS_PREFIX}{video_id}",
        ]
        
        for prefix in prefixes:
            for obj_name in self.list_objects(prefix):
                self.delete_object(obj_name)


# Singleton instance
_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """Get or create singleton storage service."""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
