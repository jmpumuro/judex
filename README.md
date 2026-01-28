# Judex - Generic Video Evaluation Framework

![Version](https://img.shields.io/badge/version-2.0.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**Judex** is a flexible, pluggable video content evaluation framework that allows users to define custom evaluation criteria via YAML/JSON configuration. It uses state-of-the-art AI models including YOLO26, YOLO-World, X-CLIP, Whisper, and text moderation models to provide deterministic verdicts with detailed evidence.

The framework comes with built-in presets (Child Safety, General Moderation, Brand Safety) but supports fully custom evaluation criteria for any use case.

## 🎯 Features

- **Generic Evaluation**: Define custom criteria, thresholds, and scoring via YAML/JSON
- **Built-in Presets**: Child Safety (default), General Moderation, Brand Safety
- **Pluggable Pipeline**: Stage-based architecture supports custom detectors
- **Production API**: Single `/v1/evaluate` endpoint - upload video, get verdict with evidence
- **Real-Time Progress**: SSE-based live updates with early video/frame access
- **Batch Processing**: Process multiple videos with individual progress tracking
- **Live Feed Analysis**: Real-time camera/stream processing with YOLOE detection
- **Multi-Modal Analysis**: 
  - Visual detection (YOLO26, YOLO-World)
  - Violence detection (X-CLIP)
  - Audio transcription (Whisper)
  - OCR and text moderation
- **Industry-Standard Storage**:
  - PostgreSQL for metadata and results
  - MinIO (S3-compatible) for video/frame storage
  - Thumbnail generation for fast filmstrip display
  - Paginated frame API
- **Early Access**: View original video immediately after upload, frames after segmentation
- **Deterministic Verdicts**: Policy-based scoring ensures consistent, explainable results
- **Labeled Video Output**: Annotated videos with bounding boxes, uploaded immediately

## 📋 Evaluation Criteria

Criteria are defined via YAML/JSON configuration. Example:

```yaml
name: "My Custom Criteria"
version: "1.0"
criteria:
  - id: violence
    label: "Violence & Aggression"
    description: "Fights, weapons, aggressive behavior"
    threshold: 0.6
    severity: high
  - id: profanity
    label: "Profanity"
    threshold: 0.4
    severity: medium
settings:
  verdict_strategy: threshold_based
  generate_labeled_video: true
```

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    React Frontend (Port 5173)                 │
│   - Video Upload & Preview    - Real-time Stage Updates      │
│   - Criteria Configuration    - Filmstrip Frame Gallery      │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                FastAPI Backend (Port 8012)                    │
│                                                               │
│  POST /v1/evaluate          →  Submit evaluation              │
│  GET  /v1/evaluations/{id}  →  Get status/results             │
│  GET  /v1/evaluations/{id}/events  →  SSE progress stream     │
│  GET  /v1/evaluations/{id}/frames  →  Paginated frames        │
│  GET  /v1/criteria/*        →  Manage presets & custom        │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│              LangGraph Pipeline (Stable Graph)                │
│                                                               │
│  ingest_video → segment_video → run_pipeline → fuse_policy   │
│                                      │                        │
│                         ┌────────────┴────────────┐          │
│                         │    PipelineRunner       │          │
│                         │  (Dynamic Stage Exec)   │          │
│                         │                         │          │
│                         │  ┌─────────────────┐   │          │
│                         │  │  StagePlugins   │   │          │
│                         │  │  - yolo26       │   │          │
│                         │  │  - yoloworld    │   │          │
│                         │  │  - violence     │   │          │
│                         │  │  - whisper      │   │          │
│                         │  │  - ocr          │   │          │
│                         │  │  - moderation   │   │          │
│                         │  └─────────────────┘   │          │
│                         └────────────────────────┘          │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────┐    ┌─────────────────┐    ┌────────────────┐
│   PostgreSQL    │    │     MinIO       │    │    Outputs     │
│   - Evaluations │    │   - Videos      │    │  - JSON Result │
│   - Results     │    │   - Frames      │    │  - Labeled MP4 │
│   - Criteria    │    │   - Thumbnails  │    │  - Evidence    │
└─────────────────┘    └─────────────────┘    └────────────────┘
```

### Pipeline Architecture

**Stable LangGraph** with dynamic stage execution:

1. **ingest_video**: Validate, normalize to 720p@30fps, upload to MinIO immediately
2. **segment_video**: Extract keyframes (1fps), generate thumbnails, upload to MinIO
3. **run_pipeline**: Dynamic execution via PipelineRunner based on criteria
4. **fuse_policy**: Compute scores using configured fusion strategy, determine verdict
5. **llm_report**: Optional AI-generated summary

**StagePlugin System** (pluggable detectors):
- `yolo26` - Object detection (weapons, substances, persons)
- `yoloworld` - Open-vocabulary detection for custom objects
- `violence` - X-CLIP based violence/aggression detection
- `whisper` - Audio transcription (multilingual)
- `ocr` - Text extraction from frames
- `text_moderation` - Profanity, hate speech, sexual content detection

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose
- 8GB+ RAM recommended

### Running with Docker

```bash
# Clone and run
git clone <repository-url>
cd judex
docker-compose -f docker/docker-compose.yml up --build

# Services:
# - API: http://localhost:8012
# - UI:  http://localhost:5173
# - MinIO Console: http://localhost:9001
```

### Using the Web UI

1. Open http://localhost:5173
2. Select evaluation criteria (preset or custom)
3. Upload videos (drag & drop or click +)
4. Click **EVALUATE** to start processing
5. Watch real-time progress - video appears after ingest, frames after segment
6. Click stages to view detailed outputs
7. Toggle between Original/Labeled video

### API Usage

```bash
# Health check
curl http://localhost:8012/v1/health

# Evaluate with preset
curl -X POST http://localhost:8012/v1/evaluate \
  -F "files=@video.mp4" \
  -F "criteria_id=child_safety"

# Evaluate with custom criteria (YAML)
curl -X POST http://localhost:8012/v1/evaluate \
  -F "files=@video.mp4" \
  -F "criteria=@my_criteria.yaml"

# Get evaluation status/results
curl http://localhost:8012/v1/evaluations/{id}

# Stream progress (SSE)
curl http://localhost:8012/v1/evaluations/{id}/events

# List frames (paginated, thumbnails)
curl "http://localhost:8012/v1/evaluations/{id}/frames?page=1&page_size=50"

# Get video artifact
curl "http://localhost:8012/v1/evaluations/{id}/artifacts/labeled_video?stream=true"
```

## 📡 API Reference

### Evaluation Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/evaluate` | Submit evaluation (single or batch) |
| GET | `/v1/evaluations/{id}` | Get evaluation status and results |
| GET | `/v1/evaluations/{id}/events` | SSE progress stream |
| GET | `/v1/evaluations/{id}/stages` | List all stage outputs |
| GET | `/v1/evaluations/{id}/stages/{stage}` | Get specific stage output |
| GET | `/v1/evaluations/{id}/frames` | List frames (paginated) |
| GET | `/v1/evaluations/{id}/frames/{filename}` | Get frame image |
| GET | `/v1/evaluations/{id}/thumbnails/{filename}` | Get thumbnail image |
| GET | `/v1/evaluations/{id}/artifacts/{type}` | Get artifact (video, thumbnail) |
| DELETE | `/v1/evaluations/{id}` | Delete evaluation and artifacts |
| GET | `/v1/evaluations` | List recent evaluations |

### Criteria Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/criteria/presets` | List built-in presets |
| GET | `/v1/criteria/presets/{id}` | Get preset details |
| GET | `/v1/criteria/presets/{id}/export` | Export preset as YAML/JSON |
| GET | `/v1/criteria/custom` | List custom criteria |
| POST | `/v1/criteria` | Save custom criteria |
| GET | `/v1/criteria/custom/{id}` | Get custom criteria |
| DELETE | `/v1/criteria/custom/{id}` | Delete custom criteria |
| POST | `/v1/criteria/validate` | Validate criteria config |

### Response Structure

```json
{
  "id": "abc123",
  "status": "completed",
  "items": [{
    "id": "item123",
    "filename": "video.mp4",
    "status": "completed",
    "result": {
      "verdict": "UNSAFE",
      "confidence": 0.85,
      "criteria_scores": {
        "violence": {"score": 0.78, "verdict": "UNSAFE", "severity": "high"},
        "profanity": {"score": 0.12, "verdict": "SAFE", "severity": "low"}
      },
      "violations": [{
        "criterion": "violence",
        "score": 0.78,
        "severity": "high",
        "evidence_refs": ["violence_seg_004"]
      }],
      "evidence": {
        "vision": [...],
        "violence_segments": [...],
        "transcript": {...},
        "ocr": [...]
      },
      "report": "AI-generated summary..."
    }
  }]
}
```

## 📦 Models Used

| Model | Purpose | HuggingFace ID |
|-------|---------|----------------|
| YOLO26 | Object detection | `openvision/yolo26-s` |
| YOLO-World | Open-vocab detection | `ultralytics/yoloworld` |
| X-CLIP | Violence detection | `microsoft/xclip-base-patch32-16-frames` |
| Whisper | Audio transcription | `openai/whisper-small` |
| PardonMyAI | Profanity detection | `tarekziade/pardonmyai` |
| BART-NLI | Multi-category moderation | `facebook/bart-large-mnli` |
| EasyOCR | Text extraction | Built-in |

## 🔧 Configuration

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@postgres:5432/judex

# Storage
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=judex

# Models
YOLO26_MODEL_ID=openvision/yolo26-s
VIOLENCE_MODEL_ID=microsoft/xclip-base-patch32-16-frames
WHISPER_MODEL_ID=openai/whisper-small

# Processing
DEFAULT_SAMPLING_FPS=1.0
SEGMENT_DURATION_SEC=2.0

# Optional: OpenAI for enhanced reports
OPENAI_API_KEY=sk-...
```

### Criteria Configuration

Create custom criteria via YAML:

```yaml
name: "Brand Safety"
version: "1.0"
description: "Evaluate content for brand safety"

criteria:
  - id: violence
    label: "Violence"
    threshold: 0.5
    severity: high
    
  - id: adult_content
    label: "Adult Content"
    threshold: 0.3
    severity: critical
    
  - id: controversial
    label: "Controversial Topics"
    threshold: 0.4
    severity: medium

settings:
  verdict_strategy: threshold_based
  unsafe_threshold: 0.6
  caution_threshold: 0.3
  generate_labeled_video: true
  generate_report: true
```

## 📂 Project Structure

```
judex/
├── app/
│   ├── main.py                 # FastAPI application
│   ├── api/
│   │   ├── evaluations.py      # Evaluation endpoints
│   │   ├── criteria_routes.py  # Criteria management
│   │   ├── schemas.py          # Pydantic DTOs
│   │   └── sse.py              # SSE manager
│   ├── db/
│   │   ├── models.py           # SQLAlchemy models
│   │   ├── connection.py       # Database connection
│   │   └── seeds.py            # Preset seeding
│   ├── evaluation/
│   │   ├── criteria.py         # EvaluationCriteria model
│   │   ├── routing.py          # Criteria to detector routing
│   │   └── result.py           # Result types
│   ├── fusion/
│   │   ├── engine.py           # FusionEngine
│   │   ├── scorers.py          # Criterion scorers
│   │   ├── strategies.py       # Verdict strategies
│   │   └── config.py           # Weights/thresholds
│   ├── pipeline/
│   │   ├── graph.py            # Stable LangGraph
│   │   ├── runner.py           # PipelineRunner
│   │   ├── state.py            # PipelineState
│   │   ├── nodes/              # Core pipeline nodes
│   │   └── stages/             # StagePlugin system
│   │       ├── base.py         # StagePlugin interface
│   │       ├── registry.py     # StageRegistry
│   │       └── builtins/       # Built-in plugins
│   ├── models/                 # AI model wrappers
│   └── utils/
│       ├── storage.py          # MinIO service
│       ├── ffmpeg.py           # Video processing
│       └── progress.py         # Progress tracking
├── frontend/
│   ├── src/
│   │   ├── pages/Pipeline.tsx  # Main UI
│   │   ├── api/client.ts       # API client
│   │   └── components/         # React components
│   └── package.json
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── tests/
└── README.md
```

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Specific test suites
pytest tests/test_fusion_strategies.py -v
pytest tests/test_api_contract_generic.py -v
pytest tests/test_spec_validation.py -v
```

## 🎯 Design Principles

### Pluggable Architecture
- **StagePlugin** interface for custom detectors
- **StageRegistry** for dynamic plugin resolution
- **PipelineRunner** for stage orchestration
- Stable LangGraph (no per-request compilation)

### Deterministic Verdicts
- Policy engine determines verdicts based on evidence
- Configurable fusion strategies (threshold, weighted, rules)
- LLM only formats reports, never decides outcomes

### Early Access
- Original video uploaded during ingest (immediately viewable)
- Frames + thumbnails saved during segment (filmstrip available early)
- Labeled video uploaded after YOLO26 (before pipeline completes)

### Industry-Standard Storage
- PostgreSQL for structured data (evaluations, results, criteria)
- MinIO/S3 for binary assets (videos, frames, thumbnails)
- Paginated APIs for large datasets
- Thumbnail optimization for fast UI

## 📝 License

MIT License - see LICENSE file for details

---

**Built for flexible, transparent video content evaluation**
