"""
Live stream and real-time feed processing endpoints.

Refactored to use the LangGraph-based live feed analysis pipeline
for consistency with the batch video pipeline.
"""
import uuid
import asyncio
from typing import Dict, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import cv2
import numpy as np
from io import BytesIO
from PIL import Image
import time

from app.core.logging import get_logger
from app.live.graph import analyze_frame_async, get_live_graph
from app.utils.frame_queue import get_frame_queue, Frame, FrameStatus

logger = get_logger("live")

router = APIRouter(prefix="/live", tags=["live"])


# Store active streams
active_streams: Dict[str, dict] = {}


class StreamStartRequest(BaseModel):
    stream_url: str
    stream_type: str  # 'rtsp', 'rtmp', 'http'


@router.post("/stream/start")
async def start_stream(request: StreamStartRequest):
    """
    Start processing a live stream (RTSP/RTMP).
    Returns a stream ID that can be used to access the processed feed.
    """
    stream_id = str(uuid.uuid4())
    
    logger.info(f"Starting stream {stream_id}: {request.stream_url}")
    
    try:
        # Create video capture for the stream
        cap = cv2.VideoCapture(request.stream_url)
        
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail="Failed to open stream")
        
        # Store stream info
        active_streams[stream_id] = {
            "url": request.stream_url,
            "type": request.stream_type,
            "capture": cap,
            "active": True
        }
        
        return {
            "stream_id": stream_id,
            "status": "active",
            "message": "Stream started successfully"
        }
        
    except Exception as e:
        logger.error(f"Error starting stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/stream/{stream_id}")
async def stop_stream(stream_id: str):
    """Stop a live stream."""
    if stream_id not in active_streams:
        raise HTTPException(status_code=404, detail="Stream not found")
    
    stream = active_streams[stream_id]
    stream["active"] = False
    
    if "capture" in stream:
        stream["capture"].release()
    
    del active_streams[stream_id]
    
    logger.info(f"Stopped stream {stream_id}")
    
    return {"status": "stopped", "stream_id": stream_id}


@router.get("/stream/{stream_id}")
async def get_stream_feed(stream_id: str):
    """
    Get the live stream feed (MJPEG).
    
    This endpoint streams the processed video with bounding boxes overlaid,
    using the LangGraph pipeline for each frame.
    """
    if stream_id not in active_streams:
        raise HTTPException(status_code=404, detail="Stream not found")
    
    async def generate_frames():
        stream = active_streams[stream_id]
        cap = stream["capture"]
        
        frame_count = 0
        
        while stream["active"]:
            ret, frame = cap.read()
            
            if not ret:
                break
            
            frame_count += 1
            frame_id = f"{stream_id}_{frame_count}"
            
            # Encode frame to bytes
            is_success, buffer = cv2.imencode('.jpg', frame)
            if not is_success:
                continue
            
            frame_bytes = buffer.tobytes()
            
            # Analyze every Nth frame (e.g., every 10th frame to avoid overload)
            if frame_count % 10 == 0:
                try:
                    # Run through graph
                    result = await analyze_frame_async(
                        frame_id=frame_id,
                        frame_data=frame_bytes,
                        stream_id=stream_id
                    )
                    
                    # Draw bounding boxes on frame
                    detections = result.get("objects", [])
                    for det in detections:
                        bbox = det['bbox']
                        label = det['label']
                        confidence = det['confidence']
                        category = det.get('category', 'other')
                        
                        x1, y1, x2, y2 = int(bbox['x1']), int(bbox['y1']), int(bbox['x2']), int(bbox['y2'])
                        
                        # Color based on category
                        if category == 'weapon':
                            color = (0, 0, 255)  # Red
                        elif category == 'person':
                            color = (255, 255, 0)  # Cyan
                        else:
                            color = (0, 255, 0)  # Green
                        
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(frame, f"{label} {confidence:.2f}", (x1, y1 - 5),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                    
                    # Add verdict overlay
                    verdict = result.get("verdict", "SAFE")
                    violence_score = result.get("violence_score", 0.0)
                    
                    verdict_color = (0, 255, 0) if verdict == "SAFE" else (0, 0, 255)
                    cv2.putText(frame, f"{verdict} | Violence: {violence_score:.0%}", (10, 30),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, verdict_color, 2)
                    
                except Exception as e:
                    logger.error(f"Error analyzing stream frame: {e}")
            
            # Encode frame as JPEG
            _, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
            
            # Yield frame in MJPEG format
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
            await asyncio.sleep(0.033)  # ~30 FPS
    
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.post("/analyze-frame")
async def analyze_frame(
    frame: UploadFile = File(...),
    stream_id: str = "default",
    background_tasks: BackgroundTasks = None
):
    """
    Analyze a single frame from live feed using the LangGraph pipeline.
    
    This endpoint:
    1. Uses the same architecture as batch video processing
    2. Leverages the frame queue for backpressure and concurrency control
    3. Returns object detections, violence score, and policy verdict
    
    Returns:
        Analysis result with detections, verdict, and timing
    """
    try:
        # Read frame data
        contents = await frame.read()
        frame_id = str(uuid.uuid4())
        
        logger.debug(f"Received frame {frame_id} from stream {stream_id}")
        
        # Get queue
        queue = get_frame_queue(
            max_size=100,  # Max 100 frames in queue
            max_concurrent=5,  # Max 5 concurrent processes
            max_retries=2  # Retry failed frames twice
        )
        
        # Create frame object
        frame_obj = Frame(
            frame_id=frame_id,
            stream_id=stream_id,
            timestamp=time.time(),
            data=contents
        )
        
        # Try to enqueue
        enqueued = await queue.enqueue(frame_obj)
        
        if not enqueued:
            # Frame was dropped due to backpressure
            logger.warning(f"Frame {frame_id} dropped due to queue backpressure")
            return {
                "status": "dropped",
                "reason": "queue_full",
                "message": "Frame dropped due to high load. Try reducing frame rate.",
                "queue_metrics": queue.get_metrics()
            }
        
        # Process frame using LangGraph pipeline
        frame_obj = await queue.dequeue()
        
        if not frame_obj:
            raise HTTPException(status_code=500, detail="Failed to dequeue frame")
        
        try:
            # Run frame through the LangGraph pipeline
            result = await analyze_frame_async(
                frame_id=frame_obj.frame_id,
                frame_data=frame_obj.data,
                stream_id=frame_obj.stream_id,
                stream_metadata={"timestamp": frame_obj.timestamp}
            )
            
            # Add queue metrics to result
            result["queue_metrics"] = {
                "queue_size": queue.metrics["current_queue_size"],
                "processing": queue.metrics["current_processing"],
                "success_rate": f"{queue.get_metrics()['success_rate']:.1f}%"
            }
            
            # Mark as completed in queue
            queue.mark_completed(frame_obj.frame_id, result)
            
            logger.info(
                f"Frame {frame_id} processed: verdict={result.get('verdict')}, "
                f"objects={result.get('object_count')}, "
                f"violence={result.get('violence_score'):.2f}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing frame {frame_obj.frame_id}: {e}", exc_info=True)
            queue.mark_failed(frame_obj.frame_id, str(e))
            raise HTTPException(status_code=500, detail=str(e))
        
    except Exception as e:
        logger.error(f"Error in analyze_frame endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/streams")
async def list_active_streams():
    """List all active streams."""
    return {
        "streams": [
            {
                "stream_id": sid,
                "url": info["url"],
                "type": info["type"],
                "active": info["active"]
            }
            for sid, info in active_streams.items()
        ]
    }


@router.get("/queue/metrics")
async def get_queue_metrics():
    """Get queue performance metrics."""
    queue = get_frame_queue()
    return {
        "metrics": queue.get_metrics(),
        "configuration": {
            "max_size": queue.max_size,
            "max_concurrent": queue.max_concurrent,
            "max_retries": queue.max_retries,
            "drop_policy": queue.drop_policy
        },
        "current_state": {
            "queue_size": len(queue.queue),
            "processing": len(queue.processing),
            "completed_recent": len(queue.completed),
            "failed_recent": len(queue.failed)
        }
    }


@router.get("/queue/stream/{stream_id}")
async def get_stream_queue_stats(stream_id: str):
    """Get queue statistics for a specific stream."""
    queue = get_frame_queue()
    return queue.get_stream_stats(stream_id)


@router.delete("/queue/stream/{stream_id}")
async def clear_stream_queue(stream_id: str):
    """Clear queue for a specific stream."""
    queue = get_frame_queue()
    queue.clear_stream(stream_id)
    return {
        "status": "cleared",
        "stream_id": stream_id,
        "message": f"All frames for stream {stream_id} have been removed from queue"
    }
