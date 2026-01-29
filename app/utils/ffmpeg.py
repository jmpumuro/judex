"""
FFmpeg utilities for video processing.
"""
import subprocess
import json
from pathlib import Path
from typing import Dict, Any, List
from app.core.logging import get_logger

logger = get_logger("ffmpeg")


def get_video_metadata(video_path: str) -> Dict[str, Any]:
    """Extract video metadata using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        video_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        # Find video stream
        video_stream = None
        audio_stream = None
        
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video" and not video_stream:
                video_stream = stream
            elif stream.get("codec_type") == "audio" and not audio_stream:
                audio_stream = stream
        
        if not video_stream:
            raise ValueError("No video stream found")
        
        duration = float(data["format"].get("duration", 0))
        
        # Parse frame rate
        fps_str = video_stream.get("r_frame_rate", "30/1")
        if "/" in fps_str:
            num, den = map(int, fps_str.split("/"))
            fps = num / den if den != 0 else 30.0
        else:
            fps = float(fps_str)
        
        return {
            "duration": duration,
            "fps": fps,
            "width": int(video_stream.get("width", 0)),
            "height": int(video_stream.get("height", 0)),
            "has_audio": audio_stream is not None,
            "codec": video_stream.get("codec_name", "unknown"),
        }
    
    except subprocess.CalledProcessError as e:
        logger.error(f"ffprobe failed: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Failed to extract video metadata: {e}")
        raise


def extract_frames(
    video_path: str,
    output_dir: str,
    fps: float = 1.0,
    output_pattern: str = "frame_%04d.jpg"
) -> List[str]:
    """Extract frames from video at specified FPS."""
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    
    output_path = str(output_dir_path / output_pattern)
    
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vf", f"fps={fps}",
        "-q:v", "2",  # High quality
        "-y",  # Overwrite
        output_path
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        
        # Get list of extracted frames
        frames = sorted(output_dir_path.glob("frame_*.jpg"))
        return [str(f) for f in frames]
    
    except subprocess.CalledProcessError as e:
        logger.error(f"Frame extraction failed: {e.stderr}")
        raise


def extract_audio(video_path: str, output_path: str) -> str:
    """Extract audio from video as WAV."""
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vn",  # No video
        "-acodec", "pcm_s16le",  # PCM 16-bit
        "-ar", "16000",  # 16kHz sample rate
        "-ac", "1",  # Mono
        "-y",  # Overwrite
        output_path
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return output_path
    
    except subprocess.CalledProcessError as e:
        logger.error(f"Audio extraction failed: {e.stderr}")
        raise


def normalize_video(
    input_path: str,
    output_path: str,
    audio_path: str,
    target_fps: int = 30,
    target_height: int = 480  # Reduced from 720 to save memory
) -> bool:
    """
    Normalize video to consistent format for downstream models.
    
    Args:
        input_path: Source video path
        output_path: Normalized video output path
        audio_path: Extracted audio output path (mono 16kHz WAV)
        target_fps: Target frame rate (default 30)
        target_height: Target height while preserving aspect ratio (default 480)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Normalize video:
        # - Constant FPS
        # - Scale to target height, preserve aspect ratio
        # - Re-encode with consistent codec
        # - Use ultrafast preset and single thread to minimize memory
        video_cmd = [
            "ffmpeg",
            "-threads", "1",  # Single thread to reduce memory
            "-i", input_path,
            "-vf", f"fps={target_fps},scale=-2:{target_height}",  # -2 ensures width is even
            "-c:v", "libx264",
            "-preset", "ultrafast",  # Faster, less memory
            "-crf", "28",  # Lower quality to reduce memory
            "-an",  # No audio in video file
            "-y",
            output_path
        ]
        
        logger.info(f"Normalizing video: {target_fps}fps, {target_height}p (memory-optimized)")
        result = subprocess.run(video_cmd, capture_output=True, text=True, timeout=120)  # 2 min timeout
        
        if result.returncode != 0:
            logger.error(f"Video normalization failed: {result.stderr}")
            return False
        
        # Extract audio separately (mono 16kHz for Whisper)
        audio_cmd = [
            "ffmpeg",
            "-i", input_path,
            "-vn",  # No video
            "-acodec", "pcm_s16le",  # PCM 16-bit
            "-ar", "16000",  # 16kHz sample rate (Whisper-friendly)
            "-ac", "1",  # Mono
            "-y",
            audio_path
        ]
        
        audio_result = subprocess.run(audio_cmd, capture_output=True, text=True)
        
        if audio_result.returncode != 0:
            logger.warning(f"Audio extraction failed: {audio_result.stderr}")
            # Continue even if audio extraction fails (video without audio is okay)
        
        logger.info("Video normalization completed successfully")
        return True
    
    except Exception as e:
        logger.error(f"Video normalization error: {e}")
        return False


def extract_segment_frames(
    video_path: str,
    output_dir: str,
    start_time: float,
    duration: float,
    num_frames: int = 16
) -> List[str]:
    """Extract a specific number of frames from a video segment."""
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    
    output_pattern = f"seg_{start_time:.1f}_%04d.jpg"
    output_path = str(output_dir_path / output_pattern)
    
    # Calculate FPS to get desired number of frames
    fps = num_frames / duration if duration > 0 else 1.0
    
    cmd = [
        "ffmpeg",
        "-ss", str(start_time),
        "-i", video_path,
        "-t", str(duration),
        "-vf", f"fps={fps}",
        "-q:v", "2",
        "-y",
        output_path
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        
        # Get list of extracted frames
        frames = sorted(output_dir_path.glob(f"seg_{start_time:.1f}_*.jpg"))
        return [str(f) for f in frames]
    
    except subprocess.CalledProcessError as e:
        logger.error(f"Segment frame extraction failed: {e.stderr}")
        raise


def create_labeled_video(
    video_path: str,
    output_path: str,
    detections: List[Dict[str, Any]],
    fps: float,
    violence_segments: List[Dict[str, Any]] = None
) -> str:
    """
    Create a video with labeled bounding boxes from YOLO detections using Python.
    Optionally adds a timeline bar at the bottom with red markers for violent segments.
    
    Args:
        video_path: Path to input video
        output_path: Path to output video
        detections: List of YOLO detection dictionaries
        fps: Video FPS
        violence_segments: Optional list of violence segment dictionaries with start_time, end_time, violence_score
    """
    import cv2
    import numpy as np
    
    try:
        # Open the video
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")
        
        # Get video properties
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        original_fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / original_fps if original_fps > 0 else 0
        
        # Create temporary output with OpenCV (uncompressed AVI)
        temp_output = output_path.replace('.mp4', '_temp.avi')
        
        # Use XVID codec for temporary file (more reliable than mp4v)
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        out = cv2.VideoWriter(temp_output, fourcc, original_fps, (width, height))
        
        if not out.isOpened():
            raise ValueError(f"Could not create video writer for: {temp_output}")
        
        # Group detections by timestamp for quick lookup
        detection_map = {}
        detection_timestamps = []
        
        for det in detections:
            ts = round(det['timestamp'], 2)
            if ts not in detection_map:
                detection_map[ts] = []
                detection_timestamps.append(ts)
            detection_map[ts].append(det)
        
        detection_timestamps.sort()
        
        # Prepare violence segments timeline (if provided)
        violence_timeline = []
        if violence_segments:
            for seg in violence_segments:
                if seg.get('violence_score', 0) > 0.5:  # Only mark high-violence segments
                    violence_timeline.append({
                        'start': seg.get('start_time', 0),
                        'end': seg.get('end_time', 0),
                        'score': seg.get('violence_score', 0)
                    })
        
        # Timeline bar properties
        timeline_height = 8  # Thin bar at bottom
        timeline_margin = 10  # Margin from edges
        timeline_y = height - timeline_height - 5  # Position near bottom
        
        frame_idx = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Calculate current timestamp
            current_time = round(frame_idx / original_fps, 2)
            
            # Find the nearest detection timestamp (within 1 second)
            # This provides temporal smoothing to avoid flickering
            nearest_detection_time = None
            min_diff = float('inf')
            
            for det_time in detection_timestamps:
                diff = abs(current_time - det_time)
                if diff < min_diff and diff < 1.0:  # Within 1 second
                    min_diff = diff
                    nearest_detection_time = det_time
            
            # Draw bounding boxes from the nearest detection timestamp
            if nearest_detection_time is not None and nearest_detection_time in detection_map:
                for det in detection_map[nearest_detection_time]:
                    bbox = det['bbox']
                    label = det['label']
                    confidence = det['confidence']
                    category = det.get('category', 'other')
                    
                    # Color based on category (BGR format for OpenCV)
                    if category == 'weapon':
                        color = (0, 0, 255)  # Red
                    elif category == 'substance':
                        color = (0, 165, 255)  # Orange
                    elif category == 'person':
                        color = (255, 255, 0)  # Cyan
                    else:
                        color = (0, 255, 0)  # Green
                    
                    # Draw rectangle
                    x1, y1, x2, y2 = int(bbox['x1']), int(bbox['y1']), int(bbox['x2']), int(bbox['y2'])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    
                    # Draw label
                    label_text = f"{label} {confidence:.2f}"
                    label_size = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
                    
                    # Background for text
                    cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), 
                                (x1 + label_size[0], y1), color, -1)
                    
                    # Text
                    cv2.putText(frame, label_text, (x1, y1 - 5), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Draw timeline bar at the bottom
            if violence_timeline and duration > 0:
                # Draw background bar (dark gray)
                timeline_width = width - (2 * timeline_margin)
                cv2.rectangle(frame, 
                            (timeline_margin, timeline_y), 
                            (timeline_margin + timeline_width, timeline_y + timeline_height),
                            (40, 40, 40), -1)  # Dark gray background
                
                # Draw progress indicator (white line)
                progress_x = int(timeline_margin + (current_time / duration) * timeline_width)
                cv2.line(frame, 
                        (progress_x, timeline_y), 
                        (progress_x, timeline_y + timeline_height),
                        (255, 255, 255), 2)  # White current position
                
                # Draw red markers for violent segments
                for v_seg in violence_timeline:
                    start_x = int(timeline_margin + (v_seg['start'] / duration) * timeline_width)
                    end_x = int(timeline_margin + (v_seg['end'] / duration) * timeline_width)
                    
                    # Ensure minimum width for visibility
                    if end_x - start_x < 3:
                        end_x = start_x + 3
                    
                    # Draw red marker
                    cv2.rectangle(frame,
                                (start_x, timeline_y),
                                (end_x, timeline_y + timeline_height),
                                (0, 0, 255), -1)  # Red for violence
            
            out.write(frame)
            frame_idx += 1
        
        cap.release()
        out.release()
        
        logger.info(f"OpenCV processing complete, converting to H.264...")
        
        # Convert to H.264 MP4 using FFmpeg for browser compatibility
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", temp_output,
            "-c:v", "libx264",  # H.264 codec
            "-preset", "fast",
            "-crf", "23",  # Quality (lower = better, 23 is default)
            "-pix_fmt", "yuv420p",  # Required for browser compatibility
            "-y",  # Overwrite
            output_path
        ]
        
        subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
        
        # Remove temporary file
        Path(temp_output).unlink()
        
        logger.info(f"Created labeled video: {output_path}")
        return output_path
    
    except Exception as e:
        logger.error(f"Failed to create labeled video: {e}")
        # Clean up temporary file if it exists
        try:
            if 'temp_output' in locals():
                Path(temp_output).unlink()
        except:
            pass
        raise
