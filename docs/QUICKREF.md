# Judex Developer Quick Reference

Quick reference guide for common development tasks and patterns.

## Table of Contents

- [Common Commands](#common-commands)
- [API Endpoints Quick Reference](#api-endpoints-quick-reference)
- [Pipeline Stages](#pipeline-stages)
- [Configuration Reference](#configuration-reference)
- [Criteria YAML Format](#criteria-yaml-format)
- [Debugging Tips](#debugging-tips)

---

## Common Commands

### Docker Operations

```bash
# Start all services
docker-compose -f docker/docker-compose.yml up -d

# Rebuild and start
docker-compose -f docker/docker-compose.yml up -d --build

# View logs
docker-compose -f docker/docker-compose.yml logs -f judex

# Stop services
docker-compose -f docker/docker-compose.yml down

# Remove volumes (clean slate)
docker-compose -f docker/docker-compose.yml down -v
```

### Database Operations

```bash
# Create database (PostgreSQL)
createdb judex

# Drop and recreate
dropdb judex && createdb judex

# Connect via psql
psql -d judex

# Quick queries
psql -d judex -c "SELECT id, status FROM evaluations ORDER BY created_at DESC LIMIT 5;"
psql -d judex -c "SELECT COUNT(*) FROM evaluation_items WHERE status = 'completed';"
```

### Frontend Development

```bash
# Install dependencies
cd frontend && npm install

# Development server
cd frontend && npm run dev

# Build production
cd frontend && npm run build

# Type check
cd frontend && npm run tsc
```

### API Testing

```bash
# Health check
curl http://localhost:8012/v1/health | jq

# Evaluate video
curl -X POST http://localhost:8012/v1/evaluate \
  -F "video=@video.mp4" | jq

# List evaluations
curl http://localhost:8012/v1/evaluations | jq

# Get evaluation details
curl http://localhost:8012/v1/evaluations/{id} | jq

# Stream SSE events
curl -N http://localhost:8012/v1/evaluations/{id}/events

# List presets
curl http://localhost:8012/v1/criteria/presets | jq

# Validate criteria
curl -X POST http://localhost:8012/v1/criteria/validate \
  -F 'content=name: test
version: "1.0"
criteria:
  - id: violence' | jq
```

---

## API Endpoints Quick Reference

### Evaluation

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/evaluate` | Submit video for evaluation |
| GET | `/v1/evaluations` | List all evaluations |
| GET | `/v1/evaluations/{id}` | Get evaluation details |
| DELETE | `/v1/evaluations/{id}` | Delete evaluation |
| GET | `/v1/evaluations/{id}/stages` | List stage status |
| GET | `/v1/evaluations/{id}/stages/{stage}` | Get stage output |
| GET | `/v1/evaluations/{id}/events` | SSE progress stream |

### Artifacts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/evaluations/{id}/artifact/uploaded` | Original video |
| GET | `/v1/evaluations/{id}/artifact/labeled` | Labeled video |
| GET | `/v1/evaluations/{id}/frames` | List frames (paginated) |
| GET | `/v1/evaluations/{id}/frames/{filename}` | Get frame image |

### Criteria

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/criteria/presets` | List built-in presets |
| GET | `/v1/criteria/presets/{id}` | Get preset details |
| GET | `/v1/criteria/presets/{id}/export` | Export preset YAML |
| GET | `/v1/criteria/custom` | List custom criteria |
| POST | `/v1/criteria/custom` | Create custom criteria |
| POST | `/v1/criteria/validate` | Validate criteria |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/health` | Health check |
| GET | `/v1/models` | List loaded models |

---

## Pipeline Stages

### Stable Graph Nodes

| Stage | Function | Input | Output |
|-------|----------|-------|--------|
| `ingest_video` | Normalize video | `video_path` | `work_dir`, `fps`, `duration` |
| `segment_video` | Extract frames | `video_path` | `sampled_frames`, `segment_clips` |
| `run_pipeline` | Execute detectors | criteria | detector outputs |
| `fuse_policy` | Compute scores | detector outputs | `verdict`, `criteria_scores` |
| `llm_report` | Generate summary | all outputs | `report` |

### Dynamic Stages (via PipelineRunner)

| Stage | Detector | Output Keys |
|-------|----------|-------------|
| `yolo26` | YOLO26 object detection | `vision_detections` |
| `yoloworld` | YOLO-World open-vocab | `vision_detections` |
| `violence` | X-CLIP temporal analysis | `violence_segments`, `violence_score` |
| `whisper` | Audio transcription | `transcript` |
| `ocr` | Text extraction | `ocr_text` |
| `text_moderation` | Content moderation | `moderation_results` |

---

## Configuration Reference

### Environment Variables

```bash
# API
APP_NAME="Judex - Video Evaluation Framework"
VERSION="2.0.0"
API_PREFIX="/v1"

# Database
DATABASE_URL=postgresql://docker:docker@localhost:5432/judex

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=judex
MINIO_SECRET_KEY=judex123
MINIO_BUCKET=judex

# Models
YOLO26_MODEL_ID=openvision/yolo26-s
VIOLENCE_MODEL_ID=microsoft/xclip-base-patch32-16-frames
WHISPER_MODEL_ID=openai/whisper-tiny

# LLM
LLM_PROVIDER=template  # or "qwen" or "openai"
OPENAI_API_KEY=sk-...

# Paths
HF_HOME=/models/hf
TEMP_DIR=/tmp/judex
DATA_DIR=/data/judex
```

### Processing Settings

```bash
DEFAULT_SAMPLING_FPS=1.0        # Frames per second for sampling
SEGMENT_DURATION_SEC=3.0        # Segment duration for violence
VIOLENCE_FRAMES_PER_SEGMENT=16  # Frames per violence segment
OCR_INTERVAL_SEC=2.0            # OCR sampling interval
```

---

## Criteria YAML Format

### Minimal Example

```yaml
name: My Criteria
version: "1.0"
criteria:
  - id: violence
  - id: profanity
```

### Full Example

```yaml
name: Custom Evaluation
version: "1.0"
description: Custom criteria for content moderation

criteria:
  - id: violence
    label: Violence Detection
    description: Detect violent content
    weight: 1.5
    threshold: 0.6
    keywords:
      - fight
      - weapon
      - blood

  - id: profanity
    label: Profanity Detection
    weight: 1.0
    threshold: 0.5

  - id: drugs
    label: Drug Content
    weight: 0.8
    threshold: 0.7
    keywords:
      - marijuana
      - cocaine

fusion:
  strategy: weighted_average  # or: max, min

verdict:
  strategy: threshold  # or: majority, any
  safe_threshold: 0.3
  unsafe_threshold: 0.7
```

### Available Criterion IDs

| ID | Detectors Used |
|----|----------------|
| `violence` | violence, yolo26 |
| `profanity` | whisper, text_moderation |
| `sexual_content` | yolo26, yoloworld, ocr, text_moderation |
| `drugs` | yolo26, yoloworld, ocr |
| `hate_speech` | whisper, ocr, text_moderation |
| `weapons` | yolo26, yoloworld |

---

## Debugging Tips

### Check Pipeline State

```python
# In Python shell
from app.db.connection import get_db_session
from app.api.evaluations import EvaluationRepository

with get_db_session() as session:
    repo = EvaluationRepository(session)
    eval = repo.get("abc123")
    print(eval.items[0].stage_outputs)
```

### View Docker Logs

```bash
# All logs
docker-compose -f docker/docker-compose.yml logs

# Follow specific service
docker-compose -f docker/docker-compose.yml logs -f judex

# Last 100 lines
docker-compose -f docker/docker-compose.yml logs --tail=100 judex
```

### Check MinIO

```bash
# MinIO Console
open http://localhost:9001
# Login: judex / judex123

# List buckets via mc
mc alias set local http://localhost:9000 judex judex123
mc ls local/judex/
```

### Check PostgreSQL

```bash
# Quick status
psql -d judex -c "\dt"

# Recent evaluations
psql -d judex -c "SELECT id, status, created_at FROM evaluations ORDER BY created_at DESC LIMIT 10;"

# Failed items
psql -d judex -c "SELECT id, error_message FROM evaluation_items WHERE status = 'failed';"
```

### SSE Debugging

```bash
# Watch events
curl -N http://localhost:8012/v1/evaluations/{id}/events

# With timestamps
curl -N http://localhost:8012/v1/evaluations/{id}/events | ts
```

### Common Issues

| Issue | Check | Fix |
|-------|-------|-----|
| 404 on evaluation | DB has record? | Check `psql -d judex -c "SELECT * FROM evaluations WHERE id='...'"` |
| Video not loading | MinIO path exists? | Check MinIO console |
| Stage stuck | Container crashed? | Check `docker-compose logs judex` |
| Empty criteria_scores | Detectors ran? | Check `stage_outputs` in DB |

---

**For detailed API documentation, see [API.md](API.md). For architecture details, see [ARCHITECTURE.md](ARCHITECTURE.md).**
