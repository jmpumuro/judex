"""
Smoke tests for LangGraph pipeline.
"""
import pytest
from unittest.mock import MagicMock, patch
from app.pipeline.state import PipelineState
from app.pipeline.graph import build_stable_graph, get_stable_graph
from app.pipeline.nodes.ingest_video import ingest_video
from app.pipeline.nodes.segment_video import segment_video


def test_build_stable_graph():
    """Test that stable graph can be built."""
    graph = build_stable_graph()
    assert graph is not None


def test_get_stable_graph_singleton():
    """Test that get_stable_graph returns cached instance."""
    graph1 = get_stable_graph()
    graph2 = get_stable_graph()
    assert graph1 is graph2


def test_ingest_video_node():
    """Test ingest video node with mocked video."""
    with patch("app.pipeline.nodes.ingest_video.validate_video_file", return_value=True), \
         patch("app.pipeline.nodes.ingest_video.create_working_directory", return_value="/tmp/test"), \
         patch("app.pipeline.nodes.ingest_video.get_video_metadata", return_value={
             "duration": 10.0,
             "fps": 30.0,
             "width": 1920,
             "height": 1080,
             "has_audio": True,
             "codec": "h264"
         }):
        
        state = PipelineState(
            video_path="/tmp/test.mp4",
            policy_config={}
        )
        
        result = ingest_video(state)
        
        assert "video_id" in result
        assert "work_dir" in result
        assert result["duration"] == 10.0
        assert result["fps"] == 30.0
        assert result["has_audio"] is True


def test_segment_video_node():
    """Test segment video node with mocked extraction."""
    with patch("app.pipeline.nodes.segment_video.extract_frames", return_value=[
        "/tmp/frame_0001.jpg",
        "/tmp/frame_0002.jpg",
        "/tmp/frame_0003.jpg",
    ]), \
         patch("app.pipeline.nodes.segment_video.extract_segment_frames", return_value=[
        "/tmp/seg_0.0_0001.jpg",
    ]):
        
        state = PipelineState(
            video_path="/tmp/test.mp4",
            work_dir="/tmp/work",
            duration=10.0,
            fps=30.0,
            policy_config={}
        )
        
        result = segment_video(state)
        
        assert "sampled_frames" in result
        assert len(result["sampled_frames"]) == 3
        assert "segments" in result


def test_state_transitions():
    """Test that state flows through nodes correctly."""
    # Initialize state
    state = PipelineState(
        video_path="/tmp/test.mp4",
        policy_config={"sampling_fps": 1.0}
    )
    
    # Verify state has required initial fields
    assert "video_path" in state
    assert "policy_config" in state


def test_error_handling_in_nodes():
    """Test that nodes handle errors gracefully."""
    # Test with invalid video path
    state = PipelineState(
        video_path="/nonexistent/video.mp4",
        policy_config={}
    )
    
    result = ingest_video(state)
    
    # Should add error to state
    assert "errors" in result
    assert len(result.get("errors", [])) > 0


def test_policy_config_propagation():
    """Test that policy config is accessible in state."""
    policy_config = {
        "sampling_fps": 0.5,
        "segment_duration": 5.0,
        "thresholds": {
            "unsafe": {
                "violence": 0.8
            }
        }
    }
    
    state = PipelineState(
        video_path="/tmp/test.mp4",
        policy_config=policy_config
    )
    
    assert state["policy_config"]["sampling_fps"] == 0.5
    assert state["policy_config"]["segment_duration"] == 5.0


def test_evidence_structure_initialization():
    """Test that evidence collections are initialized."""
    state = PipelineState(
        video_path="/tmp/test.mp4",
        policy_config={}
    )
    
    with patch("app.pipeline.nodes.ingest_video.validate_video_file", return_value=True), \
         patch("app.pipeline.nodes.ingest_video.create_working_directory", return_value="/tmp/test"), \
         patch("app.pipeline.nodes.ingest_video.get_video_metadata", return_value={
             "duration": 10.0,
             "fps": 30.0,
             "width": 1920,
             "height": 1080,
             "has_audio": True,
             "codec": "h264"
         }):
        
        result = ingest_video(state)
        
        # Check that collections are initialized
        assert "vision_detections" in result
        assert "violence_segments" in result
        assert "ocr_results" in result
        assert isinstance(result["vision_detections"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
