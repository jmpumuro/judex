# Judex Setup Guide

Complete setup and deployment guide for the Judex video evaluation framework.

## Table of Contents

- [System Requirements](#system-requirements)
- [Quick Start with Docker](#quick-start-with-docker)
- [Local Development Setup](#local-development-setup)
- [Environment Configuration](#environment-configuration)
- [Production Deployment](#production-deployment)
- [Troubleshooting](#troubleshooting)

---

## System Requirements

### Minimum Requirements

| Component | Requirement |
|-----------|-------------|
| RAM | 8GB |
| CPU | 4 cores |
| Storage | 20GB |
| Docker | 20.10+ |
| Docker Compose | 2.0+ |
| PostgreSQL | 14+ |

### Recommended (Development)

| Component | Requirement |
|-----------|-------------|
| RAM | 16GB |
| CPU | 8 cores |
| GPU | NVIDIA (optional, 8GB+ VRAM) |
| Storage | 50GB SSD |

### Production

| Component | Requirement |
|-----------|-------------|
| RAM | 32GB+ |
| CPU | 16+ cores |
| GPU | NVIDIA (16GB+ VRAM) |
| Storage | 100GB+ SSD |

---

## Quick Start with Docker

The fastest way to get Judex running is with Docker Compose.

### 1. Prerequisites

```bash
# macOS
brew install postgresql docker

# Start PostgreSQL
brew services start postgresql

# Ubuntu/Debian
sudo apt update
sudo apt install postgresql docker.io docker-compose-plugin
sudo systemctl start postgresql
```

### 2. Create Database

```bash
# Create the judex database
createdb judex

# Verify
psql -d judex -c "\conninfo"
```

### 3. Clone and Start

```bash
# Clone repository
git clone <repository-url>
cd safeVid

# Start services (builds on first run)
docker-compose -f docker/docker-compose.yml up -d

# Watch logs
docker-compose -f docker/docker-compose.yml logs -f judex
```

### 4. Access Services

| Service | URL |
|---------|-----|
| React Frontend | http://localhost:5173 |
| API | http://localhost:8012 |
| API Docs (Swagger) | http://localhost:8012/docs |
| MinIO Console | http://localhost:9001 |

### 5. Verify

```bash
# Health check
curl http://localhost:8012/v1/health

# Expected response
{"status":"healthy","version":"2.0.0","models_loaded":true}
```

---

## Local Development Setup

### Backend Setup

```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL=postgresql://localhost:5432/judex
export MINIO_ENDPOINT=localhost:9000
export MINIO_ACCESS_KEY=judex
export MINIO_SECRET_KEY=judex123
export HF_HOME=./models/hf
export TEMP_DIR=./tmp/judex

# Create directories
mkdir -p ./models/hf ./tmp/judex

# Run server
uvicorn app.main:app --reload --port 8012
```

### Frontend Setup

```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev

# Frontend available at http://localhost:5173
```

### MinIO Setup (Local)

```bash
# Using Docker
docker run -d \
  --name judex-minio \
  -p 9000:9000 \
  -p 9001:9001 \
  -e MINIO_ROOT_USER=judex \
  -e MINIO_ROOT_PASSWORD=judex123 \
  minio/minio server /data --console-address ":9001"

# Or install locally (macOS)
brew install minio
minio server ./minio-data --console-address ":9001"
```

---

## Environment Configuration

### Required Variables

```bash
# Database
DATABASE_URL=postgresql://docker:docker@localhost:5432/judex

# MinIO Object Storage
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=judex
MINIO_SECRET_KEY=judex123
MINIO_BUCKET=judex
MINIO_SECURE=false
```

### Optional Variables

```bash
# Model configuration
YOLO26_MODEL_ID=openvision/yolo26-s
VIOLENCE_MODEL_ID=microsoft/xclip-base-patch32-16-frames
WHISPER_MODEL_ID=openai/whisper-tiny
PROFANITY_MODEL_ID=tarekziade/pardonmyai
NLI_MODEL_ID=facebook/bart-large-mnli

# LLM for reports
LLM_PROVIDER=template  # "template", "qwen", or "openai"
OPENAI_API_KEY=sk-...  # Required if LLM_PROVIDER=openai

# Processing settings
DEFAULT_SAMPLING_FPS=1.0
SEGMENT_DURATION_SEC=3.0
VIOLENCE_FRAMES_PER_SEGMENT=16

# Paths
HF_HOME=/models/hf
TRANSFORMERS_CACHE=/models/hf/transformers
TEMP_DIR=/tmp/judex
DATA_DIR=/data/judex
```

### env.example

Create a `.env` file from the example:

```bash
cp env.example .env
# Edit .env with your values
```

---

## Production Deployment

### Docker Compose (Production)

```yaml
# docker-compose.prod.yml
services:
  judex:
    build:
      context: .
      dockerfile: docker/Dockerfile
    image: judex:latest
    container_name: judex
    ports:
      - "8012:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db-host:5432/judex
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY}
      - MINIO_SECRET_KEY=${MINIO_SECRET_KEY}
      - LLM_PROVIDER=openai
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - model_cache:/models
    deploy:
      resources:
        limits:
          cpus: '8'
          memory: 16G
    restart: always

volumes:
  model_cache:
```

### Kubernetes

```yaml
# judex-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: judex
spec:
  replicas: 2
  selector:
    matchLabels:
      app: judex
  template:
    metadata:
      labels:
        app: judex
    spec:
      containers:
      - name: judex
        image: judex:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: judex-secrets
              key: database-url
        resources:
          limits:
            cpu: "4"
            memory: "12Gi"
          requests:
            cpu: "2"
            memory: "8Gi"
        volumeMounts:
        - name: models
          mountPath: /models
      volumes:
      - name: models
        persistentVolumeClaim:
          claimName: judex-models-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: judex
spec:
  selector:
    app: judex
  ports:
  - port: 8012
    targetPort: 8000
  type: LoadBalancer
```

### Nginx Reverse Proxy

```nginx
# /etc/nginx/sites-available/judex
upstream judex_backend {
    server 127.0.0.1:8012;
}

server {
    listen 80;
    server_name judex.example.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name judex.example.com;

    ssl_certificate /etc/letsencrypt/live/judex.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/judex.example.com/privkey.pem;

    # API
    location /v1/ {
        proxy_pass http://judex_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # SSE support
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding off;
    }

    # Frontend (if serving static files)
    location / {
        root /var/www/judex/dist;
        try_files $uri $uri/ /index.html;
    }

    # Upload size limit
    client_max_body_size 500M;
}
```

---

## Troubleshooting

### Common Issues

#### Container Won't Start

```bash
# Check logs
docker-compose -f docker/docker-compose.yml logs judex

# Common causes:
# 1. Database not accessible
# 2. MinIO not running
# 3. Insufficient memory
```

#### Database Connection Failed

```bash
# Verify PostgreSQL is running
pg_isready -h localhost -p 5432

# Check connection
psql -d judex -c "SELECT 1;"

# Create database if missing
createdb judex
```

#### MinIO Connection Failed

```bash
# Check MinIO is running
curl http://localhost:9000/minio/health/live

# Verify credentials
mc alias set local http://localhost:9000 judex judex123
mc ls local/
```

#### Models Not Loading

```bash
# Check model cache
ls -la ~/.cache/judex/models/

# Clear cache and redownload
rm -rf ~/.cache/judex/models/
docker-compose -f docker/docker-compose.yml restart judex
```

#### Out of Memory

```bash
# Increase Docker memory limit
# Docker Desktop: Preferences > Resources > Memory

# Or use smaller models
export WHISPER_MODEL_ID=openai/whisper-tiny
export LLM_PROVIDER=template  # Disable Qwen
```

### Debug Commands

```bash
# Container shell
docker exec -it judex bash

# Python shell
docker exec -it judex python

# Check processes
docker exec judex ps aux

# View resource usage
docker stats judex
```

### Logs

```bash
# All logs
docker-compose -f docker/docker-compose.yml logs

# Follow judex
docker-compose -f docker/docker-compose.yml logs -f judex

# Export to file
docker-compose -f docker/docker-compose.yml logs judex > judex.log
```

---

## Migration from SafeVid

If upgrading from an older SafeVid installation:

### 1. Update Database

```bash
# Create new database
createdb judex

# If migrating data from safevid
pg_dump safevid | psql judex
```

### 2. Update MinIO

```bash
# Update credentials (MinIO console or mc)
mc admin user add local judex judex123

# Create new bucket
mc mb local/judex
```

### 3. Update Configuration

Replace all occurrences of `safevid` with `judex` in:
- Environment variables
- Docker compose files
- Application configuration

### 4. Rebuild

```bash
docker-compose -f docker/docker-compose.yml down -v
docker-compose -f docker/docker-compose.yml up -d --build
```

---

**For API documentation, see [API.md](API.md). For architecture details, see [ARCHITECTURE.md](ARCHITECTURE.md).**
