# SafeVid Developer Quick Reference

Quick reference guide for common development tasks and patterns.

## Table of Contents

- [Common Commands](#common-commands)
- [API Endpoints Quick Reference](#api-endpoints-quick-reference)
- [Pipeline Nodes](#pipeline-nodes)
- [Configuration Reference](#configuration-reference)
- [Code Patterns](#code-patterns)
- [Testing](#testing)
- [Debugging](#debugging)
- [Common Tasks](#common-tasks)

---

## Common Commands

### Docker Operations

```bash
# Build and start
docker-compose -f docker/docker-compose.yml up --build

# Start detached
docker-compose -f docker/docker-compose.yml up -d

# View logs
docker-compose -f docker/docker-compose.yml logs -f safevid

# Stop services
docker-compose -f docker/docker-compose.yml down

# Rebuild without cache
docker-compose -f docker/docker-compose.yml build --no-cache

# Clean everything (including volumes)
docker-compose -f docker/docker-compose.yml down -v
```

### Local Development

```bash
# Setup
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Run backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8012

# Run UI server
cd ui && python server.py

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html

# Type checking
mypy app/

# Linting
flake8 app/
black app/
```

### Model Management

```bash
# Pre-download models
python scripts/prefetch_models.py

# Check model cache
ls -la $HF_HOME/hub/

# Clear model cache
rm -rf $HF_HOME/hub/

# Check disk usage
du -sh $HF_HOME
```

---

## API Endpoints Quick Reference

| Method | Endpoint | Purpose | Auth |
|--------|----------|---------|------|
| GET | `/v1/health` | Health check | No |
| GET | `/v1/models` | List models | No |
| POST | `/v1/evaluate` | Evaluate single video | No |
| POST | `/v1/evaluate/batch` | Evaluate multiple videos | No |
| GET | `/v1/evaluate/batch/{id}` | Get batch status | No |
| WS | `/v1/ws/{video_id}` | Progress updates | No |
| GET | `/v1/video/labeled/{id}` | Download labeled video | No |
| GET | `/v1/video/uploaded/{id}` | Download original video | No |
| POST | `/v1/results/save` | Save results | No |
| GET | `/v1/results/load` | Load saved results | No |
| DELETE | `/v1/results/{id}` | Delete result | No |
| DELETE | `/v1/results` | Clear all results | No |

---

## Pipeline Nodes

### Node Order and Progress

| Order | Node | Progress % | Purpose |
|-------|------|-----------|---------|
| 1 | `ingest_video` | 6-8% | Validate and extract metadata |
| 2 | `segment_video` | 13-16% | Extract frames and create segments |
| 3 | `yolo26_vision` | 30-37% | Detect objects, create labeled video |
| 4 | `violence_detection` | 46-49% | Analyze segments for violence |
| 5 | `audio_transcription` | 60-62% | Transcribe audio with Whisper |
| 6 | `ocr_extraction` | 71-73% | Extract text from frames |
| 7 | `text_moderation` | 82-83% | Analyze text for violations |
| 8 | `policy_fusion` | 94% | Calculate scores and verdict |
| 9 | `report_generation` | 100% | Generate LLM summary |
| 10 | `finalize` | 100% | Package final response |
| 11 | `complete` | 0% | Signal completion |

### Node File Locations

```
app/pipeline/nodes/
├── ingest_video.py      # Video validation and metadata
├── segment_video.py     # Frame extraction and segmentation
├── yolo26_vision.py     # Object detection
├── violence_video.py    # Violence analysis with X-CLIP
├── audio_asr.py         # Audio transcription
├── ocr.py              # Text extraction
├── text_moderation.py   # Text analysis
├── fuse_policy.py       # Score calculation and verdict
├── llm_report.py        # Report generation
└── finalize.py          # Final output preparation
```

---

## Configuration Reference

### Environment Variables

```bash
# Core Settings
VERSION=1.0.0
LOG_LEVEL=INFO

# Model IDs
YOLO26_MODEL_ID=openvision/yolo26-s                      # Batch pipeline: Standard YOLO
YOLOE_MODEL_ID=yolov8n.pt                                # Live feed: Efficient real-time YOLO
YOLOWORLD_MODEL_ID=yolov8s-worldv2.pt                    # Batch pipeline: Open-vocabulary detection
VIOLENCE_MODEL_ID=microsoft/xclip-base-patch32-16-frames
WHISPER_MODEL_ID=openai/whisper-small
PROFANITY_MODEL_ID=tarekziade/pardonmyai
NLI_MODEL_ID=facebook/bart-large-mnli

# Processing
DEFAULT_SAMPLING_FPS=1.0
SEGMENT_DURATION_SEC=3.0
OCR_INTERVAL_SEC=2.0

# Paths
HF_HOME=/models/hf
TEMP_DIR=/tmp/safevid
DATA_DIR=/data/safevid
```

### Default Thresholds

```python
# UNSAFE thresholds (trigger unsafe verdict)
violence: 0.75
sexual: 0.60
hate: 0.60
drugs: 0.70
profanity: 0.80

# CAUTION thresholds (trigger caution verdict)
violence: 0.40
sexual: 0.30
hate: 0.30
drugs: 0.40
profanity: 0.40
```

### Default Weights

```python
violence: 1.5
sexual: 1.2
hate: 1.0
drugs: 1.0
profanity: 0.8
```

---

## Code Patterns

### Creating a New Pipeline Node

```python
# app/pipeline/nodes/my_node.py
from app.pipeline.state import PipelineState
from app.utils.progress import update_progress
from app.utils.timing import track_time
from app.core.logging import get_logger

logger = get_logger("pipeline.my_node")

@track_time
async def my_node(state: PipelineState) -> PipelineState:
    """
    Description of what this node does.
    
    Args:
        state: Current pipeline state
        
    Returns:
        Updated state with node results
    """
    video_id = state["video_id"]
    
    # Update progress
    await update_progress(
        video_id, 
        stage="my_node",
        progress=50,
        message="Processing..."
    )
    
    try:
        # Your processing logic here
        result = process_something(state["input_data"])
        
        # Update state
        state["my_node_output"] = result
        
    except Exception as e:
        logger.error(f"Error in my_node: {e}")
        state["error"] = str(e)
    
    return state
```

### Creating a Model Wrapper

```python
# app/models/my_model.py
import torch
from transformers import AutoModel, AutoProcessor
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("models.my_model")

class MyModel:
    """Singleton wrapper for custom model."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        logger.info("Loading MyModel...")
        
        self.model = AutoModel.from_pretrained(settings.my_model_id)
        self.processor = AutoProcessor.from_pretrained(settings.my_model_id)
        
        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        self.model.to(self.device)
        self.model.eval()
        
        self._initialized = True
        logger.info(f"MyModel loaded on {self.device}")
    
    def predict(self, inputs):
        """Run inference."""
        with torch.no_grad():
            processed = self.processor(inputs, return_tensors="pt")
            processed = {k: v.to(self.device) for k, v in processed.items()}
            
            outputs = self.model(**processed)
            
            return outputs.logits.cpu().numpy()
```

### Adding a New API Endpoint

```python
# app/api/routes.py
@router.post("/my-endpoint", response_model=MyResponse)
async def my_endpoint(
    param: str,
    file: UploadFile = File(...),
) -> MyResponse:
    """
    Description of endpoint.
    
    Args:
        param: Parameter description
        file: File description
        
    Returns:
        Response description
    """
    try:
        # Validate input
        if not file.filename.endswith('.mp4'):
            raise HTTPException(400, "Invalid file type")
        
        # Process
        result = await process_file(file)
        
        # Return response
        return MyResponse(
            status="success",
            result=result
        )
        
    except Exception as e:
        logger.error(f"Error in my_endpoint: {e}")
        raise HTTPException(500, str(e))
```

### WebSocket Progress Updates

```python
# In any pipeline node
from app.api.websocket import manager

async def my_node(state: PipelineState) -> PipelineState:
    video_id = state["video_id"]
    
    # Send progress update
    await manager.broadcast(video_id, {
        "stage": "my_node",
        "progress": 50,
        "message": "Processing...",
        "stage_output": {
            "custom_data": "value"
        }
    })
    
    return state
```

---

## Testing

### Running Tests

```bash
# All tests
pytest tests/

# Specific test file
pytest tests/test_policy_fusion.py -v

# Specific test
pytest tests/test_api_contract.py::test_health_endpoint -v

# With coverage
pytest tests/ --cov=app --cov-report=html

# Stop on first failure
pytest tests/ -x

# Show print statements
pytest tests/ -s
```

### Writing Tests

```python
# tests/test_my_feature.py
import pytest
from app.pipeline.nodes.my_node import my_node
from app.pipeline.state import PipelineState

@pytest.mark.asyncio
async def test_my_node():
    """Test my_node processes correctly."""
    # Setup
    state: PipelineState = {
        "video_id": "test-123",
        "input_data": "test input"
    }
    
    # Execute
    result = await my_node(state)
    
    # Assert
    assert "my_node_output" in result
    assert result["my_node_output"] is not None
    assert "error" not in result

def test_my_function():
    """Test helper function."""
    result = my_function("input")
    assert result == "expected"
```

### Test Fixtures

```python
# tests/conftest.py
import pytest
from pathlib import Path

@pytest.fixture
def sample_video():
    """Provide path to sample video."""
    return Path(__file__).parent / "fixtures" / "sample.mp4"

@pytest.fixture
def mock_state():
    """Provide mock pipeline state."""
    return {
        "video_id": "test-123",
        "video_path": "/path/to/video.mp4",
        "duration": 60.0,
        "fps": 30.0
    }
```

---

## Debugging

### Enabling Debug Logging

```bash
# Environment variable
export LOG_LEVEL=DEBUG

# Run with debug
uvicorn app.main:app --reload --log-level debug
```

### Logging Best Practices

```python
from app.core.logging import get_logger

logger = get_logger(__name__)

# Good logging
logger.info(f"Processing video {video_id}")
logger.debug(f"Frame {frame_idx}: {len(detections)} detections")
logger.warning(f"Low confidence detection: {confidence}")
logger.error(f"Failed to process frame {frame_idx}: {error}")

# Bad logging
print("Processing...")  # Don't use print
logger.info(f"API key: {api_key}")  # Don't log secrets
```

### Debugging Pipeline

```python
# Add debug output to nodes
logger.debug(f"State at entry: {state.keys()}")
logger.debug(f"Processing {len(state['frames'])} frames")

# Check intermediate results
if logger.level == logging.DEBUG:
    with open("/tmp/debug_output.json", "w") as f:
        json.dump(state["detections"], f, indent=2)
```

### Using Python Debugger

```python
# Add breakpoint
import pdb; pdb.set_trace()

# Or use built-in breakpoint()
breakpoint()

# Common pdb commands:
# n - next line
# s - step into
# c - continue
# p variable - print variable
# l - list code
# q - quit
```

---

## Common Tasks

### Add a New Safety Criterion

1. **Update config** (`app/core/config.py`):
```python
threshold_unsafe_my_criterion: float = 0.70
threshold_caution_my_criterion: float = 0.40
weight_my_criterion: float = 1.0
```

2. **Add detection logic** (new node or existing):
```python
state["my_criterion_detections"] = detect_my_criterion(frames)
```

3. **Update policy fusion** (`app/pipeline/nodes/fuse_policy.py`):
```python
def calculate_my_criterion_score(state, policy):
    detections = state.get("my_criterion_detections", [])
    if not detections:
        return 0.0
    return max(d["score"] for d in detections)

# In fuse_policy_node:
criteria_scores["my_criterion"] = calculate_my_criterion_score(state, policy)
```

4. **Update schemas** (`app/api/schemas.py`):
```python
class CriteriaScores(BaseModel):
    my_criterion: CriterionScore
```

### Change Default Thresholds

**Option 1: Environment variables**
```bash
export THRESHOLD_UNSAFE_VIOLENCE=0.80
```

**Option 2: Config file**
```python
# app/core/config.py
threshold_unsafe_violence: float = 0.80
```

**Option 3: Per-request**
```python
policy_override = {
    "thresholds": {
        "unsafe": {"violence": 0.80}
    }
}
```

### Add a New Model

1. **Add model ID to config**
2. **Create model wrapper** (see patterns above)
3. **Create pipeline node** (see patterns above)
4. **Update graph** (`app/pipeline/graph.py`)
5. **Update state** (`app/pipeline/state.py`)
6. **Add to prefetch** (`scripts/prefetch_models.py`)

### Modify Video Processing Parameters

```bash
# Frame extraction rate
export DEFAULT_SAMPLING_FPS=0.5  # Extract 1 frame per 2 seconds

# Violence segment duration
export SEGMENT_DURATION_SEC=5.0  # 5-second segments

# OCR frequency
export OCR_INTERVAL_SEC=3.0  # OCR every 3 seconds
```

### Add Custom Evidence to Results

```python
# In any node
state["custom_evidence"] = {
    "type": "custom",
    "data": my_custom_data
}

# In finalize node
result["evidence"]["custom"] = state.get("custom_evidence", {})
```

---

## File Structure Quick Reference

```
safeVid/
├── app/
│   ├── main.py              # FastAPI app
│   ├── api/
│   │   ├── routes.py        # API endpoints
│   │   ├── schemas.py       # Pydantic models
│   │   └── websocket.py     # WebSocket manager
│   ├── core/
│   │   ├── config.py        # Configuration
│   │   └── logging.py       # Logging setup
│   ├── models/              # Model wrappers
│   ├── pipeline/
│   │   ├── graph.py         # LangGraph definition
│   │   ├── state.py         # State TypedDict
│   │   └── nodes/           # Pipeline nodes
│   └── utils/               # Utilities
├── ui/
│   ├── index.html           # Web UI
│   └── server.py            # UI server
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── scripts/
│   └── prefetch_models.py   # Model downloader
├── tests/                   # Test suite
├── docs/                    # Documentation
└── README.md
```

---

## Quick Links

- [Main README](../README.md)
- [API Documentation](API.md)
- [Setup Guide](SETUP.md)
- [Architecture Guide](ARCHITECTURE.md)

---

For more detailed information, refer to the full documentation.
