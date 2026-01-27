# SafeVid Setup Guide

Complete setup and deployment guide for the SafeVid child safety video analysis service.

## Table of Contents

- [System Requirements](#system-requirements)
- [Quick Start with Docker](#quick-start-with-docker)
- [Local Development Setup](#local-development-setup)
- [Environment Configuration](#environment-configuration)
- [Model Management](#model-management)
- [Production Deployment](#production-deployment)
- [Troubleshooting](#troubleshooting)

---

## System Requirements

### Minimum Requirements

- **OS**: Linux, macOS, or Windows with WSL2
- **RAM**: 8GB (16GB recommended for production)
- **Storage**: 20GB free space (models + temporary files)
- **CPU**: 4 cores minimum (8+ recommended)
- **GPU**: Optional (CUDA-compatible for faster processing)

### Software Dependencies

- **Docker**: 20.10+ and Docker Compose 2.0+
- **Python**: 3.9+ (for local development)
- **FFmpeg**: 4.4+ (included in Docker image)

---

## Quick Start with Docker

The fastest way to get SafeVid running is with Docker Compose.

### 1. Clone the Repository

```bash
git clone <repository-url>
cd safeVid
```

### 2. Configure Environment (Optional)

```bash
cp env.example .env
# Edit .env with your settings (OpenAI key, etc.)
nano .env
```

### 3. Build and Run

```bash
# Build and start services
docker-compose -f docker/docker-compose.yml up --build

# Or run in detached mode
docker-compose -f docker/docker-compose.yml up -d --build
```

### 4. Verify Services

```bash
# Check API health
curl http://localhost:8012/v1/health

# Check models
curl http://localhost:8012/v1/models

# Open UI in browser
open http://localhost:8080
```

### 5. Stop Services

```bash
# Stop containers
docker-compose -f docker/docker-compose.yml down

# Stop and remove volumes (deletes cached models)
docker-compose -f docker/docker-compose.yml down -v
```

---

## Local Development Setup

For development without Docker, follow these steps:

### 1. Create Virtual Environment

```bash
# Create venv
python3 -m venv venv

# Activate (Linux/macOS)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate
```

### 2. Install Dependencies

```bash
# Install Python packages
pip install --upgrade pip
pip install -r requirements.txt

# Install test dependencies (optional)
pip install -r tests/requirements-test.txt
```

### 3. Install FFmpeg

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH.

### 4. Install EasyOCR Dependencies

```bash
# EasyOCR requires specific system packages
# Ubuntu/Debian:
sudo apt install libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1

# macOS: (usually not needed)
# Windows: (usually not needed)
```

### 5. Configure Environment

```bash
# Copy example env
cp env.example .env

# Set required paths
export HF_HOME=./models/hf
export TRANSFORMERS_CACHE=./models/hf/transformers
export TEMP_DIR=./tmp/safevid
export DATA_DIR=./data/safevid

# Create directories
mkdir -p $HF_HOME
mkdir -p $TEMP_DIR
mkdir -p $DATA_DIR
```

### 6. Pre-download Models (Optional but Recommended)

```bash
# Download all models before first run
python scripts/prefetch_models.py

# This can take 10-20 minutes depending on connection
# Models are ~5GB total
```

### 7. Run Backend Server

```bash
# Development mode (auto-reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8012

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8012 --workers 4
```

### 8. Run UI Server (separate terminal)

```bash
cd ui
python server.py

# UI will be available at http://localhost:8080
```

---

## Environment Configuration

### Environment Variables

Create a `.env` file in the project root or set these as system environment variables:

```bash
# ===== Model Configuration =====
YOLO26_MODEL_ID=openvision/yolo26-s
VIOLENCE_MODEL_ID=microsoft/xclip-base-patch32-16-frames
USE_XCLIP_VIOLENCE=true
WHISPER_MODEL_ID=openai/whisper-small
PROFANITY_MODEL_ID=tarekziade/pardonmyai
NLI_MODEL_ID=facebook/bart-large-mnli

# ===== OpenAI Configuration (Optional) =====
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o-mini

# ===== Processing Parameters =====
DEFAULT_SAMPLING_FPS=1.0
SEGMENT_DURATION_SEC=3.0
VIOLENCE_FRAMES_PER_SEGMENT=16
OCR_INTERVAL_SEC=2.0

# ===== Policy Thresholds =====
THRESHOLD_UNSAFE_VIOLENCE=0.75
THRESHOLD_UNSAFE_SEXUAL=0.60
THRESHOLD_UNSAFE_HATE=0.60
THRESHOLD_UNSAFE_DRUGS=0.70
THRESHOLD_UNSAFE_PROFANITY=0.80

THRESHOLD_CAUTION_VIOLENCE=0.40
THRESHOLD_CAUTION_SEXUAL=0.30
THRESHOLD_CAUTION_HATE=0.30
THRESHOLD_CAUTION_DRUGS=0.40
THRESHOLD_CAUTION_PROFANITY=0.40

# ===== Scoring Weights =====
WEIGHT_VIOLENCE=1.5
WEIGHT_SEXUAL=1.2
WEIGHT_HATE=1.0
WEIGHT_DRUGS=1.0
WEIGHT_PROFANITY=0.8

# ===== Paths =====
HF_HOME=/models/hf
TRANSFORMERS_CACHE=/models/hf/transformers
TEMP_DIR=/tmp/safevid
DATA_DIR=/data/safevid

# ===== Service Configuration =====
VERSION=1.0.0
LOG_LEVEL=INFO
MAX_WORKERS=4
```

### Configuration Hierarchy

Settings are loaded in this order (later overrides earlier):

1. Default values in `app/core/config.py`
2. Environment variables
3. `.env` file
4. Per-request policy overrides (API)

---

## Model Management

### Model Storage

Models are cached in the location specified by `HF_HOME`:

```
/models/hf/
├── hub/
│   ├── models--openvision--yolo26-s/
│   ├── models--microsoft--xclip-base-patch32-16-frames/
│   ├── models--openai--whisper-small/
│   ├── models--tarekziade--pardonmyai/
│   └── models--facebook--bart-large-mnli/
└── transformers/
    └── (cached transformers files)
```

### Pre-downloading Models

**Option 1: Use prefetch script**
```bash
python scripts/prefetch_models.py
```

**Option 2: First-run download**
```bash
# Models download automatically on first use
# This adds ~5-10 minutes to first request
```

**Option 3: Docker volume**
```bash
# Docker automatically caches models in named volume
# Volume persists between container restarts
docker volume ls | grep models
```

### Model Sizes

| Model | Size | Download Time (100 Mbps) |
|-------|------|--------------------------|
| YOLO26-S | ~50 MB | ~5 seconds |
| X-CLIP | ~600 MB | ~50 seconds |
| Whisper Small | ~500 MB | ~40 seconds |
| PardonMyAI | ~500 MB | ~40 seconds |
| BART-Large-MNLI | ~1.6 GB | ~2 minutes |
| EasyOCR (auto) | ~100 MB | ~10 seconds |
| **Total** | **~3.4 GB** | **~4 minutes** |

### Changing Models

To use different model variants:

1. Update model ID in `.env`:
```bash
# Example: Use larger Whisper model
WHISPER_MODEL_ID=openai/whisper-medium
```

2. Restart service:
```bash
docker-compose -f docker/docker-compose.yml restart
```

3. New model downloads automatically on first use

### GPU Acceleration (Optional)

To use GPU for faster processing:

1. Install NVIDIA Container Toolkit:
```bash
# Ubuntu/Debian
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo systemctl restart docker
```

2. Update `docker-compose.yml`:
```yaml
services:
  safevid:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

3. Rebuild and run:
```bash
docker-compose -f docker/docker-compose.yml up --build
```

---

## Production Deployment

### Docker Production Setup

1. **Use environment variables for secrets:**
```bash
# Don't commit .env to git
echo ".env" >> .gitignore

# Use secret management in production
export OPENAI_API_KEY=$(cat /run/secrets/openai_key)
```

2. **Configure resource limits:**
```yaml
# docker-compose.yml
services:
  safevid:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G
```

3. **Enable health checks:**
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8012/v1/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

4. **Use production server:**
```bash
# Multiple workers for concurrent requests
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8012", "--workers", "4"]
```

### Kubernetes Deployment

Example Kubernetes manifests:

**Deployment:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: safevid
spec:
  replicas: 3
  selector:
    matchLabels:
      app: safevid
  template:
    metadata:
      labels:
        app: safevid
    spec:
      containers:
      - name: safevid
        image: safevid:latest
        ports:
        - containerPort: 8012
        env:
        - name: HF_HOME
          value: /models/hf
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: safevid-secrets
              key: openai-key
        volumeMounts:
        - name: models
          mountPath: /models
        - name: data
          mountPath: /data
        resources:
          requests:
            memory: "4Gi"
            cpu: "2"
          limits:
            memory: "8Gi"
            cpu: "4"
      volumes:
      - name: models
        persistentVolumeClaim:
          claimName: safevid-models-pvc
      - name: data
        persistentVolumeClaim:
          claimName: safevid-data-pvc
```

**Service:**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: safevid
spec:
  selector:
    app: safevid
  ports:
  - port: 8012
    targetPort: 8012
  type: LoadBalancer
```

### Monitoring and Logging

1. **Enable structured logging:**
```python
# app/core/logging.py already configured
LOG_LEVEL=INFO  # or DEBUG for verbose
```

2. **Monitor health endpoint:**
```bash
# Set up monitoring to check /v1/health
curl http://localhost:8012/v1/health
```

3. **Log aggregation:**
```bash
# Docker logs
docker-compose logs -f safevid

# Export to file
docker-compose logs safevid > safevid.log
```

### Scaling Considerations

- **Horizontal Scaling**: Multiple instances behind load balancer
- **Batch Processing**: Adjust `MAX_WORKERS` based on CPU cores
- **Model Caching**: Share model volume across instances (read-only)
- **Result Storage**: Use external database instead of local JSON files
- **WebSocket**: Consider Redis for WebSocket message broker

---

## Troubleshooting

### Common Issues

#### 1. Models Not Loading

**Symptom:** 500 errors or "models not loaded" message

**Solutions:**
```bash
# Check model cache
ls -la $HF_HOME/hub/

# Re-download models
rm -rf $HF_HOME/hub/
python scripts/prefetch_models.py

# Check disk space
df -h
```

#### 2. Out of Memory

**Symptom:** Container crashes or OOM kills

**Solutions:**
```bash
# Increase Docker memory limit
# Docker Desktop → Settings → Resources → Memory → 8GB+

# Reduce concurrent workers
export MAX_WORKERS=2

# Use smaller models
export WHISPER_MODEL_ID=openai/whisper-tiny
```

#### 3. FFmpeg Errors

**Symptom:** Video processing fails with FFmpeg errors

**Solutions:**
```bash
# Test FFmpeg
ffmpeg -version

# Reinstall in Docker
docker-compose -f docker/docker-compose.yml build --no-cache

# Check video file
ffprobe video.mp4
```

#### 4. WebSocket Connection Fails

**Symptom:** No progress updates in UI

**Solutions:**
```bash
# Check WebSocket endpoint
wscat -c ws://localhost:8012/v1/ws/test-id

# Check CORS settings
# app/main.py has CORS configured for localhost

# Check firewall
sudo ufw allow 8012
```

#### 5. Labeled Video Not Generated

**Symptom:** No labeled video in results

**Solutions:**
```bash
# Check temp directory permissions
ls -la $TEMP_DIR

# Check disk space
df -h $TEMP_DIR

# Check FFmpeg installation
ffmpeg -codecs | grep h264
```

#### 6. Slow Processing

**Symptom:** Videos take too long to process

**Solutions:**
```bash
# Reduce sampling rate
export DEFAULT_SAMPLING_FPS=0.5

# Use smaller models
export WHISPER_MODEL_ID=openai/whisper-tiny
export VIOLENCE_MODEL_ID=facebook/timesformer-base-finetuned-k400

# Enable GPU (if available)
# See GPU Acceleration section

# Reduce OCR frequency
export OCR_INTERVAL_SEC=5.0
```

### Debug Mode

Enable detailed logging:

```bash
# Set log level
export LOG_LEVEL=DEBUG

# Run with debug output
uvicorn app.main:app --reload --log-level debug
```

### Testing Installation

Run the test suite to verify everything is working:

```bash
# Install test dependencies
pip install -r tests/requirements-test.txt

# Run all tests
pytest tests/ -v

# Run specific tests
pytest tests/test_api_contract.py -v
pytest tests/test_policy_fusion.py -v
pytest tests/test_graph_smoke.py -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

### Getting Help

If you encounter issues:

1. Check logs: `docker-compose logs safevid`
2. Verify requirements: Review [System Requirements](#system-requirements)
3. Test health endpoint: `curl http://localhost:8012/v1/health`
4. Check GitHub issues: Search for similar problems
5. Open new issue: Include logs and system info

### System Information

Collect system info for bug reports:

```bash
# Docker info
docker version
docker-compose version

# System info
uname -a
python --version
ffmpeg -version

# Disk space
df -h

# Memory
free -h

# GPU (if applicable)
nvidia-smi
```

---

## Next Steps

- Read the [API Documentation](API.md)
- Explore the [Architecture Guide](ARCHITECTURE.md)
- Review [Usage Examples](../examples/)
- Check the [Main README](../README.md)

---

For production deployments or enterprise support, please contact the maintainers.
