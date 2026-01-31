"""
Tests for numpy-aware serializer.

Ensures that numpy types from detection stages can be properly
serialized and checkpointed without errors.
"""
import pytest
import numpy as np
from app.pipeline.serializer import _convert_numpy_types, get_numpy_safe_serializer


class TestNumpyConversion:
    """Test numpy type conversion to Python native types."""

    def test_convert_float64(self):
        """numpy.float64 -> float"""
        result = _convert_numpy_types(np.float64(3.14))
        assert isinstance(result, float)
        assert result == 3.14

    def test_convert_float32(self):
        """numpy.float32 -> float"""
        result = _convert_numpy_types(np.float32(2.718))
        assert isinstance(result, float)
        assert abs(result - 2.718) < 0.001

    def test_convert_int64(self):
        """numpy.int64 -> int"""
        result = _convert_numpy_types(np.int64(42))
        assert isinstance(result, int)
        assert result == 42

    def test_convert_int32(self):
        """numpy.int32 -> int"""
        result = _convert_numpy_types(np.int32(123))
        assert isinstance(result, int)
        assert result == 123

    def test_convert_bool(self):
        """numpy.bool_ -> bool"""
        result = _convert_numpy_types(np.bool_(True))
        assert isinstance(result, bool)
        assert result is True

    def test_convert_ndarray(self):
        """numpy.ndarray -> list"""
        arr = np.array([1.0, 2.0, 3.0])
        result = _convert_numpy_types(arr)
        assert isinstance(result, list)
        assert result == [1.0, 2.0, 3.0]

    def test_convert_nested_dict(self):
        """Dict with nested numpy values"""
        data = {
            "score": np.float64(0.85),
            "count": np.int64(10),
            "enabled": np.bool_(True),
            "metadata": {
                "confidence": np.float32(0.9),
                "timestamps": np.array([1.0, 2.0, 3.0])
            }
        }
        result = _convert_numpy_types(data)

        assert isinstance(result["score"], float)
        assert isinstance(result["count"], int)
        assert isinstance(result["enabled"], bool)
        assert isinstance(result["metadata"]["confidence"], float)
        assert isinstance(result["metadata"]["timestamps"], list)

    def test_convert_list_with_numpy(self):
        """List containing numpy values"""
        data = [np.float64(1.0), np.int64(2), np.bool_(True)]
        result = _convert_numpy_types(data)

        assert isinstance(result, list)
        assert all(not isinstance(x, (np.generic, np.ndarray)) for x in result)

    def test_convert_detection_result(self):
        """Realistic detection result with numpy values"""
        detection = {
            "label": "weapon",
            "confidence": np.float64(0.92),
            "bbox": {
                "x1": np.int64(100),
                "y1": np.int64(200),
                "x2": np.int64(300),
                "y2": np.int64(400)
            },
            "timestamp": np.float32(5.5),
            "features": np.array([0.1, 0.2, 0.3, 0.4])
        }
        result = _convert_numpy_types(detection)

        # All numpy types should be converted
        assert isinstance(result["confidence"], float)
        assert isinstance(result["bbox"]["x1"], int)
        assert isinstance(result["timestamp"], float)
        assert isinstance(result["features"], list)

    def test_preserve_native_types(self):
        """Native Python types should pass through unchanged"""
        data = {
            "string": "hello",
            "int": 42,
            "float": 3.14,
            "bool": True,
            "list": [1, 2, 3],
            "dict": {"key": "value"}
        }
        result = _convert_numpy_types(data)
        assert result == data


class TestNumpyAwareSerializer:
    """Test the complete serializer with msgpack."""

    def test_serializer_basic(self):
        """Serializer should handle basic types"""
        serializer = get_numpy_safe_serializer()

        data = {"message": "hello", "count": 42}
        type_name, serialized = serializer.dumps_typed(data)

        assert type_name in ["json", "msgpack"]
        assert serialized  # Should produce bytes

    def test_serializer_with_numpy(self):
        """Serializer should handle numpy types without error"""
        serializer = get_numpy_safe_serializer()

        data = {
            "score": np.float64(0.85),
            "count": np.int64(100),
            "values": np.array([1.0, 2.0, 3.0])
        }

        # Should not raise TypeError
        type_name, serialized = serializer.dumps_typed(data)
        assert type_name in ["json", "msgpack"]
        assert serialized

    def test_serializer_detection_state(self):
        """Serializer should handle realistic pipeline state"""
        serializer = get_numpy_safe_serializer()

        state = {
            "video_id": "test123",
            "detections": [
                {
                    "label": "weapon",
                    "confidence": np.float64(0.92),
                    "bbox": {
                        "x1": np.int64(100),
                        "y1": np.int64(200)
                    }
                }
            ],
            "violence_scores": np.array([0.1, 0.2, 0.8, 0.3]),
            "metadata": {
                "fps": np.float32(30.0),
                "frame_count": np.int64(300)
            }
        }

        # Should serialize without error
        type_name, serialized = serializer.dumps_typed(state)
        assert type_name in ["json", "msgpack"]
        assert serialized

        # Should be able to deserialize
        deserialized = serializer.loads_typed((type_name, serialized))
        assert deserialized["video_id"] == "test123"
        assert len(deserialized["detections"]) == 1
        assert isinstance(deserialized["detections"][0]["confidence"], float)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
