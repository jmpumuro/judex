# SafeVid API Documentation

Complete API reference for the SafeVid child safety video analysis service.

## 🚀 Quick Links

- **[Interactive API Docs](http://localhost:8012/docs)** - Swagger UI (when service is running)
- **[Architecture](./ARCHITECTURE.md)** - System design and pipeline details
- **[Setup Guide](./SETUP.md)** - Installation and configuration
- **[Quick Reference](./QUICKREF.md)** - Common tasks and examples

## Base URL

```
http://localhost:8012/v1
```

## Table of Contents

- [Health & Status](#health--status)
- [Video Evaluation](#video-evaluation)
  - [Production Endpoint](#post-evaluate-production-endpoint) `/v1/evaluate` (Recommended)
  - [Legacy Endpoint](#post-evaluatesingle-legacy) `/v1/evaluate/single` (Deprecated)
- [Batch Processing](#batch-processing)
- [Results Persistence](#results-persistence)
- [Video Resources](#video-resources)
- [Policy Configuration](#policy-configuration)
- [Import Endpoints](#import-endpoints)
- [Checkpoint Management](#checkpoint-management)
- [SSE API](#sse-api-server-sent-events)
- [Response Schemas](#response-schemas)
- [Error Handling](#error-handling)

---

## Health & Status

### GET `/health`

Health check endpoint to verify service availability.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "models_loaded": true
}
```

**Status Codes:**
- `200` - Service is healthy
- `503` - Service unavailable

---

### GET `/models`

List all configured models and their cache status.

**Response:**
```json
{
  "models": [
    {
      "model_id": "openvision/yolo26-s",
      "model_type": "vision",
      "cached": true,
      "status": "ready"
    },
    {
      "model_id": "yolov8n.pt",
      "model_type": "vision_realtime",
      "cached": true,
      "status": "ready",
      "description": "YOLOE - Efficient real-time detection for live feeds"
    },
    {
      "model_id": "yolov8s-worldv2.pt",
      "model_type": "vision_openworld",
      "cached": true,
      "status": "ready",
      "description": "YOLO-World - Open-vocabulary detection for batch pipeline"
    },
    {
      "model_id": "microsoft/xclip-base-patch32-16-frames",
      "model_type": "violence",
      "cached": true,
      "status": "ready"
    },
    {
      "model_id": "openai/whisper-small",
      "model_type": "asr",
      "cached": true,
      "status": "ready"
    },
    {
      "model_id": "tarekziade/pardonmyai",
      "model_type": "moderation",
      "cached": true,
      "status": "ready"
    },
    {
      "model_id": "facebook/bart-large-mnli",
      "model_type": "moderation",
      "cached": true,
      "status": "ready"
    }
  ]
}
```

---

## Video Evaluation

### POST `/evaluate` (Production Endpoint)

**🎯 Recommended for production use**

The primary endpoint for video safety evaluation. Accepts video file OR URL and returns complete verdict with evidence.

**Content-Type:** `multipart/form-data`

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `video` | File | Optional* | Video file upload (MP4, AVI, MOV, MKV, WEBM) |
| `url` | String | Optional* | Video URL (alternative to file upload) |
| `policy` | String | Optional | JSON string with custom policy configuration |

*Either `video` or `url` must be provided, but not both.

**Examples:**

```bash
# Upload file
curl -X POST http://localhost:8012/v1/evaluate \
  -F "video=@video.mp4"

# From URL
curl -X POST http://localhost:8012/v1/evaluate \
  -F "url=https://example.com/video.mp4"

# With custom strict policy
curl -X POST http://localhost:8012/v1/evaluate \
  -F "video=@video.mp4" \
  -F 'policy={"thresholds":{"unsafe":{"violence":0.60,"sexual":0.45}}}'
```

**Python Example:**

```python
import requests

# Simple file upload
response = requests.post(
    'http://localhost:8012/v1/evaluate',
    files={'video': open('video.mp4', 'rb')}
)

result = response.json()
print(f"Verdict: {result['verdict']}")
print(f"Violence: {result['scores']['violence']*100:.1f}%")
```

**Response:**

```json
{
  "status": "success",
  "verdict": "SAFE|CAUTION|UNSAFE|NEEDS_REVIEW",
  "confidence": 0.85,
  "processing_time_sec": 45.2,
  "scores": {
    "violence": 0.15,
    "sexual": 0.05,
    "hate": 0.02,
    "drugs": 0.08,
    "profanity": 0.12
  },
  "evidence": {
    "video_metadata": {
      "duration": 120.5,
      "fps": 30.0,
      "resolution": "1920x1080",
      "has_audio": true
    },
    "object_detections": {
      "total_frames_analyzed": 120,
      "detections": [...]
    },
    "violence_segments": [...],
    "audio_transcript": [...],
    "ocr_results": [...],
    "moderation_flags": [...]
  },
  "summary": "AI-generated markdown summary...",
  "model_versions": {...},
  "policy_applied": {...}
}
```

**Verdict Types:**

- `SAFE` - Content is safe for all audiences
- `CAUTION` - Content has minor concerns, review recommended
- `UNSAFE` - Content violates safety policies
- `NEEDS_REVIEW` - Ambiguous content requiring manual review

**Status Codes:**

- `200` - Success
- `400` - Invalid parameters or missing required fields
- `500` - Processing error

**Performance:**

- Typical processing time: 30-60 seconds for a 2-minute video
- Max file size: 500MB
- Supported formats: MP4, AVI, MOV, MKV, WEBM

---

### POST `/evaluate/single` (Legacy)

**⚠️ DEPRECATED**: Use `/v1/evaluate` instead

Legacy endpoint with SSE/WebSocket tracking support. Used internally by the UI for real-time progress updates.

**Request:**

Content-Type: `multipart/form-data`

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | File | Yes | Video file (MP4, AVI, MOV, etc.) |
| `video_id` | String | No | Video ID for SSE/WebSocket tracking |
| `policy` | String | No | JSON string with policy overrides |

**Response:** See [VideoEvaluationResponse](#videoevaluationresponse)

---

## Batch Processing

### POST `/evaluate/batch`

Evaluate multiple videos in a single batch.

**Request:**

Content-Type: `multipart/form-data`

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `files` | File[] | Yes | Multiple video files |
| `policy` | String | No | JSON string with policy overrides (applies to all videos) |

**Example (cURL):**
```bash
curl -X POST http://localhost:8012/v1/evaluate/batch \
  -F "files=@video1.mp4" \
  -F "files=@video2.mp4" \
  -F "files=@video3.mp4" \
  | jq .
```

**Example (Python):**
```python
import requests

files = [
    ('files', ('video1.mp4', open('video1.mp4', 'rb'), 'video/mp4')),
    ('files', ('video2.mp4', open('video2.mp4', 'rb'), 'video/mp4')),
    ('files', ('video3.mp4', open('video3.mp4', 'rb'), 'video/mp4')),
]

response = requests.post(
    "http://localhost:8012/v1/evaluate/batch",
    files=files
)

batch_info = response.json()
print(f"Batch ID: {batch_info['batch_id']}")
print(f"Total Videos: {batch_info['total_videos']}")
```

**Response:**
```json
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "total_videos": 3,
  "videos": [
    {
      "video_id": "123e4567-e89b-12d3-a456-426614174000",
      "filename": "video1.mp4",
      "status": "queued",
      "progress": 0,
      "current_stage": null,
      "result": null
    },
    {
      "video_id": "123e4567-e89b-12d3-a456-426614174001",
      "filename": "video2.mp4",
      "status": "queued",
      "progress": 0,
      "current_stage": null,
      "result": null
    }
  ]
}
```

---

### GET `/evaluate/batch/{batch_id}`

Get status and results for a batch of videos.

**Path Parameters:**
- `batch_id` (string, required) - The batch ID returned from POST `/evaluate/batch`

**Example:**
```bash
curl http://localhost:8012/v1/evaluate/batch/550e8400-e29b-41d4-a716-446655440000 | jq .
```

**Response:**
```json
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "total_videos": 3,
  "completed": 3,
  "failed": 0,
  "videos": {
    "123e4567-e89b-12d3-a456-426614174000": {
      "video_id": "123e4567-e89b-12d3-a456-426614174000",
      "filename": "video1.mp4",
      "status": "completed",
      "progress": 100,
      "current_stage": "complete",
      "result": {
        /* VideoEvaluationResponse object */
      }
    }
  }
}
```

**Batch Status Values:**
- `processing` - Batch is being processed
- `completed` - All videos completed
- `partial` - Some videos completed, some failed

**Video Status Values:**
- `queued` - Waiting to be processed
- `processing` - Currently being analyzed
- `completed` - Successfully completed
- `failed` - Processing failed

**Status Codes:**
- `200` - Success
- `404` - Batch not found

---

## Results Persistence

### POST `/results/save`

Save analysis results to persistent storage.

**Request:**
```json
{
  "results": [
    {
      "id": "video-uuid",
      "filename": "video.mp4",
      "verdict": "UNSAFE",
      "result": {
        /* Full VideoEvaluationResponse */
      },
      "timestamp": "2026-01-26T10:30:00Z"
    }
  ]
}
```

**Response:**
```json
{
  "message": "Saved 1 result(s)",
  "count": 1
}
```

---

### GET `/results/load`

Load all saved results from persistent storage.

**Response:**
```json
{
  "results": [
    {
      "id": "video-uuid",
      "filename": "video.mp4",
      "verdict": "UNSAFE",
      "result": { /* ... */ },
      "timestamp": "2026-01-26T10:30:00Z"
    }
  ],
  "count": 1
}
```

---

### DELETE `/results/{video_id}`

Delete a specific saved result.

**Path Parameters:**
- `video_id` (string, required) - The video ID to delete

**Response:**
```json
{
  "message": "Result deleted"
}
```

---

### DELETE `/results`

Clear all saved results.

**Response:**
```json
{
  "message": "All results cleared"
}
```

---

## Video Resources

### GET `/video/labeled/{video_id}`

Download the labeled video with bounding boxes.

**Path Parameters:**
- `video_id` (string, required) - The video ID from evaluation results

**Response:** Binary video file (MP4, H.264)

**Example:**
```bash
curl -O http://localhost:8012/v1/video/labeled/550e8400-e29b-41d4-a716-446655440000
```

**Status Codes:**
- `200` - Success
- `404` - Video not found

---

### GET `/video/uploaded/{video_id}`

Download the original uploaded video file.

**Path Parameters:**
- `video_id` (string, required) - The batch video ID

**Response:** Binary video file (original format)

**Example:**
```bash
curl -O http://localhost:8012/v1/video/uploaded/V_101_abc123
```

**Status Codes:**
- `200` - Success
- `404` - Video not found

---

## SSE API (Server-Sent Events)

### GET `/sse/{video_id}`

Real-time progress updates for a video being processed using Server-Sent Events (one-way server-to-client stream).

**Connection:**
```javascript
const eventSource = new EventSource(`http://localhost:8012/v1/sse/${video_id}`);

eventSource.onmessage = (event) => {
  const update = JSON.parse(event.data);
  console.log(`Stage: ${update.stage}, Progress: ${update.progress}%`);
  
  if (update.stage === 'complete') {
    eventSource.close();
  }
};

eventSource.onerror = (error) => {
  console.error('SSE error:', error);
  eventSource.close();
};
```

**Message Format (Server → Client):**
```json
{
  "stage": "yolo26_vision",
  "progress": 30,
  "message": "Analyzing frames with YOLO26...",
  "stage_output": {
    /* Optional stage-specific output */
  }
}
```

**Pipeline Stages:**
1. `ingest_video` (6-8%)
2. `segment_video` (13-18%)
3. `yolo26_vision` (27-29%)
4. `yoloworld_vision` (33-34%)
5. `violence_detection` (46-50%)
6. `audio_transcription` (60-62%)
7. `ocr_extraction` (71-73%)
8. `text_moderation` (82-83%)
9. `policy_fusion` (94-95%)
10. `report_generation` (100%)
11. `finalize` (100%)
12. `complete` (100%)

**Connection Lifecycle:**
1. Client connects with video ID via EventSource
2. Server sends progress updates as processing occurs
3. Final update with `stage: "complete"`
4. Server closes connection

**Note:** SSE is preferred over WebSocket for one-way real-time updates as it's simpler and has automatic reconnection built-in.

---

## Response Schemas

### VideoEvaluationResponse

Complete structure of video evaluation results:

```json
{
  "verdict": "UNSAFE | CAUTION | SAFE",
  
  "criteria": {
    "violence": {
      "score": 0.88,
      "status": "violation | caution | ok",
      "evidence_count": 3,
      "sources": ["vision", "violence_model"]
    },
    "profanity": {
      "score": 0.12,
      "status": "ok",
      "evidence_count": 0,
      "sources": []
    },
    "sexual": {
      "score": 0.05,
      "status": "ok",
      "evidence_count": 0,
      "sources": []
    },
    "drugs": {
      "score": 0.41,
      "status": "caution",
      "evidence_count": 1,
      "sources": ["vision"]
    },
    "hate": {
      "score": 0.02,
      "status": "ok",
      "evidence_count": 0,
      "sources": []
    }
  },
  
  "violations": [
    {
      "criterion": "violence",
      "severity": "high | medium | low",
      "timestamp_ranges": [[31.2, 38.9], [45.0, 52.3]],
      "evidence_refs": ["violence_segment_004", "vision_detection_042"],
      "evidence_summary": "High violence detected in multiple segments"
    }
  ],
  
  "evidence": {
    "vision": [
      {
        "frame_index": 42,
        "timestamp": 42.0,
        "detections": [
          {
            "class": "knife",
            "confidence": 0.92,
            "bbox": [120, 340, 180, 420],
            "criterion": "violence"
          }
        ]
      }
    ],
    
    "violence_segments": [
      {
        "segment_id": 4,
        "start_time": 31.2,
        "end_time": 34.2,
        "violence_score": 0.88,
        "frame_indices": [31, 32, 33, 34]
      }
    ],
    
    "asr": {
      "full_text": "Complete video transcript...",
      "language": "en",
      "chunks": [
        {
          "text": "Transcribed speech segment",
          "start_time": 10.5,
          "end_time": 14.2
        }
      ]
    },
    
    "ocr": [
      {
        "frame_index": 120,
        "timestamp": 120.0,
        "text": "Combined detected text",
        "detections": [
          {
            "text": "Specific text",
            "confidence": 0.95,
            "bbox": [200, 100, 400, 150]
          }
        ]
      }
    ],
    
    "moderation": {
      "profanity_segments": [
        {
          "text": "inappropriate language",
          "score": 0.89,
          "source": "asr | ocr",
          "timestamp": 45.2
        }
      ],
      "sexual_segments": [],
      "hate_segments": [],
      "drugs_segments": []
    }
  },
  
  "transcript": {
    "full_text": "Complete transcript...",
    "chunks": [ /* ... */ ]
  },
  
  "report": "AI-generated human-friendly summary (if OpenAI configured)",
  
  "labeled_video_path": "/tmp/safevid/work_xyz/labeled.mp4",
  
  "metadata": {
    "video_id": "550e8400-e29b-41d4-a716-446655440000",
    "duration": 120.5,
    "fps": 30.0,
    "width": 1920,
    "height": 1080,
    "has_audio": true,
    "frames_analyzed": 120,
    "segments_analyzed": 40,
    "detections_count": 15,
    "violence_segments_count": 2,
    "ocr_results_count": 8,
    "processing_time": 45.2
  },
  
  "timings": {
    "total_seconds": 45.2,
    "ingest_video": 1.2,
    "segment_video": 3.5,
    "yolo26_vision": 12.8,
    "violence_detection": 18.4,
    "audio_transcription": 5.3,
    "ocr_extraction": 2.1,
    "text_moderation": 0.8,
    "policy_fusion": 0.3,
    "report_generation": 0.6,
    "finalize": 0.2
  }
}
```

### Verdict Values

- **UNSAFE**: Video violates child safety criteria and should be blocked
- **CAUTION**: Video contains concerning content requiring review
- **SAFE**: Video is appropriate for children

### Criterion Status Values

- **violation**: Score exceeds unsafe threshold
- **caution**: Score exceeds caution threshold but not unsafe
- **ok**: Score below caution threshold

---

## Error Handling

### Error Response Format

```json
{
  "detail": "Error message",
  "error_type": "ValidationError | ProcessingError | NotFoundError"
}
```

### Common Error Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 400 | Bad Request | Invalid file format, missing required fields |
| 404 | Not Found | Batch ID or video ID not found |
| 413 | Payload Too Large | Video file exceeds size limit |
| 422 | Unprocessable Entity | Invalid JSON in policy parameter |
| 500 | Internal Server Error | Model loading error, processing failure |
| 503 | Service Unavailable | Service not ready, models not loaded |

### Example Error Response

```json
{
  "detail": "Unsupported video format. Supported formats: mp4, avi, mov, mkv",
  "error_type": "ValidationError"
}
```

---

## Policy Override Structure

Override default thresholds and processing parameters per request:

```json
{
  "thresholds": {
    "unsafe": {
      "violence": 0.75,
      "sexual": 0.60,
      "hate": 0.60,
      "drugs": 0.70,
      "profanity": 0.80
    },
    "caution": {
      "violence": 0.40,
      "sexual": 0.30,
      "hate": 0.30,
      "drugs": 0.40,
      "profanity": 0.40
    }
  },
  "weights": {
    "violence": 1.5,
    "sexual": 1.2,
    "hate": 1.0,
    "drugs": 1.0,
    "profanity": 0.8
  },
  "sampling_fps": 1.0,
  "segment_duration": 3.0,
  "ocr_interval": 2.0
}
```

---

## Rate Limits

Currently no rate limits are enforced in development mode. For production deployment, consider:

- Max concurrent batch jobs: Configurable
- Max videos per batch: Unlimited (adjust based on resources)
- Max file size: 500MB (configurable)
- WebSocket connection timeout: 1 hour

---

## Best Practices

1. **Batch Processing**: Use batch endpoint for multiple videos to leverage parallel processing
2. **WebSocket Monitoring**: Connect to WebSocket before starting processing for real-time updates
3. **Result Persistence**: Save important results using persistence API for audit trails
4. **Error Handling**: Always check response status codes and handle errors gracefully
5. **Resource Cleanup**: Labeled videos are temporary; download immediately if needed
6. **Policy Overrides**: Use sparingly; default thresholds are tuned for safety

---

## Examples

### Complete Workflow Example (Python)

```python
import requests
import json
import websocket
import threading

API_URL = "http://localhost:8012/v1"

# 1. Submit batch for processing
files = [
    ('files', ('video1.mp4', open('video1.mp4', 'rb'), 'video/mp4')),
    ('files', ('video2.mp4', open('video2.mp4', 'rb'), 'video/mp4')),
]

response = requests.post(f"{API_URL}/evaluate/batch", files=files)
batch = response.json()
batch_id = batch['batch_id']

print(f"Batch submitted: {batch_id}")

# 2. Connect WebSocket for first video
video_id = batch['videos'][0]['video_id']

def on_message(ws, message):
    data = json.loads(message)
    print(f"Progress: {data['progress']}% - {data['stage']}")

def on_error(ws, error):
    print(f"WebSocket error: {error}")

ws = websocket.WebSocketApp(
    f"ws://localhost:8012/v1/ws/{video_id}",
    on_message=on_message,
    on_error=on_error
)

threading.Thread(target=ws.run_forever, daemon=True).start()

# 3. Poll for batch completion
import time
while True:
    response = requests.get(f"{API_URL}/evaluate/batch/{batch_id}")
    batch_status = response.json()
    
    if batch_status['status'] == 'completed':
        break
    
    time.sleep(5)

# 4. Process results
for video_id, video_data in batch_status['videos'].items():
    result = video_data['result']
    print(f"\n{video_data['filename']}: {result['verdict']}")
    
    # Download labeled video
    if 'labeled_video_path' in result:
        labeled_response = requests.get(f"{API_URL}/video/labeled/{video_id}")
        with open(f"labeled_{video_data['filename']}", 'wb') as f:
            f.write(labeled_response.content)
    
    # Save results
    save_data = {
        "results": [{
            "id": video_id,
            "filename": video_data['filename'],
            "verdict": result['verdict'],
            "result": result,
            "timestamp": "2026-01-26T10:30:00Z"
        }]
    }
    requests.post(f"{API_URL}/results/save", json=save_data)

print("\nBatch processing complete!")
```

---

For more information, see the [main README](../README.md) or [Setup Guide](SETUP.md).
