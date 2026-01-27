# SafeVid - Child Safety Video Analysis Service

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**SafeVid** is a comprehensive video content analysis service designed to evaluate videos against child-safety criteria. It uses state-of-the-art AI models including YOLO26, YOLOE, YOLO-World, X-CLIP, Whisper, and text moderation models to provide deterministic safety verdicts with detailed evidence.

## 🎯 Features

- **Production API**: Simple `/v1/evaluate` endpoint - upload video, get verdict with evidence
- **Batch Processing**: Upload and process multiple videos simultaneously with individual progress tracking
- **Live Feed Analysis**: Real-time camera/stream processing with efficient YOLOE detection
- **Multi-Modal Analysis**: 
  - Visual (YOLO26 for batch, YOLOE for live)
  - Open-vocabulary detection (YOLO-World for custom objects)
  - Violence detection (X-CLIP)
  - Audio transcription (Whisper)
  - OCR and text moderation
- **Real-Time Progress**: SSE-based live updates for each video in the pipeline
- **Deterministic Verdicts**: Policy-based scoring ensures consistent, explainable results
- **Comprehensive Criteria**: Analyzes violence, profanity, sexual content, drugs/substances, and hate speech
- **Detailed Evidence**: Provides timestamps, detections, and references for all findings
- **LLM-Enhanced Reports**: Optional OpenAI integration for human-friendly summaries
- **Labeled Video Output**: Generates annotated videos with bounding boxes for detected objects
- **Result Persistence**: Saves analysis results across sessions with checkpoint recovery
- **Modern Web UI**: Intuitive interface with video preview, pipeline visualization, and stage-by-stage output inspection
- **Configurable Policy**: Customize safety thresholds with presets (Strict, Balanced, Lenient)

## 📋 Safety Criteria

SafeVid analyzes videos across five key criteria:

1. **Violence**: Fights, weapons, aggressive behavior (X-CLIP based detection)
2. **Profanity**: Inappropriate language in audio and text
3. **Sexual Content**: Adult themes and suggestive material
4. **Drugs/Substances**: Drug paraphernalia, substance use (YOLO26 detection)
5. **Hate/Harassment**: Hateful speech and harassment

## 🏗️ Architecture

```
┌──────────────────────┐
│   Web UI (Port 8080) │
│   - Batch Upload     │
│   - Real-time Updates│
│   - Pipeline View    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────┐
│              FastAPI Backend (Port 8012)                  │
│                                                           │
│  /v1/evaluate/batch  →  Process multiple videos          │
│  /v1/results/*       →  Persistence layer                │
│  /ws/{video_id}      →  WebSocket progress updates       │
└──────────┬───────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────┐
│              LangGraph Pipeline (Per Video)               │
│                                                           │
│  1. Ingest → 2. Segment → 3. YOLO26 Vision              │
│     ↓           ↓              ↓                          │
│  4. YOLO-World (Open-Vocab) → 5. Violence (X-CLIP)      │
│     ↓                            ↓                        │
│  6. Audio ASR → 7. OCR → 8. Text Moderation             │
│     ↓                                                     │
│  9. Policy Fusion → 10. LLM Report → 11. Finalize       │
└──────────┬───────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────┐
│  Outputs             │
│  - JSON Results      │
│  - Labeled Video     │
│  - Persistent Store  │
└──────────────────────┘
```

### Pipeline Nodes

**Batch Video Pipeline:**
1. **Ingest Video**: Validate video, extract metadata, save original file
2. **Segment Video**: Create time windows (3s), extract frames at 1 FPS
3. **YOLO26 Vision**: Detect objects (weapons, substances), generate labeled video
4. **YOLO-World Vision**: Open-vocabulary detection for custom/policy-specific objects
5. **Violence Detection**: Analyze segments with X-CLIP for violent content
6. **Audio ASR**: Transcribe audio with Whisper (multilingual)
7. **OCR**: Extract text from frames with EasyOCR
8. **Text Moderation**: Analyze transcript and OCR text for policy violations
9. **Policy Fusion**: Compute weighted scores and determine verdict (deterministic)
10. **LLM Report**: Generate human-friendly summary (optional)
11. **Finalize**: Prepare final JSON response with all evidence

**Live Feed Pipeline:**
1. **Capture Frame**: Decode incoming frame data
2. **YOLOE Detection**: Fast real-time object detection (optimized YOLOv8n)
3. **Violence Detection**: Heuristic-based violence estimation
4. **Moderate Content**: Policy evaluation and verdict generation
5. **Emit Result**: Format and return analysis result

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose
- 8GB+ RAM recommended
- (Optional) OpenAI API key for enhanced reports

### Running with Docker

```bash
# Clone the repository
git clone <repository-url>
cd safeVid

# Build and run
docker-compose -f docker/docker-compose.yml up --build

# Services will be available at:
# - API: http://localhost:8012
# - UI:  http://localhost:8080
```

### Using the Web UI

1. Open http://localhost:8080 in your browser
2. Click the **+** button to add videos (or drag & drop)
3. Click **▶ PROCESS ALL** to start batch processing
4. Watch real-time progress updates for each video
5. Click on the **▤** icon to view detailed pipeline results
6. Click on filename to preview the original video

### Testing the API

#### Production Endpoint

```bash
# Health check
curl http://localhost:8012/v1/health

# Evaluate video from file
curl -X POST http://localhost:8012/v1/evaluate \
  -F "video=@/path/to/video.mp4" \
  | jq .

# Evaluate video from URL
curl -X POST http://localhost:8012/v1/evaluate \
  -F "url=https://example.com/video.mp4" \
  | jq .

# With custom policy (strict)
curl -X POST http://localhost:8012/v1/evaluate \
  -F "video=@video.mp4" \
  -F 'policy={"thresholds":{"unsafe":{"violence":0.60}}}' \
  | jq .
```

**Response:**

```json
{
  "status": "success",
  "verdict": "SAFE",
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
    "video_metadata": {...},
    "object_detections": {...},
    "violence_segments": [...],
    "audio_transcript": [...],
    "ocr_results": [...],
    "moderation_flags": [...]
  },
  "summary": "Video analysis summary...",
  "model_versions": {...}
}
```

#### Batch Processing

```bash
# Batch evaluation
curl -X POST http://localhost:8012/v1/evaluate/batch \
  -F "files=@video1.mp4" \
  -F "files=@video2.mp4" \
  | jq .

# Get batch status
curl http://localhost:8012/v1/evaluate/batch/{batch_id} | jq .
```

#### Python Example

```python
import requests

# Simple evaluation
response = requests.post(
    'http://localhost:8012/v1/evaluate',
    files={'video': open('video.mp4', 'rb')}
)

result = response.json()
print(f"Verdict: {result['verdict']}")
print(f"Violence Score: {result['scores']['violence']*100:.1f}%")
```

**More Examples:**
- Python: [`examples/evaluate_api_example.py`](examples/evaluate_api_example.py)
- cURL: [`examples/evaluate_api_curl.sh`](examples/evaluate_api_curl.sh)
- Full API Docs: [`docs/API.md`](docs/API.md)
- Interactive Docs: http://localhost:8012/docs

## 📦 Models Used

| Model | Type | Purpose | HuggingFace ID |
|-------|------|---------|----------------|
| YOLO26 | Object Detection | Weapons, substances, persons | `openvision/yolo26-s` |
| X-CLIP | Video Classification | Violence/crime detection | `microsoft/xclip-base-patch32-16-frames` |
| Whisper | ASR | Audio transcription | `openai/whisper-small` |
| PardonMyAI | Text Classification | Profanity detection | `tarekziade/pardonmyai` |
| BART-NLI | Zero-Shot | Multi-category moderation | `facebook/bart-large-mnli` |
| EasyOCR | OCR | Text extraction from frames | Built-in |

All models are cached in Docker volumes on first run.

## 🔧 Configuration

### Environment Variables

```bash
# Model Selection
YOLO26_MODEL_ID=openvision/yolo26-s
VIOLENCE_MODEL_ID=microsoft/xclip-base-patch32-16-frames
USE_XCLIP_VIOLENCE=true
WHISPER_MODEL_ID=openai/whisper-small
PROFANITY_MODEL_ID=tarekziade/pardonmyai
NLI_MODEL_ID=facebook/bart-large-mnli

# OpenAI (Optional - for enhanced reports)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Processing Parameters
DEFAULT_SAMPLING_FPS=1.0           # Frame extraction rate
SEGMENT_DURATION_SEC=3.0           # Violence analysis segments
VIOLENCE_FRAMES_PER_SEGMENT=16     # Frames per violence segment
OCR_INTERVAL_SEC=2.0               # OCR sampling interval

# Paths
HF_HOME=/models/hf
TRANSFORMERS_CACHE=/models/hf/transformers
TEMP_DIR=/tmp/safevid
DATA_DIR=/data/safevid             # Persistent storage
```

### Policy Thresholds

Default thresholds are configurable in `app/core/config.py`:

```python
# UNSAFE thresholds (trigger unsafe verdict)
threshold_unsafe_violence = 0.75
threshold_unsafe_sexual = 0.60
threshold_unsafe_hate = 0.60
threshold_unsafe_drugs = 0.70

# CAUTION thresholds (trigger caution verdict)
threshold_caution_violence = 0.40
threshold_caution_profanity = 0.40
threshold_caution_drugs = 0.40
threshold_caution_sexual = 0.30
threshold_caution_hate = 0.30
```

### Policy Overrides (Per-Request)

```python
import requests
import json

policy_override = {
    "thresholds": {
        "unsafe": {
            "violence": 0.8,  # Higher threshold
            "sexual": 0.7
        }
    },
    "sampling_fps": 0.5  # Lower FPS for faster processing
}

response = requests.post(
    "http://localhost:8012/v1/evaluate",
    files={"file": open("video.mp4", "rb")},
    data={"policy": json.dumps(policy_override)}
)
```

## 📖 API Reference

### POST `/v1/evaluate`

Evaluate a single video for child safety.

**Request:**
- `file` (required): Video file (multipart/form-data)
- `policy` (optional): JSON string with policy overrides

**Response:** `VideoEvaluationResponse` (see structure below)

---

### POST `/v1/evaluate/batch`

Evaluate multiple videos in batch.

**Request:**
- `files` (required): Multiple video files (multipart/form-data)
- `policy` (optional): JSON string with policy overrides (applies to all)

**Response:**
```json
{
  "batch_id": "uuid-v4",
  "status": "processing",
  "total_videos": 3,
  "videos": [
    {
      "video_id": "uuid-v4",
      "filename": "video1.mp4",
      "status": "queued",
      "progress": 0
    }
  ]
}
```

---

### GET `/v1/evaluate/batch/{batch_id}`

Get batch processing status and results.

**Response:**
```json
{
  "batch_id": "uuid-v4",
  "status": "completed",
  "total_videos": 3,
  "completed": 3,
  "failed": 0,
  "videos": {
    "video-id-1": {
      "video_id": "video-id-1",
      "filename": "video1.mp4",
      "status": "completed",
      "progress": 100,
      "result": { /* VideoEvaluationResponse */ }
    }
  }
}
```

---

### WebSocket `/ws/{video_id}`

Real-time progress updates for a video.

**Messages (Server → Client):**
```json
{
  "stage": "yolo26_vision",
  "progress": 30,
  "message": "Analyzing frames with YOLO26..."
}
```

---

### GET `/v1/video/labeled/{video_id}`

Download the labeled video with bounding boxes.

**Response:** MP4 video file (H.264)

---

### Persistence Endpoints

- `POST /v1/results/save` - Save analysis results
- `GET /v1/results/load` - Load saved results
- `DELETE /v1/results/{video_id}` - Delete specific result
- `DELETE /v1/results` - Clear all results

---

### Video Evaluation Response Structure

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
    "profanity": { "score": 0.12, "status": "ok" },
    "sexual": { "score": 0.05, "status": "ok" },
    "drugs": { "score": 0.41, "status": "caution" },
    "hate": { "score": 0.02, "status": "ok" }
  },
  "violations": [
    {
      "criterion": "violence",
      "severity": "high",
      "timestamp_ranges": [[31.2, 38.9]],
      "evidence_refs": ["violence_segment_004"],
      "evidence_summary": "High violence detected in segment"
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
            "bbox": [120, 340, 180, 420]
          }
        ]
      }
    ],
    "violence_segments": [
      {
        "segment_id": 4,
        "start_time": 31.2,
        "end_time": 34.2,
        "violence_score": 0.88
      }
    ],
    "asr": {
      "full_text": "Complete transcript...",
      "language": "en",
      "chunks": [
        {
          "text": "...",
          "start_time": 10.5,
          "end_time": 14.2
        }
      ]
    },
    "ocr": [
      {
        "frame_index": 120,
        "timestamp": 120.0,
        "text": "Detected text",
        "detections": [
          {
            "text": "...",
            "confidence": 0.95,
            "bbox": [...]
          }
        ]
      }
    ],
    "moderation": {
      "profanity_segments": [],
      "sexual_segments": [],
      "hate_segments": [],
      "drugs_segments": []
    }
  },
  "transcript": {
    "full_text": "...",
    "chunks": [...]
  },
  "report": "AI-generated summary (if OpenAI key provided)",
  "labeled_video_path": "/tmp/safevid/work_xyz/labeled.mp4",
  "metadata": {
    "video_id": "uuid-v4",
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

---

### GET `/v1/health`

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "models_loaded": true
}
```

---

### GET `/v1/models`

List configured models and cache status.

**Response:**
```json
{
  "models": [
    {
      "model_id": "openvision/yolo26-s",
      "model_type": "vision",
      "cached": true,
      "status": "ready"
    }
  ]
}
```

## 🧪 Testing

```bash
# Install test dependencies
pip install -r tests/requirements-test.txt

# Run all tests
pytest tests/ -v

# Run specific test suites
pytest tests/test_policy_fusion.py -v       # Policy scoring logic
pytest tests/test_api_contract.py -v        # API endpoint contracts
pytest tests/test_graph_smoke.py -v         # Pipeline integration
```

## 📂 Project Structure

```
safeVid/
├── app/
│   ├── main.py                    # FastAPI application
│   ├── api/
│   │   ├── routes.py              # API endpoints (batch, single, persistence)
│   │   ├── schemas.py             # Pydantic models
│   │   └── websocket.py           # WebSocket manager
│   ├── core/
│   │   ├── config.py              # Configuration & policy settings
│   │   └── logging.py             # Logging setup
│   ├── models/
│   │   ├── yolo26.py              # YOLO26 object detection
│   │   ├── violence_xclip.py      # X-CLIP violence detection
│   │   ├── whisper_asr.py         # Whisper ASR wrapper
│   │   └── moderation.py          # Text moderation models
│   ├── pipeline/
│   │   ├── graph.py               # LangGraph pipeline definition
│   │   ├── state.py               # PipelineState TypedDict
│   │   └── nodes/                 # Pipeline node implementations
│   │       ├── ingest_video.py    # Video ingestion
│   │       ├── segment_video.py   # Segmentation
│   │       ├── yolo26_vision.py   # YOLO detection + labeling
│   │       ├── violence_video.py  # Violence analysis
│   │       ├── audio_asr.py       # Audio transcription
│   │       ├── ocr.py             # Text extraction
│   │       ├── text_moderation.py # Text analysis
│   │       ├── fuse_policy.py     # Policy fusion & scoring
│   │       ├── llm_report.py      # LLM report generation
│   │       └── finalize.py        # Final output preparation
│   └── utils/
│       ├── ffmpeg.py              # Video processing & labeled video creation
│       ├── video.py               # Video utilities
│       ├── hashing.py             # ID generation
│       ├── timing.py              # Performance tracking
│       ├── progress.py            # Progress reporting
│       └── persistence.py         # Result storage (NEW)
├── ui/
│   ├── index.html                 # Modern web UI (single-page app)
│   └── server.py                  # Simple HTTP server for UI
├── docker/
│   ├── Dockerfile                 # Container definition
│   └── docker-compose.yml         # Multi-service setup
├── scripts/
│   └── prefetch_models.py         # Model pre-download script
├── tests/
│   ├── test_policy_fusion.py
│   ├── test_api_contract.py
│   └── test_graph_smoke.py
├── requirements.txt
└── README.md
```

## 🎯 Design Principles

### Deterministic Verdicts

The verdict is **always** determined by the policy engine based on evidence scores and thresholds. The LLM only formats the report—it never decides safety outcomes.

### Configurable Policy

Thresholds, weights, and model choices are fully configurable via:
- Environment variables (persistent)
- Config file (`app/core/config.py`)
- Per-request API overrides (dynamic)

### Evidence-Based

Every violation includes:
- Timestamp ranges (when did it occur)
- Evidence references (which detections/segments)
- Model confidence scores (how confident)
- Source information (vision/audio/text/OCR)
- Full evidence objects in response

### Batch Processing

- Upload multiple videos at once
- Independent processing per video
- Real-time progress via WebSocket
- Individual results and statuses
- Checkpoint recovery for interrupted processing

### Production-Ready

- Model caching (Docker volumes, no re-downloads)
- Result persistence (survive restarts)
- Checkpoint recovery (resume interrupted jobs)
- Health checks & monitoring
- Comprehensive logging
- Error handling & retries
- H.264 labeled videos (browser-compatible)
- Temporal smoothing (reduced flickering in labeled videos)

## 🔍 Example Use Cases

1. **Content Moderation Platforms**: Pre-screen user uploads before publication
2. **Educational Platforms**: Verify child-appropriate content in libraries
3. **Parental Control Apps**: Analyze videos before children watch
4. **Media Companies**: Quality assurance for kids' content production
5. **Social Media**: Automated flagging of inappropriate content

## ⚠️ Limitations

- **Automated Analysis**: Not a replacement for human review in critical cases
- **Model Accuracy**: AI models may have false positives/negatives
- **Language Support**: Optimized for English (Whisper supports multilingual)
- **Video Length**: Best for videos under 10 minutes (longer videos increase processing time significantly)
- **Context**: May miss nuanced context that humans would understand
- **Labeled Video Storage**: Labeled videos are temporary and may be cleaned up

## 🛠️ Development

### Local Setup (without Docker)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export HF_HOME=./models/hf
export TRANSFORMERS_CACHE=./models/hf/transformers
export TEMP_DIR=./tmp/safevid
export DATA_DIR=./data/safevid

# Run prefetch (optional, downloads models)
python scripts/prefetch_models.py

# Run backend server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8012

# In another terminal, run UI server
cd ui && python server.py
```

### Adding Custom Models

1. Update `app/core/config.py` with new model IDs
2. Create model wrapper in `app/models/`
3. Add pipeline node in `app/pipeline/nodes/`
4. Update graph in `app/pipeline/graph.py`
5. Update policy fusion (`fuse_policy.py`) to use new evidence
6. Update state definition in `state.py` if needed

### Key Features Implementation

**Batch Processing:**
- `batch_jobs` dict stores active batches
- Each video gets unique `video_id`
- WebSocket connections per video for progress
- Background tasks for async processing

**Labeled Videos:**
- Created in `yolo26_vision.py` node
- Uses OpenCV for frame annotation
- FFmpeg re-encodes to H.264 for browser compatibility
- Temporal smoothing reduces bounding box flickering

**Checkpoint Recovery:**
- Browser localStorage stores progress
- On reload, checks for interrupted videos
- Fetches original video from backend `/video/uploaded/{video_id}`
- Allows resume from last stage

## 📝 License

MIT License - see LICENSE file for details

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Add tests for new functionality
4. Ensure all tests pass (`pytest tests/`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## 📞 Support

For issues, questions, or suggestions:
- Open an issue on GitHub
- Check existing documentation in `/docs`
- Review test files for usage examples

## 🙏 Acknowledgments

- YOLO26 models from OpenVision team
- X-CLIP models from Microsoft Research
- Transformers library by HuggingFace
- Whisper ASR by OpenAI
- EasyOCR for text extraction
- LangGraph for pipeline orchestration
- FastAPI for modern Python web framework

---

**Built with ❤️ for child safety**
