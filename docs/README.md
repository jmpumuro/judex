# Judex Documentation

Complete documentation for the Judex video evaluation framework.

---

## 📚 Documentation Index

### Core Documentation

1. **[SETUP.md](SETUP.md)** - Installation, configuration, and deployment
2. **[API.md](API.md)** - Complete REST API reference
3. **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design and pipeline details
4. **[QUICKREF.md](QUICKREF.md)** - Quick reference for common tasks

For a general overview, see the main [README.md](../README.md) in the project root.

---

## 🚀 Quick Start

### Installation

```bash
# Clone and start
git clone <repository-url>
cd safeVid

# Start PostgreSQL (if not running)
createdb judex

# Start services
docker-compose -f docker/docker-compose.yml up -d

# Access services
# UI:  http://localhost:5173  (React frontend)
# API: http://localhost:8012
# Docs: http://localhost:8012/docs
# MinIO Console: http://localhost:9001
```

### API Quick Start

```bash
# Health check
curl http://localhost:8012/v1/health

# Evaluate video with default criteria
curl -X POST http://localhost:8012/v1/evaluate \
  -F "video=@video.mp4"

# Evaluate with specific preset
curl -X POST http://localhost:8012/v1/evaluate \
  -F "video=@video.mp4" \
  -F "preset_id=child_safety"

# List evaluations
curl http://localhost:8012/v1/evaluations

# Get evaluation status
curl http://localhost:8012/v1/evaluations/{evaluation_id}
```

---

## 📖 Documentation by Role

### **Content Moderators**
Start with [API.md](API.md) to understand available endpoints and responses.

### **Developers**
Start with [ARCHITECTURE.md](ARCHITECTURE.md) for system design, then [SETUP.md](SETUP.md) for development setup.

### **System Administrators**
Start with [SETUP.md](SETUP.md) for deployment, then [QUICKREF.md](QUICKREF.md) for daily operations.

### **Integration Engineers**
Start with [API.md](API.md) for API reference, then check the `/examples` folder for code samples.

---

## 🎯 Key Features

### **Unified Evaluation API**
- Single `/v1/evaluate` endpoint for all use cases
- Upload file or provide URL
- Configurable evaluation criteria (presets or custom YAML/JSON)
- Real-time progress via SSE

### **Generic Criteria Framework**
- Define custom evaluation criteria
- Configure detectors, fusion strategies, and thresholds
- Built-in presets: `child_safety`, `content_moderation`, `violence_detection`

### **Pluggable Pipeline**
- StagePlugin architecture for extensibility
- Built-in stages: yolo26, yoloworld, violence, whisper, ocr, text_moderation
- Stable LangGraph with dynamic stage execution

### **Multi-Modal Analysis**
- **Vision**: YOLO26, YOLO-World (object detection)
- **Violence**: X-CLIP (16-frame temporal analysis)
- **Audio**: Whisper ASR (transcription)
- **Text**: PardonMyAI (profanity), BART-NLI (context moderation)
- **OCR**: Tesseract (text extraction from frames)

### **Live Feed Analysis**
- Real-time camera feed processing
- YOLOE for fast object detection
- Event-based violation tracking

---

## 🏗️ System Architecture

### **Pipeline Stages** (Stable LangGraph)

```
ingest_video → segment_video → run_pipeline → fuse_policy → llm_report
                                    │
                              PipelineRunner
                            (Dynamic Stages)
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                 yolo26        yoloworld      violence
                    │               │               │
                 whisper          ocr       text_moderation
```

1. **ingest_video** - Validate, normalize to 720p@30fps, upload to MinIO
2. **segment_video** - Extract keyframes (1fps), generate thumbnails
3. **run_pipeline** - Execute enabled detectors via PipelineRunner
4. **fuse_policy** - Compute criterion scores, determine verdict
5. **llm_report** - Optional AI-generated summary

### **Live Feed Pipeline**

1. **Capture Frame** - Webcam, RTSP, RTMP, HTTP
2. **YOLOE Detection** - Fast object detection
3. **Violence Detection** - Heuristic-based scoring
4. **Moderate Content** - Policy evaluation
5. **Emit Result** - Violation notifications

---

## 🔑 Key Concepts

### **Verdict Types**
- **SAFE** - Content is safe for all audiences
- **CAUTION** - Minor concerns, review recommended
- **UNSAFE** - Violates safety policies

### **Criteria Configuration**
Define evaluation criteria in YAML or JSON:
```yaml
name: my_criteria
version: "1.0"
criteria:
  - id: violence
    label: Violence Detection
    weight: 1.0
    threshold: 0.7
fusion:
  strategy: weighted_average
verdict:
  strategy: threshold
```

### **SSE (Server-Sent Events)**
One-way real-time progress updates from server to client:
```bash
curl -N http://localhost:8012/v1/evaluations/{id}/events
```

---

## 🛠️ Technical Stack

- **Backend**: FastAPI (Python 3.11)
- **Pipeline**: LangGraph (stable graph with dynamic execution)
- **Models**: HuggingFace Transformers, Ultralytics YOLO
- **Frontend**: React 18, TypeScript, Tailwind CSS
- **Database**: PostgreSQL (metadata, results, evidence)
- **Object Storage**: MinIO (videos, frames, thumbnails)
- **Real-time**: Server-Sent Events (SSE)
- **Infrastructure**: Docker, Docker Compose

---

## 📊 System Requirements

### Minimum
- 8GB RAM
- 4 CPU cores
- 20GB storage
- Docker + Docker Compose
- PostgreSQL 14+

### Recommended
- 16GB RAM
- 8 CPU cores
- NVIDIA GPU (8GB+ VRAM)
- 50GB storage

### For Production
- 32GB RAM
- 16+ CPU cores
- NVIDIA GPU (16GB+ VRAM)
- 100GB+ SSD storage
- Load balancer for multiple instances

---

## 📝 Common Tasks

See [QUICKREF.md](QUICKREF.md) for detailed examples:

- Evaluating videos with different criteria
- Creating custom evaluation presets
- Viewing evaluation results and artifacts
- Managing the pipeline stages
- Monitoring with SSE

---

## 🔗 External Resources

- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **LangGraph**: https://github.com/langchain-ai/langgraph
- **Ultralytics YOLO**: https://docs.ultralytics.com/
- **OpenAI Whisper**: https://github.com/openai/whisper
- **MinIO**: https://min.io/docs/

---

## 📄 License

See [LICENSE](../LICENSE) in the root directory.

---

**For detailed API documentation, see [API.md](API.md). For architecture and design, see [ARCHITECTURE.md](ARCHITECTURE.md).**
