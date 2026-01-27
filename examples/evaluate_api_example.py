#!/usr/bin/env python3
"""
Example usage of the SafeVid /v1/evaluate API endpoint.

This is a production-ready API that takes a video (file or URL) and returns
a complete verdict with evidence, scores, and detailed analysis.
"""
import requests
import json
import sys
from pathlib import Path

# API Configuration
API_URL = "http://localhost:8012/v1/evaluate"

def evaluate_video_file(video_path: str, policy: dict = None):
    """
    Evaluate a video file.
    
    Args:
        video_path: Path to the video file
        policy: Optional policy configuration dict
    
    Returns:
        dict: Complete evaluation result
    """
    print(f"\n📹 Evaluating video: {video_path}")
    print("=" * 60)
    
    # Prepare the request
    files = {
        'video': open(video_path, 'rb')
    }
    
    data = {}
    if policy:
        data['policy'] = json.dumps(policy)
    
    # Make the request
    print("⏳ Sending request to API...")
    response = requests.post(API_URL, files=files, data=data)
    
    # Close the file
    files['video'].close()
    
    if response.status_code != 200:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return None
    
    result = response.json()
    print_results(result)
    return result


def evaluate_video_url(video_url: str, policy: dict = None):
    """
    Evaluate a video from URL.
    
    Args:
        video_url: URL to the video
        policy: Optional policy configuration dict
    
    Returns:
        dict: Complete evaluation result
    """
    print(f"\n🌐 Evaluating video from URL: {video_url}")
    print("=" * 60)
    
    # Prepare the request
    data = {
        'url': video_url
    }
    
    if policy:
        data['policy'] = json.dumps(policy)
    
    # Make the request
    print("⏳ Sending request to API...")
    response = requests.post(API_URL, data=data)
    
    if response.status_code != 200:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return None
    
    result = response.json()
    print_results(result)
    return result


def print_results(result: dict):
    """Print evaluation results in a readable format."""
    print("\n✅ Evaluation Complete!")
    print("=" * 60)
    
    # Verdict
    verdict = result.get('verdict', 'UNKNOWN')
    confidence = result.get('confidence', 0) * 100
    processing_time = result.get('processing_time_sec', 0)
    
    verdict_emoji = {
        'SAFE': '✅',
        'CAUTION': '⚠️',
        'UNSAFE': '❌',
        'NEEDS_REVIEW': '🔍'
    }.get(verdict, '❓')
    
    print(f"\n{verdict_emoji} VERDICT: {verdict}")
    print(f"   Confidence: {confidence:.1f}%")
    print(f"   Processing Time: {processing_time:.2f}s")
    
    # Scores
    scores = result.get('scores', {})
    print(f"\n📊 SAFETY SCORES:")
    print(f"   Violence:  {scores.get('violence', 0) * 100:.1f}%")
    print(f"   Sexual:    {scores.get('sexual', 0) * 100:.1f}%")
    print(f"   Hate:      {scores.get('hate', 0) * 100:.1f}%")
    print(f"   Drugs:     {scores.get('drugs', 0) * 100:.1f}%")
    print(f"   Profanity: {scores.get('profanity', 0) * 100:.1f}%")
    
    # Evidence Summary
    evidence = result.get('evidence', {})
    video_meta = evidence.get('video_metadata', {})
    
    print(f"\n📹 VIDEO INFO:")
    print(f"   Duration: {video_meta.get('duration', 0):.1f}s")
    print(f"   Resolution: {video_meta.get('resolution', 'N/A')}")
    print(f"   FPS: {video_meta.get('fps', 0):.1f}")
    print(f"   Audio: {'Yes' if video_meta.get('has_audio') else 'No'}")
    
    # Evidence counts
    obj_det = evidence.get('object_detections', {})
    violence_segs = evidence.get('violence_segments', [])
    audio_trans = evidence.get('audio_transcript', [])
    ocr_results = evidence.get('ocr_results', [])
    mod_flags = evidence.get('moderation_flags', [])
    
    print(f"\n🔍 EVIDENCE DETECTED:")
    print(f"   Object Detections: {obj_det.get('total_frames_analyzed', 0)} frames")
    print(f"   Violence Segments: {len(violence_segs)}")
    print(f"   Audio Transcripts: {len(audio_trans)} chunks")
    print(f"   OCR Results: {len(ocr_results)}")
    print(f"   Moderation Flags: {len(mod_flags)}")
    
    # Summary
    summary = result.get('summary', '')
    if summary:
        print(f"\n📝 SUMMARY:")
        print(f"   {summary[:200]}{'...' if len(summary) > 200 else ''}")
    
    print("\n" + "=" * 60)


def example_with_custom_policy():
    """Example with custom policy configuration."""
    custom_policy = {
        "thresholds": {
            "unsafe": {
                "violence": 0.60,  # Stricter than default (0.75)
                "sexual": 0.45,
                "hate": 0.45,
                "drugs": 0.55
            },
            "caution": {
                "violence": 0.25,
                "profanity": 0.25,
                "drugs": 0.25,
                "sexual": 0.15,
                "hate": 0.15
            }
        }
    }
    
    print("\n📋 Using STRICT policy configuration")
    return custom_policy


if __name__ == "__main__":
    print("SafeVid Evaluation API - Example Usage")
    print("=" * 60)
    
    if len(sys.argv) < 2:
        print("\nUsage:")
        print("  python evaluate_api_example.py <video_path>")
        print("  python evaluate_api_example.py <video_url>")
        print("\nExamples:")
        print("  python evaluate_api_example.py video.mp4")
        print("  python evaluate_api_example.py https://example.com/video.mp4")
        sys.exit(1)
    
    input_path = sys.argv[1]
    
    # Check if it's a URL or file
    if input_path.startswith(('http://', 'https://')):
        # Evaluate from URL
        result = evaluate_video_url(input_path)
    else:
        # Evaluate from file
        if not Path(input_path).exists():
            print(f"❌ Error: File not found: {input_path}")
            sys.exit(1)
        
        result = evaluate_video_file(input_path)
    
    # Example with custom policy
    # policy = example_with_custom_policy()
    # result = evaluate_video_file(input_path, policy=policy)
    
    # Save result to JSON file
    if result:
        output_file = Path(input_path).stem + "_result.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\n💾 Full results saved to: {output_file}")
