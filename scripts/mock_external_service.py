#!/usr/bin/env python3
"""
Mock External Service for testing Judex external stages.

This simple service simulates a customer API endpoint that:
- Receives video analysis data from Judex
- Performs a mock "custom policy check"
- Returns verdict and evidence

Run with: python scripts/mock_external_service.py
Runs on: http://localhost:8099
"""
import time
import random
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

app = FastAPI(
    title="Mock External Stage Service",
    description="Test endpoint for Judex external stages",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============= Request/Response Models =============

class AnalysisRequest(BaseModel):
    """Request from Judex external stage."""
    vision_data: Optional[List[Dict]] = None
    transcript: Optional[str] = None
    video_id: Optional[str] = None
    metadata: Optional[Dict] = None
    _context: Optional[Dict] = None


class PolicyViolation(BaseModel):
    """A detected policy violation."""
    policy_id: str
    policy_name: str
    severity: str  # low, medium, high, critical
    confidence: float
    description: str
    evidence: Optional[str] = None


class AnalysisResponse(BaseModel):
    """Response to Judex."""
    verdict: str  # PASS, FAIL, REVIEW
    confidence: float
    violations: List[PolicyViolation]
    custom_score: float
    processing_time_ms: int
    timestamp: str


# ============= Mock Analysis Logic =============

# Simulated "custom policies" that this external service checks
CUSTOM_POLICIES = [
    {
        "id": "brand_safety",
        "name": "Brand Safety Check",
        "keywords": ["competitor", "lawsuit", "scandal", "controversy"],
        "severity": "high"
    },
    {
        "id": "age_verification",
        "name": "Age-Restricted Content",
        "keywords": ["alcohol", "gambling", "tobacco", "vaping"],
        "severity": "medium"
    },
    {
        "id": "compliance_check",
        "name": "Regulatory Compliance",
        "keywords": ["investment advice", "medical claim", "guaranteed results"],
        "severity": "critical"
    },
]


def analyze_content(request: AnalysisRequest) -> AnalysisResponse:
    """
    Perform mock analysis on the video content.
    
    In a real service, this would:
    - Check against customer-specific policies
    - Run custom ML models
    - Query internal databases
    - etc.
    """
    start_time = time.time()
    violations = []
    
    # Combine all text content for analysis
    all_text = ""
    if request.transcript:
        all_text += request.transcript.lower() + " "
    
    # Check vision detections for concerning objects
    concerning_objects = {"knife", "gun", "weapon", "cigarette", "alcohol", "blood"}
    if request.vision_data:
        for detection in request.vision_data:
            label = (detection.get("label") or detection.get("class") or "").lower()
            if label in concerning_objects:
                violations.append(PolicyViolation(
                    policy_id="visual_content",
                    policy_name="Visual Content Policy",
                    severity="high",
                    confidence=detection.get("confidence", 0.8),
                    description=f"Detected concerning object: {label}",
                    evidence=f"Frame {detection.get('frame_idx', 'N/A')}"
                ))
    
    # Check text against custom policies
    for policy in CUSTOM_POLICIES:
        for keyword in policy["keywords"]:
            if keyword.lower() in all_text:
                violations.append(PolicyViolation(
                    policy_id=policy["id"],
                    policy_name=policy["name"],
                    severity=policy["severity"],
                    confidence=0.85 + random.random() * 0.1,
                    description=f"Keyword '{keyword}' detected",
                    evidence=f"Found in transcript"
                ))
                break  # One violation per policy
    
    # Always add some sample findings for demo purposes
    # (In production, remove this and rely on actual analysis)
    if not violations:
        # Add sample findings so UI has something to display
        violations.append(PolicyViolation(
            policy_id="content_review",
            policy_name="Content Review Required",
            severity="low",
            confidence=0.75,
            description="Video requires manual review per company policy",
            evidence="Automated pre-screening"
        ))
    
    # Add a random "brand mention" check (for demo purposes)
    if random.random() < 0.3:
        violations.append(PolicyViolation(
            policy_id="brand_mention",
            policy_name="Competitor Brand Mention",
            severity="medium",
            confidence=0.7,
            description="Possible competitor brand mentioned",
            evidence="Audio analysis"
        ))
    
    # Calculate overall verdict
    processing_time = int((time.time() - start_time) * 1000)
    
    # Simulate some processing time
    time.sleep(random.uniform(0.1, 0.3))
    
    if any(v.severity == "critical" for v in violations):
        verdict = "FAIL"
        confidence = 0.95
    elif any(v.severity == "high" for v in violations):
        verdict = "REVIEW"
        confidence = 0.8
    elif violations:
        verdict = "REVIEW"
        confidence = 0.7
    else:
        verdict = "PASS"
        confidence = 0.9
    
    # Calculate custom score (0-1, lower is better)
    severity_weights = {"low": 0.1, "medium": 0.3, "high": 0.5, "critical": 0.8}
    custom_score = min(1.0, sum(severity_weights.get(v.severity, 0.2) for v in violations))
    
    return AnalysisResponse(
        verdict=verdict,
        confidence=confidence,
        violations=violations,
        custom_score=custom_score,
        processing_time_ms=processing_time,
        timestamp=datetime.utcnow().isoformat()
    )


# ============= Endpoints =============

@app.get("/")
async def root():
    """Health check and info."""
    return {
        "service": "Mock External Stage Service",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "analyze": "POST /analyze - Main analysis endpoint",
            "health": "GET /health - Health check",
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze(
    request: AnalysisRequest,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    x_judex_stage: Optional[str] = Header(None)
):
    """
    Main analysis endpoint for Judex external stage.
    
    Accepts video analysis data and returns custom policy evaluation.
    
    Supports authentication via:
    - Bearer token (Authorization header)
    - API key (X-API-Key header)
    """
    # Log the request (for debugging)
    print(f"\n{'='*50}")
    print(f"Received analysis request from stage: {x_judex_stage or 'unknown'}")
    print(f"Video ID: {request.video_id or 'N/A'}")
    print(f"Vision detections: {len(request.vision_data or [])} items")
    print(f"Transcript length: {len(request.transcript or '')} chars")
    
    # Optional: Validate authentication
    # In a real service, you'd verify the token/API key
    if authorization:
        print(f"Auth: Bearer token provided")
    if x_api_key:
        print(f"Auth: API key provided")
    
    # Perform analysis
    response = analyze_content(request)
    
    print(f"Result: {response.verdict} ({response.confidence:.0%} confidence)")
    print(f"Violations: {len(response.violations)}")
    print(f"Processing time: {response.processing_time_ms}ms")
    print(f"{'='*50}\n")
    
    return response


@app.post("/webhook")
async def webhook(data: Dict[str, Any]):
    """
    Alternative webhook-style endpoint.
    
    Accepts any JSON and echoes it back with a mock result.
    Useful for testing different input formats.
    """
    return {
        "received": True,
        "input_keys": list(data.keys()),
        "mock_result": {
            "status": "processed",
            "score": random.uniform(0, 1)
        },
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  Mock External Stage Service")
    print("  Test endpoint for Judex external stages")
    print("="*60)
    print("\nEndpoints:")
    print("  POST /analyze  - Main analysis (matches Judex mapping)")
    print("  POST /webhook  - Generic webhook test")
    print("  GET  /health   - Health check")
    print("\nStarting server on http://localhost:8099 ...")
    print("="*60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8099, log_level="info")
