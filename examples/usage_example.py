"""
Example usage of SafeVid API.
"""
import requests
import json
from pathlib import Path


# API endpoint
API_URL = "http://localhost:8000/v1"


def evaluate_video(video_path: str, policy_override: dict = None):
    """
    Evaluate a video for child safety.
    
    Args:
        video_path: Path to video file
        policy_override: Optional policy configuration overrides
    
    Returns:
        dict: Evaluation results
    """
    url = f"{API_URL}/evaluate"
    
    # Prepare request
    files = {"file": open(video_path, "rb")}
    data = {}
    
    if policy_override:
        data["policy"] = json.dumps(policy_override)
    
    # Send request
    response = requests.post(url, files=files, data=data)
    response.raise_for_status()
    
    return response.json()


def check_health():
    """Check service health."""
    response = requests.get(f"{API_URL}/health")
    return response.json()


def list_models():
    """List configured models."""
    response = requests.get(f"{API_URL}/models")
    return response.json()


# Example 1: Basic evaluation
def example_basic():
    print("=" * 60)
    print("Example 1: Basic Video Evaluation")
    print("=" * 60)
    
    video_path = "test_video.mp4"
    
    if not Path(video_path).exists():
        print(f"Video not found: {video_path}")
        return
    
    result = evaluate_video(video_path)
    
    print(f"\nVerdict: {result['verdict']}")
    print(f"\nCriteria Scores:")
    for criterion, info in result['criteria'].items():
        print(f"  {criterion}: {info['score']:.2f} ({info['status']})")
    
    print(f"\nViolations: {len(result['violations'])}")
    for violation in result['violations']:
        print(f"  - {violation['criterion']} ({violation['severity']})")
    
    print(f"\nReport:\n{result['report']}")


# Example 2: With policy override
def example_with_policy():
    print("=" * 60)
    print("Example 2: Evaluation with Policy Override")
    print("=" * 60)
    
    video_path = "test_video.mp4"
    
    if not Path(video_path).exists():
        print(f"Video not found: {video_path}")
        return
    
    # Custom policy: stricter violence threshold, faster processing
    policy = {
        "thresholds": {
            "unsafe": {
                "violence": 0.5,  # Lower threshold (stricter)
            }
        },
        "sampling_fps": 0.5,  # Process fewer frames
        "segment_duration": 5.0  # Longer segments
    }
    
    result = evaluate_video(video_path, policy)
    
    print(f"\nVerdict: {result['verdict']}")
    print(f"Violence score: {result['criteria']['violence']['score']:.2f}")


# Example 3: Health check
def example_health():
    print("=" * 60)
    print("Example 3: Health Check")
    print("=" * 60)
    
    health = check_health()
    print(json.dumps(health, indent=2))


# Example 4: List models
def example_models():
    print("=" * 60)
    print("Example 4: List Models")
    print("=" * 60)
    
    models = list_models()
    
    print(f"\nConfigured Models: {len(models['models'])}")
    for model in models['models']:
        print(f"\n  {model['model_type'].upper()}")
        print(f"    ID: {model['model_id']}")
        print(f"    Status: {model['status']}")
        print(f"    Cached: {model['cached']}")


# Example 5: Batch processing
def example_batch():
    print("=" * 60)
    print("Example 5: Batch Processing")
    print("=" * 60)
    
    video_dir = Path("./videos")
    
    if not video_dir.exists():
        print(f"Video directory not found: {video_dir}")
        return
    
    videos = list(video_dir.glob("*.mp4"))
    
    results = []
    
    for video_path in videos:
        print(f"\nProcessing: {video_path.name}")
        
        try:
            result = evaluate_video(str(video_path))
            results.append({
                "filename": video_path.name,
                "verdict": result["verdict"],
                "violence_score": result["criteria"]["violence"]["score"],
                "profanity_score": result["criteria"]["profanity"]["score"]
            })
            
            print(f"  Verdict: {result['verdict']}")
        
        except Exception as e:
            print(f"  Error: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print("Batch Summary")
    print("=" * 60)
    
    safe_count = sum(1 for r in results if r["verdict"] == "SAFE")
    unsafe_count = sum(1 for r in results if r["verdict"] == "UNSAFE")
    caution_count = sum(1 for r in results if r["verdict"] == "CAUTION")
    
    print(f"Total: {len(results)}")
    print(f"SAFE: {safe_count}")
    print(f"CAUTION: {caution_count}")
    print(f"UNSAFE: {unsafe_count}")


if __name__ == "__main__":
    # Run examples
    try:
        example_health()
        print("\n")
        
        example_models()
        print("\n")
        
        # Uncomment to run evaluation examples
        # example_basic()
        # example_with_policy()
        # example_batch()
        
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to SafeVid service")
        print("Make sure the service is running: docker compose up")
