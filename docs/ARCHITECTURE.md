# Judex Architecture Guide

Deep dive into the Judex system architecture, design decisions, and implementation details.

## Table of Contents

- [System Overview](#system-overview)
- [Technology Stack](#technology-stack)
- [Pipeline Architecture](#pipeline-architecture)
- [StagePlugin System](#stageplugin-system)
- [Criteria & Fusion Engine](#criteria--fusion-engine)
- [Data Flow](#data-flow)
- [Storage Architecture](#storage-architecture)
- [Real-Time Communication](#real-time-communication)
- [Model Integration](#model-integration)
- [Design Decisions](#design-decisions)

---

## System Overview

Judex is a multi-modal video evaluation framework built on a pluggable pipeline architecture. The system evaluates videos against configurable criteria using multiple AI models and produces deterministic verdicts.

### High-Level Architecture

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
│  POST /v1/evaluate        - Submit video for evaluation      │
│  GET  /v1/evaluations/*   - Query results & artifacts        │
│  GET  /v1/criteria/*      - Manage evaluation criteria       │
│  GET  /v1/evaluations/{id}/events - SSE progress stream      │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│              LangGraph Pipeline (Stable Graph)                │
│                                                               │
│  ingest_video → segment_video → run_pipeline → fuse_policy   │
│                                      │            → llm_report│
│                         ┌────────────┴────────────┐          │
│                         │    PipelineRunner       │          │
│                         │  (Dynamic Stage Exec)   │          │
│                         │                         │          │
│                         │  ┌─────┐ ┌─────────┐   │          │
│                         │  │yolo │ │yoloworld│   │          │
│                         │  └─────┘ └─────────┘   │          │
│                         │  ┌────────┐ ┌───────┐  │          │
│                         │  │violence│ │whisper│  │          │
│                         │  └────────┘ └───────┘  │          │
│                         │  ┌───┐ ┌──────────┐    │          │
│                         │  │ocr│ │moderation│    │          │
│                         │  └───┘ └──────────┘    │          │
│                         └────────────────────────┘          │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                      Storage Layer                            │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │   PostgreSQL    │  │     MinIO       │                   │
│  │  - Evaluations  │  │  - Videos       │                   │
│  │  - Results      │  │  - Frames       │                   │
│  │  - Criteria     │  │  - Thumbnails   │                   │
│  │  - Evidence     │  │  - Artifacts    │                   │
│  └─────────────────┘  └─────────────────┘                   │
└──────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

### Backend

| Component | Technology | Purpose |
|-----------|------------|---------|
| Web Framework | FastAPI | Async REST API, OpenAPI docs |
| Pipeline | LangGraph | Stateful workflow orchestration |
| ORM | SQLAlchemy | Database abstraction |
| Validation | Pydantic | Request/response schemas |

### AI/ML

| Model | Library | Purpose |
|-------|---------|---------|
| YOLO26 | Ultralytics | Object detection |
| YOLO-World | Ultralytics | Open-vocabulary detection |
| X-CLIP | HuggingFace | Violence detection (temporal) |
| Whisper | HuggingFace | Audio transcription |
| PardonMyAI | HuggingFace | Profanity detection |
| BART-NLI | HuggingFace | Text moderation |

### Frontend

| Component | Technology | Purpose |
|-----------|------------|---------|
| Framework | React 18 | UI components |
| Language | TypeScript | Type safety |
| Styling | Tailwind CSS | Utility-first CSS |
| State | Zustand | Global state management |
| Build | Vite | Fast development/build |

### Infrastructure

| Component | Technology | Purpose |
|-----------|------------|---------|
| Database | PostgreSQL 14+ | Metadata, results, criteria |
| Object Storage | MinIO | Videos, frames, artifacts |
| Container | Docker | Deployment |
| Orchestration | Docker Compose | Multi-service management |

---

## Pipeline Architecture

### Stable LangGraph

The core pipeline is a **stable LangGraph** with a fixed set of nodes. Dynamic stage execution happens inside the `run_pipeline` node via the `PipelineRunner`.

```python
# pipeline/graph.py
from langgraph.graph import StateGraph, END

def build_evaluation_graph():
    workflow = StateGraph(PipelineState)
    
    # Fixed nodes (never changes)
    workflow.add_node("ingest_video", ingest_video)
    workflow.add_node("segment_video", segment_video)
    workflow.add_node("run_pipeline", run_pipeline_node)  # Dynamic stages
    workflow.add_node("fuse_policy", fuse_policy_generic)
    workflow.add_node("generate_llm_report", generate_llm_report)
    
    # Fixed edges
    workflow.add_edge("ingest_video", "segment_video")
    workflow.add_edge("segment_video", "run_pipeline")
    workflow.add_edge("run_pipeline", "fuse_policy")
    workflow.add_edge("fuse_policy", "generate_llm_report")
    workflow.add_edge("generate_llm_report", END)
    
    return workflow.compile()
```

### Pipeline Nodes

| Node | Purpose | Key Outputs |
|------|---------|-------------|
| `ingest_video` | Validate, normalize (720p@30fps), upload to MinIO | `video_path`, `uploaded_video_path` |
| `segment_video` | Extract keyframes (1fps), generate thumbnails | `sampled_frames`, `segment_clips` |
| `run_pipeline` | Execute dynamic stages via PipelineRunner | Stage-specific outputs |
| `fuse_policy` | Compute criterion scores, determine verdict | `criteria_scores`, `verdict` |
| `llm_report` | Generate AI summary (optional) | `report` |

---

## StagePlugin System

### Overview

The `StagePlugin` system provides a pluggable architecture for detector stages. Each plugin wraps an existing node function.

```python
# pipeline/stages/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class StagePlugin(ABC):
    """Base class for pipeline stage plugins."""
    
    @property
    @abstractmethod
    def stage_type(self) -> str:
        """Unique identifier for this stage type."""
        pass
    
    @property
    def display_name(self) -> str:
        """Human-readable name for UI display."""
        return self.stage_type.replace("_", " ").title()
    
    @property
    def input_keys(self) -> List[str]:
        """State keys required by this stage."""
        return []
    
    @property
    def output_keys(self) -> List[str]:
        """State keys produced by this stage."""
        return []
    
    @abstractmethod
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the stage and return updated state."""
        pass
    
    def get_stage_output(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Extract stage-specific output for API response."""
        return {}
    
    def validate_state(self, state: Dict[str, Any]) -> bool:
        """Check if required inputs are present."""
        return all(key in state for key in self.input_keys)
```

### Built-in Plugins

| Plugin | Stage Type | Wraps | Purpose |
|--------|------------|-------|---------|
| `Yolo26StagePlugin` | `yolo26` | `run_yolo26_vision` | Object detection |
| `YoloWorldStagePlugin` | `yoloworld` | `run_yoloworld_vision` | Open-vocab detection |
| `ViolenceStagePlugin` | `violence` | `run_violence_video` | Temporal violence |
| `WhisperStagePlugin` | `whisper` | `run_audio_asr` | Audio transcription |
| `OcrStagePlugin` | `ocr` | `run_ocr` | Text extraction |
| `TextModerationStagePlugin` | `text_moderation` | `run_text_moderation` | Content moderation |

### StageRegistry

```python
# pipeline/stages/registry.py
class StageRegistry:
    """Singleton registry for stage plugins."""
    
    _instance = None
    _stages: Dict[str, Type[StagePlugin]] = {}
    
    @classmethod
    def register(cls, stage_class: Type[StagePlugin]):
        """Register a stage plugin."""
        instance = stage_class()
        cls._stages[instance.stage_type] = stage_class
    
    @classmethod
    def get(cls, stage_type: str) -> Optional[StagePlugin]:
        """Get a stage plugin by type."""
        if stage_type in cls._stages:
            return cls._stages[stage_type]()
        return None
```

### PipelineRunner

```python
# pipeline/runner.py
class PipelineRunner:
    """Executes a sequence of stages dynamically."""
    
    def __init__(self, stages: List[str], progress_callback=None):
        self.stages = stages
        self.progress_callback = progress_callback
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute all stages sequentially."""
        for stage_type in self.stages:
            plugin = StageRegistry.get(stage_type)
            if not plugin:
                continue
            
            # Update progress
            state["current_stage"] = stage_type
            
            # Validate inputs
            if not plugin.validate_state(state):
                state["errors"].append(f"Missing inputs for {stage_type}")
                continue
            
            # Execute stage
            state = plugin.run(state)
            
            # Save stage output
            output = plugin.get_stage_output(state)
            state["stage_outputs"][stage_type] = output
        
        return state
```

---

## Criteria & Fusion Engine

### EvaluationCriteria

User-defined criteria are parsed into an `EvaluationCriteria` object:

```python
# evaluation/criteria.py
class CriterionConfig(BaseModel):
    id: str
    label: Optional[str] = None
    description: Optional[str] = None
    weight: float = 1.0
    threshold: float = 0.5
    keywords: List[str] = []

class FusionConfig(BaseModel):
    strategy: str = "weighted_average"

class VerdictConfig(BaseModel):
    strategy: str = "threshold"
    safe_threshold: float = 0.3
    unsafe_threshold: float = 0.7

class EvaluationCriteria(BaseModel):
    name: str
    version: str = "1.0"
    description: Optional[str] = None
    criteria: List[CriterionConfig]
    fusion: FusionConfig = FusionConfig()
    verdict: VerdictConfig = VerdictConfig()
```

### Auto-Routing

Criteria IDs are automatically mapped to required detectors:

```python
# evaluation/routing.py
CRITERION_TO_DETECTORS = {
    "violence": ["violence", "yolo26"],
    "profanity": ["whisper", "text_moderation"],
    "sexual_content": ["yolo26", "yoloworld", "ocr", "text_moderation"],
    "drugs": ["yolo26", "yoloworld", "ocr"],
    "hate_speech": ["whisper", "ocr", "text_moderation"],
    "weapons": ["yolo26", "yoloworld"],
}
```

### Fusion Strategies

```python
# fusion/strategies.py
class FusionStrategy(ABC):
    @abstractmethod
    def fuse(self, scores: Dict[str, float], weights: Dict[str, float]) -> float:
        pass

class WeightedAverageStrategy(FusionStrategy):
    def fuse(self, scores, weights):
        total_weight = sum(weights.values())
        return sum(scores[k] * weights[k] for k in scores) / total_weight

class MaxStrategy(FusionStrategy):
    def fuse(self, scores, weights):
        return max(scores.values())
```

### Verdict Determination

```python
# fusion/verdict.py
class VerdictStrategy(ABC):
    @abstractmethod
    def determine(self, scores: Dict[str, float], config: VerdictConfig) -> str:
        pass

class ThresholdVerdictStrategy(VerdictStrategy):
    def determine(self, scores, config):
        max_score = max(scores.values()) if scores else 0
        if max_score >= config.unsafe_threshold:
            return "UNSAFE"
        elif max_score >= config.safe_threshold:
            return "CAUTION"
        return "SAFE"
```

---

## Data Flow

### Evaluation Flow

```
1. POST /v1/evaluate
   └── Create Evaluation record
   └── Create EvaluationItem record
   └── Upload video to MinIO
   └── Start pipeline (background)

2. Pipeline Execution
   └── ingest_video: Normalize video
   └── segment_video: Extract frames/thumbnails
   └── run_pipeline: Execute detectors
       └── yolo26 → yoloworld → violence → whisper → ocr → moderation
   └── fuse_policy: Compute scores & verdict
   └── llm_report: Generate summary

3. Progress Updates (SSE)
   └── Stage transitions broadcast to connected clients
   └── Final result saved to PostgreSQL

4. GET /v1/evaluations/{id}
   └── Return status, results, artifact paths
```

### State Object

```python
# pipeline/state.py
class PipelineState(TypedDict, total=False):
    # Input
    video_path: str
    video_id: str
    item_id: str
    evaluation_criteria: Dict[str, Any]
    
    # Processing
    work_dir: str
    fps: float
    duration: float
    sampled_frames: List[Dict]
    segment_clips: List[Dict]
    current_stage: str
    
    # Detector outputs
    vision_detections: List[Dict]
    violence_segments: List[Dict]
    transcript: str
    ocr_text: str
    moderation_results: Dict
    
    # Results
    criteria_scores: Dict[str, Dict]
    verdict: str
    confidence: float
    violations: List[Dict]
    report: str
    
    # Artifacts
    uploaded_video_path: str
    labeled_video_path: str
    stage_outputs: Dict[str, Any]
    errors: List[str]
```

---

## Storage Architecture

### PostgreSQL Schema

```sql
-- Evaluations (parent)
CREATE TABLE evaluations (
    id VARCHAR PRIMARY KEY,
    status VARCHAR NOT NULL,
    criteria_id VARCHAR,
    created_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Evaluation Items (children)
CREATE TABLE evaluation_items (
    id VARCHAR PRIMARY KEY,
    evaluation_id VARCHAR REFERENCES evaluations(id),
    filename VARCHAR,
    status VARCHAR,
    current_stage VARCHAR,
    progress INTEGER,
    result JSONB,
    stage_outputs JSONB,
    uploaded_video_path VARCHAR,
    labeled_video_path VARCHAR,
    error_message TEXT
);

-- Custom Criteria
CREATE TABLE criteria (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    content TEXT NOT NULL,
    is_builtin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP
);
```

### MinIO Structure

```
judex/
├── uploaded/
│   └── {item_id}/
│       └── video.mp4
├── labeled/
│   └── {item_id}/
│       └── labeled.mp4
├── frames/
│   └── {item_id}/
│       └── frame_00001_1500.jpg
├── frame_thumbs/
│   └── {item_id}/
│       └── frame_00001_1500.jpg
└── thumbnails/
    └── {item_id}/
        └── thumb.jpg
```

---

## Real-Time Communication

### SSE (Server-Sent Events)

```python
# api/sse.py
class SSEManager:
    def __init__(self):
        self._connections: Dict[str, List[Queue]] = {}
    
    async def subscribe(self, evaluation_id: str):
        queue = asyncio.Queue()
        self._connections.setdefault(evaluation_id, []).append(queue)
        try:
            while True:
                data = await queue.get()
                yield f"event: {data['event']}\ndata: {json.dumps(data)}\n\n"
        finally:
            self._connections[evaluation_id].remove(queue)
    
    async def broadcast(self, evaluation_id: str, event: str, data: dict):
        if evaluation_id in self._connections:
            for queue in self._connections[evaluation_id]:
                await queue.put({"event": event, **data})
```

### Event Types

| Event | Description | Data |
|-------|-------------|------|
| `progress` | Stage progress update | `stage`, `progress`, `message` |
| `stage_complete` | Stage finished | `stage`, `output` |
| `complete` | Evaluation finished | `result` |
| `error` | Error occurred | `error`, `stage` |

---

## Model Integration

### Singleton Pattern

All models use the singleton pattern for efficient memory usage:

```python
# models/yolo26.py
class YOLO26Model:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._model = None
        return cls._instance
    
    def load(self):
        if self._model is None:
            self._model = YOLO("openvision/yolo26-s")
        return self._model

def get_yolo26_model():
    return YOLO26Model().load()
```

### Model Registry

```python
# models/__init__.py
def preload_all_models():
    """Pre-load all models at startup."""
    from .yolo26 import get_yolo26_model
    from .violence_xclip import get_violence_model
    from .whisper_asr import get_whisper_model
    # ... etc
```

---

## Design Decisions

### Why Stable LangGraph?

**Before:** Dynamic graph built per request based on criteria.
- ❌ Graph compilation overhead per request
- ❌ Complex conditional logic in graph builder
- ❌ Harder to debug and maintain

**After:** Stable graph with dynamic execution inside `run_pipeline`.
- ✅ Graph compiled once at startup
- ✅ Dynamic behavior encapsulated in PipelineRunner
- ✅ Easier to test and extend

### Why StagePlugins?

- **Encapsulation:** Each detector is self-contained
- **Reusability:** Wraps existing node functions
- **Extensibility:** Easy to add new detectors
- **Testability:** Plugins can be tested in isolation

### Why PostgreSQL + MinIO?

- **PostgreSQL:** Structured data, relationships, queries
- **MinIO:** Large binary files (videos, frames)
- **Separation of concerns:** Metadata vs. artifacts

### Why SSE over WebSocket?

- **Simpler:** One-way server-to-client communication
- **Reliable:** Automatic reconnection in browsers
- **Scalable:** Easier to load balance

---

## Conclusion

Judex's architecture prioritizes:

- **Modularity:** Easy to understand and extend
- **Reliability:** Deterministic, reproducible results
- **Scalability:** Pluggable stages, stable pipeline
- **Observability:** Real-time progress, structured logs

**For API details, see [API.md](API.md). For setup instructions, see [SETUP.md](SETUP.md).**
