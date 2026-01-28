# Judex API Documentation

Complete API reference for the Judex video evaluation framework.

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
- [Evaluation API](#evaluation-api)
- [Criteria Management](#criteria-management)
- [Video & Artifacts](#video--artifacts)
- [SSE Events](#sse-events)
- [Live Feed](#live-feed)
- [Response Schemas](#response-schemas)
- [Error Handling](#error-handling)

---

## Health & Status

### GET `/v1/health`

Health check endpoint to verify service availability.

**Response:**
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "models_loaded": true
}
```

### GET `/v1/models`

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
      "model_id": "microsoft/xclip-base-patch32-16-frames",
      "model_type": "violence",
      "cached": true,
      "status": "ready"
    }
  ]
}
```

---

## Evaluation API

### POST `/v1/evaluate`

**Main evaluation endpoint.** Submit a video for evaluation with optional criteria.

**Request (multipart/form-data):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `video` | file | Yes* | Video file to evaluate |
| `url` | string | Yes* | URL to video (alternative to file) |
| `preset_id` | string | No | Use a preset criteria (e.g., `child_safety`) |
| `criteria` | string | No | Inline YAML/JSON criteria definition |

*Either `video` or `url` is required.

**Examples:**

```bash
# Basic evaluation with default criteria
curl -X POST http://localhost:8012/v1/evaluate \
  -F "video=@video.mp4"

# With preset
curl -X POST http://localhost:8012/v1/evaluate \
  -F "video=@video.mp4" \
  -F "preset_id=child_safety"

# With custom criteria (inline YAML)
curl -X POST http://localhost:8012/v1/evaluate \
  -F "video=@video.mp4" \
  -F 'criteria=name: custom
version: "1.0"
criteria:
  - id: violence
    weight: 1.0
    threshold: 0.5'

# From URL
curl -X POST http://localhost:8012/v1/evaluate \
  -F "url=https://example.com/video.mp4"
```

**Response:**
```json
{
  "evaluation_id": "abc123",
  "status": "processing",
  "created_at": "2026-01-28T12:00:00Z",
  "items": [
    {
      "id": "item-456",
      "filename": "video.mp4",
      "status": "processing",
      "current_stage": "ingest",
      "progress": 10
    }
  ]
}
```

---

### GET `/v1/evaluations`

List all evaluations with optional filtering.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 20 | Maximum results to return |
| `offset` | int | 0 | Pagination offset |
| `status` | string | - | Filter by status (`pending`, `processing`, `completed`, `failed`) |

**Response:**
```json
{
  "evaluations": [
    {
      "id": "abc123",
      "status": "completed",
      "created_at": "2026-01-28T12:00:00Z",
      "items": [...]
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

---

### GET `/v1/evaluations/{evaluation_id}`

Get detailed evaluation status and results.

**Response (completed):**
```json
{
  "id": "abc123",
  "status": "completed",
  "criteria_id": "child_safety",
  "created_at": "2026-01-28T12:00:00Z",
  "completed_at": "2026-01-28T12:05:00Z",
  "items": [
    {
      "id": "item-456",
      "filename": "video.mp4",
      "status": "completed",
      "current_stage": "completed",
      "progress": 100,
      "result": {
        "verdict": "UNSAFE",
        "confidence": 0.87,
        "criteria_scores": {
          "violence": {
            "score": 0.85,
            "verdict": "UNSAFE",
            "label": "Violence Detection",
            "severity": "high"
          },
          "profanity": {
            "score": 0.12,
            "verdict": "SAFE",
            "label": "Profanity Detection",
            "severity": "low"
          }
        },
        "violations": [...],
        "processing_time": 45.2,
        "report": "AI-generated summary..."
      },
      "uploaded_video_path": "uploaded/item-456/video.mp4",
      "labeled_video_path": "labeled/item-456/labeled.mp4",
      "stage_outputs": {...}
    }
  ]
}
```

---

### DELETE `/v1/evaluations/{evaluation_id}`

Delete an evaluation and all associated artifacts.

**Response:**
```json
{
  "status": "deleted",
  "evaluation_id": "abc123"
}
```

---

### GET `/v1/evaluations/{evaluation_id}/stages`

List all stages and their status for an evaluation.

**Response:**
```json
{
  "evaluation_id": "abc123",
  "item_id": "item-456",
  "stages": {
    "ingest": {"status": "completed", "progress": 100},
    "segment": {"status": "completed", "progress": 100},
    "yolo26": {"status": "completed", "progress": 100},
    "violence": {"status": "processing", "progress": 50}
  }
}
```

---

### GET `/v1/evaluations/{evaluation_id}/stages/{stage}`

Get detailed output for a specific stage.

**Query Parameters:**
- `item_id` (optional): Specific item ID

**Response:**
```json
{
  "stage": "yolo26",
  "status": "completed",
  "output": {
    "total_detections": 142,
    "unique_classes": ["person", "car", "dog"],
    "frames_processed": 30,
    "high_confidence_detections": [
      {
        "class": "person",
        "confidence": 0.95,
        "frame_index": 5,
        "timestamp": 2.5
      }
    ]
  }
}
```

---

## Criteria Management

### GET `/v1/criteria/presets`

List available built-in presets.

**Response:**
```json
{
  "presets": [
    {
      "id": "child_safety",
      "name": "Child Safety",
      "description": "Comprehensive child safety evaluation"
    },
    {
      "id": "content_moderation", 
      "name": "Content Moderation",
      "description": "General content moderation"
    },
    {
      "id": "violence_detection",
      "name": "Violence Detection",
      "description": "Focused violence detection"
    }
  ]
}
```

---

### GET `/v1/criteria/presets/{preset_id}`

Get preset details and schema.

**Response:**
```json
{
  "id": "child_safety",
  "name": "Child Safety",
  "description": "Comprehensive child safety evaluation",
  "content": "name: Child Safety\nversion: \"1.0\"\ncriteria:\n  - id: violence\n    ..."
}
```

---

### GET `/v1/criteria/presets/{preset_id}/export`

Export preset as YAML file.

**Response:** YAML content with `Content-Type: application/x-yaml`

---

### GET `/v1/criteria/custom`

List user-defined custom criteria.

**Response:**
```json
{
  "criteria": [
    {
      "id": "my-criteria-123",
      "name": "My Custom Criteria",
      "created_at": "2026-01-28T12:00:00Z"
    }
  ]
}
```

---

### POST `/v1/criteria/custom`

Create a new custom criteria.

**Request (multipart/form-data):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | string | Yes | YAML or JSON criteria definition |

**Response:**
```json
{
  "id": "custom-abc123",
  "name": "My Custom Criteria",
  "status": "valid"
}
```

---

### POST `/v1/criteria/validate`

Validate criteria without saving.

**Request (multipart/form-data):**
- `content`: YAML/JSON criteria definition

**Response:**
```json
{
  "valid": true,
  "criteria": {
    "name": "My Criteria",
    "version": "1.0",
    "criteria": [...]
  }
}
```

Or with errors:
```json
{
  "valid": false,
  "errors": ["Missing required field: criteria"]
}
```

---

## Video & Artifacts

### GET `/v1/evaluations/{evaluation_id}/artifact/{artifact_type}`

Stream video artifact (original or labeled).

**Path Parameters:**
- `artifact_type`: `uploaded` or `labeled`

**Query Parameters:**
- `item_id` (optional): Specific item ID
- `stream` (optional): `true` for streaming response

**Response:** Video stream (`video/mp4`)

---

### GET `/v1/evaluations/{evaluation_id}/frames`

List processed frames with pagination.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `item_id` | string | - | Specific item ID |
| `page` | int | 1 | Page number |
| `page_size` | int | 50 | Items per page (max 200) |
| `thumbnails` | bool | true | Return thumbnail URLs |

**Response:**
```json
{
  "evaluation_id": "abc123",
  "item_id": "item-456",
  "frames": [
    {
      "id": "frame_00001_1500",
      "index": 1,
      "timestamp": 1.5,
      "url": "/v1/evaluations/abc123/frames/frame_00001_1500?..."
    }
  ],
  "total": 120,
  "page": 1,
  "page_size": 50,
  "total_pages": 3
}
```

---

### GET `/v1/evaluations/{evaluation_id}/frames/{filename}`

Get a specific frame image.

**Query Parameters:**
- `item_id`: Item ID
- `stream`: `true` for streaming
- `thumbnails`: `true` for thumbnail version

**Response:** JPEG image

---

## SSE Events

### GET `/v1/evaluations/{evaluation_id}/events`

Subscribe to real-time evaluation progress via Server-Sent Events.

**Response (SSE stream):**
```
event: progress
data: {"evaluation_id":"abc123","item_id":"item-456","stage":"yolo26","progress":50,"message":"Processing frames..."}

event: stage_complete
data: {"evaluation_id":"abc123","item_id":"item-456","stage":"yolo26","output":{...}}

event: complete
data: {"evaluation_id":"abc123","item_id":"item-456","result":{...}}

event: error
data: {"evaluation_id":"abc123","error":"Processing failed"}
```

**Example:**
```bash
curl -N http://localhost:8012/v1/evaluations/abc123/events
```

---

## Live Feed

### POST `/v1/live/start`

Start live feed analysis.

**Request:**
```json
{
  "source": "webcam",
  "detection_interval": 1.0
}
```

---

### POST `/v1/live/stop`

Stop live feed analysis.

---

### GET `/v1/live/status`

Get current live feed status.

---

### GET `/v1/live/events`

Get recent live feed events.

---

## Response Schemas

### Evaluation Result

```json
{
  "verdict": "SAFE|CAUTION|UNSAFE",
  "confidence": 0.0-1.0,
  "criteria_scores": {
    "<criterion_id>": {
      "score": 0.0-1.0,
      "verdict": "SAFE|CAUTION|UNSAFE",
      "label": "Human-readable label",
      "severity": "low|medium|high"
    }
  },
  "violations": [
    {
      "category": "violence",
      "score": 0.85,
      "timestamp": 12.5,
      "evidence": "Person detected with aggressive behavior"
    }
  ],
  "processing_time": 45.2,
  "report": "Optional AI-generated summary"
}
```

### Criteria Schema

```yaml
name: string (required)
version: string (required)
description: string (optional)
criteria:
  - id: string (required)
    label: string (optional)
    description: string (optional)
    weight: float (0.0-1.0, default: 1.0)
    threshold: float (0.0-1.0, default: 0.5)
    keywords: list[string] (optional)
fusion:
  strategy: weighted_average|max|min|custom (default: weighted_average)
verdict:
  strategy: threshold|majority|any (default: threshold)
  safe_threshold: float (default: 0.3)
  unsafe_threshold: float (default: 0.7)
```

---

## Error Handling

### Error Response Format

```json
{
  "detail": "Error message",
  "status_code": 400
}
```

### Common Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request (invalid input) |
| 404 | Not Found |
| 422 | Validation Error |
| 500 | Internal Server Error |
| 503 | Service Unavailable |

### Validation Errors

```json
{
  "detail": [
    {
      "loc": ["body", "video"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## Rate Limits

No rate limits are enforced by default. For production deployments, consider adding rate limiting at the reverse proxy level.

---

## Authentication

Authentication is not enabled by default. For production, implement authentication via:
- API keys in headers
- OAuth2/JWT tokens
- Reverse proxy authentication

---

**For architecture details, see [ARCHITECTURE.md](ARCHITECTURE.md). For setup instructions, see [SETUP.md](SETUP.md).**
