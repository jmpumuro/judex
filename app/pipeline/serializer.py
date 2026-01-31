"""
Custom serializer for LangGraph checkpointing with numpy support.

Extends the default JsonPlusSerializer to handle numpy types that
commonly appear in video analysis pipelines (float64, int64, ndarray, etc.)
"""
from typing import Any
import numpy as np
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


def _convert_numpy_types(obj: Any) -> Any:
    """
    Recursively convert numpy types to native Python types.

    Handles:
    - numpy.float64 -> float
    - numpy.float32 -> float
    - numpy.int64 -> int
    - numpy.int32 -> int
    - numpy.ndarray -> list
    - numpy.bool_ -> bool
    """
    # Handle numpy scalar types
    if isinstance(obj, (np.float64, np.float32, np.float16)):
        return float(obj)
    elif isinstance(obj, (np.int64, np.int32, np.int16, np.int8)):
        return int(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.ndarray):
        # Convert array to list (recursively handle nested arrays)
        return [_convert_numpy_types(item) for item in obj.tolist()]

    # Handle dictionaries
    elif isinstance(obj, dict):
        return {key: _convert_numpy_types(value) for key, value in obj.items()}

    # Handle lists/tuples
    elif isinstance(obj, (list, tuple)):
        converted = [_convert_numpy_types(item) for item in obj]
        return tuple(converted) if isinstance(obj, tuple) else converted

    # Return as-is for other types
    return obj


class NumpyAwareSerializer(JsonPlusSerializer):
    """
    Custom serializer that converts numpy types to Python native types
    before serialization.

    This prevents msgpack serialization errors when checkpointing state
    that contains numpy values from detection/analysis stages.
    """

    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        """
        Serialize object, converting numpy types first.

        Returns:
            Tuple of (type_name, serialized_bytes)
        """
        # Convert numpy types to native Python types
        converted_obj = _convert_numpy_types(obj)

        # Use parent serializer
        return super().dumps_typed(converted_obj)


def get_numpy_safe_serializer() -> NumpyAwareSerializer:
    """
    Get a serializer that safely handles numpy types.

    Usage:
        from app.pipeline.serializer import get_numpy_safe_serializer

        checkpointer = PostgresSaver(conn, serde=get_numpy_safe_serializer())
    """
    return NumpyAwareSerializer()
