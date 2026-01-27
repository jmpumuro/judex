# SafeVid Architecture Guide

Deep dive into the SafeVid system architecture, design decisions, and implementation details.

## Table of Contents

- [System Overview](#system-overview)
- [Technology Stack](#technology-stack)
- [Pipeline Architecture](#pipeline-architecture)
- [Data Flow](#data-flow)
- [Model Integration](#model-integration)
- [Policy Engine](#policy-engine)
- [Batch Processing System](#batch-processing-system)
- [Real-Time Communication](#real-time-communication)
- [Persistence Layer](#persistence-layer)
- [Video Processing](#video-processing)
- [Design Decisions](#design-decisions)
- [Security Considerations](#security-considerations)
- [Performance Optimization](#performance-optimization)
- [Extension Points](#extension-points)

---

## System Overview

SafeVid is a multi-modal video analysis system built on a modular pipeline architecture. The system evaluates videos against child safety criteria using multiple AI models and produces deterministic safety verdicts.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Client Layer                          │
│  ┌──────────────┐            ┌──────────────┐              │
│  │   Web UI     │────HTTP────│  API Clients │              │
│  │ (Port 8080)  │            │   (cURL,SDK) │              │
│  └──────┬───────┘            └──────┬───────┘              │
│         │                           │                       │
│         └───────────WebSocket───────┘                       │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────────┐
│                      API Layer (FastAPI)                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  REST API (Port 8012)    WebSocket Manager           │  │
│  │  - Health checks         - Real-time updates         │  │
│  │  - Video submission      - Progress broadcasting     │  │
│  │  - Batch processing      - Per-video connections     │  │
│  │  - Result retrieval                                  │  │
│  └──────────────────┬───────────────────────────────────┘  │
└─────────────────────┼───────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────────┐
│                   Processing Layer                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           LangGraph Pipeline (per video)             │  │
│  │                                                       │  │
│  │  Ingest → Segment → Vision → Violence → Audio →     │  │
│  │  OCR → Text Mod → Policy Fusion → LLM → Finalize    │  │
│  │                                                       │  │
│  │  Each node:                                          │  │
│  │  - Updates pipeline state                            │  │
│  │  - Broadcasts progress via WebSocket                 │  │
│  │  - Handles errors gracefully                         │  │
│  └──────────────────┬───────────────────────────────────┘  │
└─────────────────────┼───────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────────┐
│                      Model Layer                             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │   YOLO26    │ │   X-CLIP    │ │   Whisper   │          │
│  │   Vision    │ │  Violence   │ │     ASR     │          │
│  └─────────────┘ └─────────────┘ └─────────────┘          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │  EasyOCR    │ │ PardonMyAI  │ │  BART-NLI   │          │
│  │    Text     │ │  Profanity  │ │ Moderation  │          │
│  └─────────────┘ └─────────────┘ └─────────────┘          │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────────┐
│                    Storage Layer                             │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐      │
│  │ Model Cache  │  │   Temp Files │  │  Results    │      │
│  │  (Docker     │  │   (Videos,   │  │  (JSON)     │      │
│  │   Volume)    │  │   Frames)    │  │             │      │
│  └──────────────┘  └──────────────┘  └─────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

### Backend

- **FastAPI**: Modern Python web framework
  - Async support for concurrent requests
  - Automatic OpenAPI documentation
  - WebSocket support
  - Type validation with Pydantic

- **LangGraph**: Pipeline orchestration
  - Stateful node execution
  - Directed graph workflow
  - Error handling and retries
  - State persistence

- **PyTorch**: Deep learning framework
  - Model inference
  - GPU acceleration support
  - HuggingFace integration

### Models & Libraries

- **Transformers**: HuggingFace library for model loading
- **OpenCV**: Video processing and frame manipulation
- **FFmpeg**: Video encoding/decoding
- **EasyOCR**: Text extraction from frames
- **Whisper**: Audio transcription

### Frontend

- **Vanilla JavaScript**: No framework dependencies
- **WebSocket API**: Real-time updates
- **Fetch API**: HTTP requests
- **LocalStorage**: Checkpoint persistence

### Infrastructure

- **Docker**: Containerization
- **Docker Compose**: Multi-service orchestration
- **Uvicorn**: ASGI server

---

## Pipeline Architecture

### LangGraph Pipeline

The core of SafeVid is a LangGraph-based pipeline that processes videos through multiple stages.

```python
# Simplified pipeline structure
from langgraph.graph import StateGraph

graph = StateGraph(PipelineState)

# Add nodes
graph.add_node("ingest_video", ingest_video_node)
graph.add_node("segment_video", segment_video_node)
graph.add_node("yolo26_vision", yolo26_vision_node)
graph.add_node("violence_detection", violence_detection_node)
graph.add_node("audio_transcription", audio_transcription_node)
graph.add_node("ocr_extraction", ocr_extraction_node)
graph.add_node("text_moderation", text_moderation_node)
graph.add_node("policy_fusion", policy_fusion_node)
graph.add_node("report_generation", report_generation_node)
graph.add_node("finalize", finalize_node)

# Define edges (linear flow)
graph.add_edge("ingest_video", "segment_video")
graph.add_edge("segment_video", "yolo26_vision")
# ... etc

# Set entry point
graph.set_entry_point("ingest_video")
graph.set_finish_point("finalize")
```

### Pipeline State

All data flows through a typed state object:

```python
from typing import TypedDict, Optional, List, Dict, Any

class PipelineState(TypedDict, total=False):
    # Input
    video_path: str
    video_id: str
    policy_config: Dict[str, Any]
    
    # Video metadata
    duration: float
    fps: float
    width: int
    height: int
    has_audio: bool
    frame_count: int
    
    # Extracted data
    frames: List[Dict]  # frame_index, timestamp, path
    segments: List[Dict]  # segment_id, start, end, frames
    
    # Detection results
    yolo_detections: List[Dict]
    violence_segments: List[Dict]
    transcript: Dict
    ocr_results: List[Dict]
    moderation_results: Dict
    
    # Analysis outputs
    criteria_scores: Dict[str, float]
    violations: List[Dict]
    evidence: Dict
    verdict: str
    report: Optional[str]
    
    # Processing metadata
    timings: Dict[str, float]
    work_dir: str
    labeled_video_path: Optional[str]
    
    # Progress tracking
    current_stage: str
    progress_percentage: int
    error: Optional[str]
```

### Node Structure

Each pipeline node follows a consistent pattern:

```python
async def node_function(state: PipelineState) -> PipelineState:
    """
    Process one stage of the pipeline.
    
    Args:
        state: Current pipeline state
        
    Returns:
        Updated state with node's outputs
    """
    # 1. Update progress
    await update_progress(state["video_id"], stage="node_name", progress=XX)
    
    # 2. Extract needed inputs from state
    video_path = state["video_path"]
    frames = state["frames"]
    
    # 3. Perform processing
    try:
        results = await process_data(video_path, frames)
    except Exception as e:
        state["error"] = str(e)
        return state
    
    # 4. Update state with results
    state["node_results"] = results
    state["timings"]["node_name"] = elapsed_time
    
    # 5. Return updated state
    return state
```

---

## Data Flow

### Request Flow

1. **Client uploads video** → API receives file
2. **API creates batch** → Generates video_id, batch_id
3. **API queues video** → Background task created
4. **Pipeline starts** → LangGraph invoked
5. **Each node processes** → State updated, progress broadcast
6. **Results finalized** → Response returned to API
7. **Client polls/receives** → Via HTTP or WebSocket

### State Flow Through Pipeline

```
Input Video
    ↓
[Ingest] → Extract metadata, validate file
    ↓
State: {video_path, duration, fps, width, height, has_audio}
    ↓
[Segment] → Extract frames, create segments
    ↓
State: {frames: [{index, timestamp, path}], segments: [...]}
    ↓
[YOLO26] → Detect objects, create labeled video
    ↓
State: {yolo_detections: [{class, confidence, bbox}], labeled_video_path}
    ↓
[Violence] → Analyze segments for violence
    ↓
State: {violence_segments: [{segment_id, score, start, end}]}
    ↓
[ASR] → Transcribe audio
    ↓
State: {transcript: {full_text, chunks: [{text, start, end}]}}
    ↓
[OCR] → Extract text from frames
    ↓
State: {ocr_results: [{frame, timestamp, text, detections}]}
    ↓
[Text Mod] → Analyze transcript + OCR
    ↓
State: {moderation_results: {profanity_segments, sexual_segments, ...}}
    ↓
[Policy Fusion] → Calculate scores, determine verdict
    ↓
State: {criteria_scores: {...}, violations: [...], verdict: "UNSAFE"}
    ↓
[LLM Report] → Generate human-readable summary
    ↓
State: {report: "AI-generated summary..."}
    ↓
[Finalize] → Package final response
    ↓
Output: VideoEvaluationResponse
```

---

## Model Integration

### Model Wrapper Pattern

Each model is wrapped in a singleton class:

```python
class ModelWrapper:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # Load model on first instantiation
        self.model = AutoModel.from_pretrained(MODEL_ID)
        self.processor = AutoProcessor.from_pretrained(MODEL_ID)
        
        # Move to GPU if available
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        
        self._initialized = True
    
    def predict(self, inputs):
        with torch.no_grad():
            return self.model(**inputs)
```

### Model Lifecycle

1. **First Request**: Model downloaded from HuggingFace
2. **Caching**: Saved to `HF_HOME` directory
3. **Loading**: Loaded into memory on service startup
4. **Inference**: Used for all subsequent requests
5. **Persistence**: Cached models survive restarts (via Docker volume)

### Supported Models

| Model | Purpose | Input | Output |
|-------|---------|-------|--------|
| YOLO26 | Object detection | Image frames | Bounding boxes + classes |
| X-CLIP | Violence detection | Video segments (16 frames) | Violence probability |
| Whisper | Speech recognition | Audio waveform | Transcript + timestamps |
| PardonMyAI | Profanity detection | Text | Profanity probability |
| BART-NLI | Zero-shot classification | Text + labels | Class probabilities |
| EasyOCR | Text extraction | Image frames | Text + bounding boxes |

---

## Policy Engine

### Deterministic Scoring

The policy engine uses a rule-based system for deterministic verdicts:

```python
def calculate_verdict(criteria_scores: Dict[str, float], 
                     policy: PolicyConfig) -> str:
    """
    Determine verdict based on criteria scores and thresholds.
    
    Logic:
    - If ANY criterion exceeds UNSAFE threshold → UNSAFE
    - Else if ANY criterion exceeds CAUTION threshold → CAUTION  
    - Else → SAFE
    """
    for criterion, score in criteria_scores.items():
        unsafe_threshold = policy.thresholds.unsafe[criterion]
        if score >= unsafe_threshold:
            return "UNSAFE"
    
    for criterion, score in criteria_scores.items():
        caution_threshold = policy.thresholds.caution[criterion]
        if score >= caution_threshold:
            return "CAUTION"
    
    return "SAFE"
```

### Score Calculation

Each criterion score is calculated from evidence:

```python
def calculate_violence_score(state: PipelineState, 
                            policy: PolicyConfig) -> float:
    """
    Calculate violence score from multiple sources.
    """
    sources = []
    
    # Violence model detections
    if state.get("violence_segments"):
        max_violence = max(seg["violence_score"] 
                          for seg in state["violence_segments"])
        sources.append(("violence_model", max_violence, 1.5))
    
    # Weapon detections from YOLO
    weapons = [d for d in state.get("yolo_detections", []) 
               if d["class"] in WEAPON_CLASSES]
    if weapons:
        weapon_score = max(d["confidence"] for d in weapons)
        sources.append(("weapon_detection", weapon_score, 1.2))
    
    # Calculate weighted average
    if not sources:
        return 0.0
    
    total_weight = sum(weight for _, _, weight in sources)
    weighted_sum = sum(score * weight for _, score, weight in sources)
    
    return weighted_sum / total_weight
```

### Evidence Collection

All detections are preserved as evidence:

```python
def collect_evidence(state: PipelineState) -> Dict:
    """
    Collect all evidence from pipeline.
    """
    return {
        "vision": state.get("yolo_detections", []),
        "violence_segments": state.get("violence_segments", []),
        "asr": state.get("transcript", {}),
        "ocr": state.get("ocr_results", []),
        "moderation": state.get("moderation_results", {})
    }
```

---

## Batch Processing System

### Architecture

```
Client uploads [video1, video2, video3]
    ↓
API creates batch_id
    ↓
For each video:
    - Generate unique video_id
    - Save to temporary storage
    - Create background task
    - Connect WebSocket for progress
    ↓
Background tasks process in parallel
    ↓
Each task:
    1. Run pipeline
    2. Broadcast progress
    3. Store result
    ↓
Client polls batch status or receives WebSocket updates
    ↓
Return individual results per video
```

### Implementation

```python
# In-memory batch tracking
batch_jobs = {}  # batch_id → BatchInfo
batch_results = {}  # batch_id → {video_id → result}

@router.post("/evaluate/batch")
async def evaluate_batch(files: List[UploadFile], 
                        background_tasks: BackgroundTasks):
    # Create batch
    batch_id = str(uuid.uuid4())
    videos = []
    
    # Process each file
    for file in files:
        video_id = str(uuid.uuid4())
        
        # Save file
        file_path = save_uploaded_file(file, video_id)
        
        # Queue processing
        background_tasks.add_task(
            process_video, 
            video_id, 
            file_path, 
            batch_id
        )
        
        videos.append({
            "video_id": video_id,
            "filename": file.filename,
            "status": "queued"
        })
    
    # Store batch info
    batch_jobs[batch_id] = {
        "batch_id": batch_id,
        "total_videos": len(videos),
        "videos": videos,
        "status": "processing"
    }
    
    return batch_jobs[batch_id]

async def process_video(video_id: str, video_path: str, batch_id: str):
    """Background task to process one video."""
    try:
        # Run pipeline
        result = await run_pipeline(video_id, video_path)
        
        # Store result
        batch_results.setdefault(batch_id, {})[video_id] = {
            "status": "completed",
            "result": result
        }
    except Exception as e:
        batch_results.setdefault(batch_id, {})[video_id] = {
            "status": "failed",
            "error": str(e)
        }
```

---

## Real-Time Communication

### WebSocket Manager

```python
class ConnectionManager:
    def __init__(self):
        # video_id → List[WebSocket]
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, video_id: str):
        await websocket.accept()
        if video_id not in self.active_connections:
            self.active_connections[video_id] = []
        self.active_connections[video_id].append(websocket)
    
    def disconnect(self, websocket: WebSocket, video_id: str):
        if video_id in self.active_connections:
            self.active_connections[video_id].remove(websocket)
    
    async def broadcast(self, video_id: str, message: dict):
        """Send message to all clients watching this video."""
        if video_id not in self.active_connections:
            return
        
        dead_connections = []
        for connection in self.active_connections[video_id]:
            try:
                await connection.send_json(message)
            except:
                dead_connections.append(connection)
        
        # Clean up dead connections
        for conn in dead_connections:
            self.active_connections[video_id].remove(conn)

# Global manager instance
manager = ConnectionManager()
```

### Progress Broadcasting

```python
async def update_progress(video_id: str, 
                         stage: str, 
                         progress: int,
                         message: str = None,
                         stage_output: dict = None):
    """
    Broadcast progress update to all connected clients.
    """
    await manager.broadcast(video_id, {
        "stage": stage,
        "progress": progress,
        "message": message or f"Processing {stage}...",
        "stage_output": stage_output
    })
```

---

## Persistence Layer

### Result Storage

```python
class ResultStore:
    """Singleton for managing persistent results."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.results_file = Path(settings.data_dir) / "results.json"
        return cls._instance
    
    def save_results(self, results: List[Dict]):
        """Save results to JSON file."""
        with open(self.results_file, 'w') as f:
            json.dump(results, f, indent=2)
    
    def load_results(self) -> List[Dict]:
        """Load results from JSON file."""
        if not self.results_file.exists():
            return []
        
        with open(self.results_file, 'r') as f:
            return json.load(f)
    
    def delete_result(self, video_id: str):
        """Delete a specific result."""
        results = self.load_results()
        results = [r for r in results if r["id"] != video_id]
        self.save_results(results)
```

### Checkpoint System

**Client-side (LocalStorage):**
```javascript
function saveCheckpoint(videoId, batchVideoId, progress, stage) {
    const checkpoint = {
        videoId,
        batchVideoId,
        progress,
        stage,
        timestamp: Date.now()
    };
    localStorage.setItem(`checkpoint_${batchVideoId}`, JSON.stringify(checkpoint));
}

function loadCheckpoints() {
    const checkpoints = [];
    for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key.startsWith('checkpoint_')) {
            checkpoints.push(JSON.parse(localStorage.getItem(key)));
        }
    }
    return checkpoints;
}
```

**Server-side (Persistent uploads):**
```python
# Original videos saved to disk
UPLOADS_DIR = Path(settings.data_dir) / "uploads"
file_path = UPLOADS_DIR / f"{batch_video_id}.mp4"

# Can be retrieved for retry
@router.get("/video/uploaded/{video_id}")
async def get_uploaded_video(video_id: str):
    file_path = UPLOADS_DIR / f"{video_id}.mp4"
    if not file_path.exists():
        raise HTTPException(404, "Video not found")
    return FileResponse(file_path)
```

---

## Video Processing

### Frame Extraction

```python
def extract_frames(video_path: str, fps: float = 1.0) -> List[Dict]:
    """
    Extract frames from video at specified FPS.
    
    Uses FFmpeg for efficient extraction:
    ffmpeg -i input.mp4 -vf fps=1 frame_%04d.jpg
    """
    output_pattern = work_dir / "frame_%04d.jpg"
    
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"fps={fps}",
        str(output_pattern)
    ]
    
    subprocess.run(cmd, check=True, capture_output=True)
    
    # Return frame info
    return [
        {
            "frame_index": i,
            "timestamp": i / fps,
            "path": str(work_dir / f"frame_{i:04d}.jpg")
        }
        for i in range(frame_count)
    ]
```

### Labeled Video Generation

```python
def create_labeled_video(video_path: str, 
                        detections: List[Dict],
                        output_path: str):
    """
    Create video with bounding boxes drawn on detections.
    
    Steps:
    1. Read frames with OpenCV
    2. Draw bounding boxes on frames with detections
    3. Write frames to temp AVI (XVID codec)
    4. Re-encode to H.264 MP4 with FFmpeg for browser compatibility
    """
    # Step 1 & 2: Draw boxes
    cap = cv2.VideoCapture(video_path)
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    out = cv2.VideoWriter(temp_avi, fourcc, fps, (width, height))
    
    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        # Get detections for this frame (with temporal smoothing)
        frame_detections = get_detections_for_frame(frame_idx, detections)
        
        # Draw boxes
        for det in frame_detections:
            x1, y1, x2, y2 = det["bbox"]
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, det["class"], (x1, y1-10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        out.write(frame)
        frame_idx += 1
    
    cap.release()
    out.release()
    
    # Step 3: Re-encode to H.264
    cmd = [
        "ffmpeg", "-i", temp_avi,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        output_path
    ]
    subprocess.run(cmd, check=True)
```

### Temporal Smoothing

To reduce flickering in labeled videos:

```python
def get_detections_for_frame(frame_idx: int, 
                            all_detections: List[Dict],
                            window_sec: float = 1.0,
                            fps: float = 30.0) -> List[Dict]:
    """
    Get detections for a frame, using nearest detection within window.
    
    This prevents flickering by persisting boxes across nearby frames.
    """
    frame_time = frame_idx / fps
    window_frames = int(window_sec * fps)
    
    # Find detections within window
    nearby_detections = []
    for det in all_detections:
        det_frame = int(det["timestamp"] * fps)
        if abs(det_frame - frame_idx) <= window_frames:
            nearby_detections.append(det)
    
    # Group by class and keep nearest for each
    result = {}
    for det in nearby_detections:
        cls = det["class"]
        det_frame = int(det["timestamp"] * fps)
        distance = abs(det_frame - frame_idx)
        
        if cls not in result or distance < result[cls]["distance"]:
            result[cls] = {**det, "distance": distance}
    
    return [d for d in result.values()]
```

---

## Design Decisions

### Why LangGraph?

1. **Stateful**: Pipeline state flows through nodes
2. **Debuggable**: Each node is independently testable
3. **Extensible**: Easy to add/remove/reorder nodes
4. **Error handling**: Built-in retry and error propagation
5. **Visualization**: Graph structure is self-documenting

### Why Deterministic Policy?

1. **Reproducibility**: Same inputs always produce same verdict
2. **Auditability**: Decisions are explainable
3. **Compliance**: Meets regulatory requirements
4. **Trust**: LLM doesn't make safety decisions
5. **Configurability**: Thresholds can be tuned

### Why In-Memory Batch Storage?

**Pros:**
- Simple implementation
- Fast access
- No external dependencies

**Cons:**
- Lost on restart
- Doesn't scale horizontally
- No persistence

**Production Alternative:** Use Redis or PostgreSQL

### Why WebSocket for Progress?

**Alternatives considered:**
- Server-Sent Events: One-way only
- Polling: Inefficient, delayed updates
- Long polling: Complex connection management

**Why WebSocket:**
- Real-time bidirectional
- Low overhead
- Native browser support
- FastAPI support

---

## Security Considerations

### Input Validation

```python
# File size limits
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB

# Allowed MIME types
ALLOWED_TYPES = ["video/mp4", "video/avi", "video/mov", "video/mkv"]

# Filename sanitization
safe_filename = secure_filename(upload.filename)
```

### Path Traversal Prevention

```python
# All file operations in controlled directories
work_dir = Path(settings.temp_dir) / video_id
work_dir.mkdir(parents=True, exist_ok=True)

# Validate paths stay within work_dir
def safe_path(base: Path, user_input: str) -> Path:
    target = (base / user_input).resolve()
    if not target.is_relative_to(base):
        raise ValueError("Path traversal detected")
    return target
```

### API Key Security

```python
# Never log API keys
logger.info(f"Using OpenAI model: {settings.openai_model}")
# NOT: logger.info(f"API key: {settings.openai_api_key}")

# Load from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Use secrets in production
# Docker: --secret openai_key
# K8s: secretKeyRef
```

### CORS Configuration

```python
# Restrict origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],  # Specific origins only
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)
```

---

## Performance Optimization

### Model Loading

- **Singleton pattern**: Load models once
- **Lazy loading**: Load on first use
- **Caching**: Use HuggingFace cache
- **GPU acceleration**: Automatic CUDA detection

### Batch Processing

- **Parallel execution**: Process videos concurrently
- **Background tasks**: Non-blocking API responses
- **Resource limits**: Limit concurrent jobs

### Frame Processing

- **Sampling**: Extract frames at 1 FPS (configurable)
- **Resolution**: Process at original resolution
- **Batch inference**: Process multiple frames together

### Memory Management

- **Cleanup**: Delete temp files after processing
- **Frame limits**: Cap max frames per video
- **Garbage collection**: Explicit cleanup in nodes

---

## Extension Points

### Adding a New Model

1. Create wrapper in `app/models/`:
```python
# app/models/custom_model.py
class CustomModel:
    _instance = None
    
    def __new__(cls):
        # Singleton pattern
        ...
    
    def predict(self, inputs):
        # Inference logic
        ...
```

2. Add node in `app/pipeline/nodes/`:
```python
# app/pipeline/nodes/custom_node.py
async def custom_node(state: PipelineState) -> PipelineState:
    # Use model
    model = CustomModel()
    results = model.predict(state["frames"])
    
    # Update state
    state["custom_results"] = results
    return state
```

3. Update graph:
```python
# app/pipeline/graph.py
graph.add_node("custom_node", custom_node)
graph.add_edge("ocr_extraction", "custom_node")
graph.add_edge("custom_node", "text_moderation")
```

4. Update policy fusion to use new evidence

### Adding a New Criterion

1. Update policy config:
```python
# app/core/config.py
threshold_unsafe_custom: float = 0.70
threshold_caution_custom: float = 0.40
weight_custom: float = 1.0
```

2. Add scoring logic:
```python
# app/pipeline/nodes/fuse_policy.py
def calculate_custom_score(state, policy):
    # Calculate score from evidence
    ...
    return score

# In fuse_policy_node:
criteria_scores["custom"] = calculate_custom_score(state, policy)
```

3. Update response schema:
```python
# app/api/schemas.py
class CriteriaScores(BaseModel):
    # ... existing fields
    custom: CriterionScore
```

---

## Conclusion

SafeVid's architecture prioritizes:
- **Modularity**: Easy to understand and extend
- **Reliability**: Deterministic, reproducible results
- **Performance**: Optimized for concurrent processing
- **Maintainability**: Clear separation of concerns

For implementation details, see the source code. For usage, see [API.md](API.md) and [SETUP.md](SETUP.md).
