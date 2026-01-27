#!/bin/bash
#
# SafeVid Evaluation API - cURL Examples
#
# This script demonstrates how to use the production-ready /v1/evaluate endpoint
# using simple cURL commands.
#

API_URL="http://localhost:8012/v1/evaluate"

echo "======================================"
echo "SafeVid Evaluation API - cURL Examples"
echo "======================================"
echo ""

# Example 1: Evaluate a local video file
echo "📹 Example 1: Evaluate a local video file"
echo "-----------------------------------"
echo "curl -X POST $API_URL \\"
echo "     -F 'video=@/path/to/video.mp4'"
echo ""
echo "Try it:"
echo "curl -X POST $API_URL -F 'video=@video.mp4' | jq '.verdict, .scores'"
echo ""

# Example 2: Evaluate a video from URL
echo "🌐 Example 2: Evaluate a video from URL"
echo "-----------------------------------"
echo "curl -X POST $API_URL \\"
echo "     -F 'url=https://example.com/video.mp4'"
echo ""

# Example 3: Evaluate with custom policy (strict)
echo "📋 Example 3: Evaluate with custom strict policy"
echo "-----------------------------------"
cat << 'EOF'
curl -X POST http://localhost:8012/v1/evaluate \
     -F 'video=@video.mp4' \
     -F 'policy={"thresholds":{"unsafe":{"violence":0.60,"sexual":0.45,"hate":0.45,"drugs":0.55},"caution":{"violence":0.25,"profanity":0.25,"drugs":0.25,"sexual":0.15,"hate":0.15}}}'
EOF
echo ""

# Example 4: Get only verdict and scores
echo "✅ Example 4: Extract only verdict and scores (using jq)"
echo "-----------------------------------"
echo "curl -s -X POST $API_URL \\"
echo "     -F 'video=@video.mp4' | jq '{verdict, confidence, scores}'"
echo ""

# Example 5: Get evidence summary
echo "🔍 Example 5: Extract evidence summary (using jq)"
echo "-----------------------------------"
echo "curl -s -X POST $API_URL \\"
echo "     -F 'video=@video.mp4' | jq '.evidence | {video_metadata, violence_segments: .violence_segments | length, audio_chunks: .audio_transcript | length}'"
echo ""

# Example 6: Save full result to file
echo "💾 Example 6: Save full result to JSON file"
echo "-----------------------------------"
echo "curl -s -X POST $API_URL \\"
echo "     -F 'video=@video.mp4' > result.json"
echo ""

echo "======================================"
echo "For detailed response structure, see:"
echo "http://localhost:8012/docs#/default/evaluate_video_evaluate_post"
echo "======================================"
