# SafeVid Documentation

Complete documentation for the SafeVid child safety video analysis service.

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
docker-compose -f docker/docker-compose.yml up -d

# Access services
# UI:  http://localhost:8080
# API: http://localhost:8012
# Docs: http://localhost:8012/docs
```

### API Quick Start

```bash
# Health check
curl http://localhost:8012/v1/health

# Evaluate video (production endpoint)
curl -X POST http://localhost:8012/v1/evaluate \
  -F "video=@video.mp4"

# Batch processing
curl -X POST http://localhost:8012/v1/evaluate/batch \
  -F "files=@video1.mp4" \
  -F "files=@video2.mp4"
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

### **Production API**
- Simple `/v1/evaluate` endpoint
- Upload file or provide URL
- Complete verdict with evidence
- Configurable safety policies

### **Batch Processing**
- Process multiple videos simultaneously
- Real-time progress updates via SSE
- Checkpoint/resume support
- Persistent result storage

### **Live Feed Analysis**
- Real-time camera feed processing
- YOLOE for fast object detection
- Event-based violation tracking
- WebRTC and RTSP support

### **Multi-Modal Analysis**
- **Vision**: YOLO26, YOLOE, YOLO-World
- **Violence**: VideoMAE (16-frame clips)
- **Audio**: Whisper ASR
- **Text**: PardonMyAI (profanity), BART (context)
- **OCR**: Tesseract

### **Safety Criteria**
- Violence (fights, weapons, aggressive behavior)
- Profanity (inappropriate language)
- Sexual Content (adult themes)
- Drugs (paraphernalia, substance use)
- Hate Speech (discrimination, harassment)

---

## 🏗️ System Architecture

### **Pipeline Stages** (Batch)

1. **Ingest** - Normalize video (fps, resolution, audio)
2. **Segment** - VideoMAE-optimized frame sampling
3. **YOLO26** - Object detection at 640px
4. **YOLO-World** - Open-vocabulary detection
5. **Violence** - VideoMAE temporal analysis
6. **Audio ASR** - Whisper transcription (30s chunks)
7. **OCR** - Tesseract text extraction
8. **Moderation** - Text analysis (profanity, context)
9. **Policy Fusion** - Multi-signal scoring
10. **LLM Report** - GPT-4o-mini summary
11. **Finalize** - Result packaging

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
- **NEEDS_REVIEW** - Ambiguous, requires manual review

### **Policy Configuration**
Customize safety thresholds for different use cases:
- **Strict** - Lower thresholds (children's content)
- **Balanced** - Default thresholds (general use)
- **Lenient** - Higher thresholds (news/documentary)

### **Server-Side Checkpoints**
Automatic state persistence allows resuming interrupted processing without starting from scratch.

### **SSE (Server-Sent Events)**
One-way real-time progress updates from server to client, simpler and more reliable than WebSockets.

---

## 🛠️ Technical Stack

- **Backend**: FastAPI (Python 3.11)
- **Pipeline**: LangGraph (state machines)
- **Models**: HuggingFace Transformers, Ultralytics YOLO
- **Frontend**: HTML/CSS/JavaScript
- **Infrastructure**: Docker, Docker Compose
- **Storage**: File-based (JSON + video files)
- **Real-time**: SSE, WebSocket

---

## 📊 System Requirements

### Minimum
- 8GB RAM
- 4 CPU cores
- 20GB storage
- Docker + Docker Compose

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

- Uploading and processing videos
- Starting live feed analysis
- Viewing and managing results
- Configuring safety policies
- Managing checkpoints
- Importing from storage/database/URLs

---

## 🔗 External Resources

- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **LangGraph**: https://github.com/langchain-ai/langgraph
- **Ultralytics YOLO**: https://docs.ultralytics.com/
- **OpenAI Whisper**: https://github.com/openai/whisper
- **Tesseract OCR**: https://github.com/tesseract-ocr/tesseract

---

## 📄 License

See [LICENSE](../LICENSE) in the root directory.

---

**For detailed API documentation, see [API.md](API.md). For architecture and design, see [ARCHITECTURE.md](ARCHITECTURE.md).**
