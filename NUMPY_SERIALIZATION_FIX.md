# Numpy Serialization Fix

## Problem

When processing videos through the pipeline, LangGraph checkpointing would fail with:

```python
TypeError: Type is not msgpack serializable: numpy.float64
```

This occurred because detection and analysis stages (YOLO, violence detection, etc.) return numpy types (float64, int64, ndarray) which msgpack (LangGraph's default serializer) doesn't natively support.

## Root Cause

1. **Detection stages use numpy** - All CV/ML models (YOLO, VideoMAE, etc.) return numpy arrays and scalar types
2. **Pipeline state contains numpy values** - These values get stored directly in the LangGraph state
3. **Checkpoint serialization fails** - When LangGraph tries to checkpoint the state to PostgreSQL, msgpack can't serialize numpy types

### Example Problematic Data

```python
# From YOLO detection
detection = {
    "label": "weapon",
    "confidence": np.float64(0.92),  # ❌ Not msgpack serializable
    "bbox": {
        "x1": np.int64(100),          # ❌ Not msgpack serializable
        "y1": np.int64(200)
    }
}

# From violence detection
violence_scores = np.array([0.1, 0.8, 0.3])  # ❌ Not msgpack serializable
```

## Solution

Created a **custom serializer** that extends LangGraph's JsonPlusSerializer to automatically convert numpy types to Python native types before serialization.

### Implementation

#### 1. Custom Serializer (`app/pipeline/serializer.py`)

```python
class NumpyAwareSerializer(JsonPlusSerializer):
    """Converts numpy types to Python native types before serialization."""

    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        # Convert numpy types first
        converted_obj = _convert_numpy_types(obj)
        return super().dumps_typed(converted_obj)
```

**Conversions Handled:**
- `numpy.float64` / `numpy.float32` → `float`
- `numpy.int64` / `numpy.int32` → `int`
- `numpy.bool_` → `bool`
- `numpy.ndarray` → `list`
- Recursive conversion for nested dicts/lists

#### 2. Updated Checkpointer (`app/pipeline/checkpointer.py`)

Modified all PostgresSaver instances to use the custom serializer:

```python
from app.pipeline.serializer import get_numpy_safe_serializer

# Sync checkpointer
_sync_checkpointer = PostgresSaver(conn, serde=get_numpy_safe_serializer())

# Async checkpointer
_async_checkpointer = AsyncPostgresSaver(pool, serde=get_numpy_safe_serializer())
```

## Testing

Created comprehensive tests (`tests/test_numpy_serializer.py`) covering:

✅ Individual numpy type conversions (float64, int64, bool_, ndarray)
✅ Nested dictionaries with numpy values
✅ Lists containing numpy values
✅ Realistic detection results with mixed types
✅ Complete serialization/deserialization cycle
✅ Pipeline state with numpy arrays

### Run Tests

```bash
pytest tests/test_numpy_serializer.py -v
```

## Benefits

### 1. **Zero Breaking Changes**
- Completely transparent to pipeline code
- No changes needed in detection stages
- Models continue returning numpy types normally

### 2. **Automatic Conversion**
- Conversion happens at serialization boundary
- No manual `.item()` or `.tolist()` calls needed
- Works for all numpy types automatically

### 3. **Performance**
- Minimal overhead (conversion only at checkpoint)
- Numpy used during computation (fast)
- Python types only for storage (compatible)

### 4. **Maintainability**
- Single location for numpy handling
- Easy to extend for new types
- Well-tested and documented

## Files Changed

**Created:**
- ✅ `app/pipeline/serializer.py` - Custom numpy-aware serializer
- ✅ `tests/test_numpy_serializer.py` - Comprehensive test suite

**Modified:**
- ✅ `app/pipeline/checkpointer.py` - Use custom serializer (4 locations)

## Before & After

### Before (Error)

```python
# Pipeline executes
state = {
    "detections": [{"confidence": np.float64(0.92)}]  # numpy type
}

# Checkpoint attempted
checkpointer.put(config, state)
# ❌ TypeError: Type is not msgpack serializable: numpy.float64
```

### After (Fixed)

```python
# Pipeline executes
state = {
    "detections": [{"confidence": np.float64(0.92)}]  # numpy type
}

# Checkpoint attempted with custom serializer
checkpointer.put(config, state)
# ✅ Automatically converts np.float64(0.92) -> 0.92 (Python float)
# ✅ Successfully serialized and stored
```

## Verification

To verify the fix is working:

```bash
# 1. Process a video
curl -X POST http://localhost:8012/v1/evaluate \
  -F "files=@test_video.mp4" \
  -F "async=true"

# 2. Check logs - should see:
# "✓ Checkpoint saved" instead of "TypeError: Type is not msgpack serializable"

# 3. Verify checkpoint exists in database
psql -h localhost -U docker -d judex -c "SELECT COUNT(*) FROM checkpoints;"
```

## Alternative Approaches Considered

### ❌ Option 1: Convert in Detection Stages
```python
# In each detection stage
return {
    "confidence": float(np.float64(0.92))  # Manual conversion
}
```
**Rejected:** Requires changes in 10+ stages, error-prone, easy to forget

### ❌ Option 2: State Sanitizer Hook
```python
# Before checkpoint
state = sanitize_numpy(state)
checkpointer.put(config, state)
```
**Rejected:** Requires modifying LangGraph internals, not maintainable

### ✅ Option 3: Custom Serializer (Chosen)
- Clean separation of concerns
- Single location for conversion logic
- Transparent to pipeline code
- Industry-standard extension point

## Future Considerations

### Additional Type Support

If other non-serializable types appear, extend `_convert_numpy_types`:

```python
def _convert_numpy_types(obj: Any) -> Any:
    # ... existing numpy handlers

    # Add new type handlers
    elif isinstance(obj, torch.Tensor):
        return obj.cpu().numpy().tolist()
    elif isinstance(obj, pd.DataFrame):
        return obj.to_dict('records')
```

### Performance Optimization

For very large arrays, consider:
- Storing arrays as separate artifacts (not in state)
- Compressing arrays before storage
- Sampling/downsampling large arrays

Currently not needed as pipeline state is reasonably sized (<10MB).

## Related Documentation

- [LangGraph Checkpointing](https://langchain-ai.github.io/langgraph/reference/checkpoints/)
- [msgpack Python Types](https://github.com/msgpack/msgpack-python#supported-types)
- [Numpy Data Types](https://numpy.org/doc/stable/user/basics.types.html)

## Summary

**Problem:** Pipeline checkpointing failed due to numpy types
**Solution:** Custom serializer that converts numpy → Python types
**Impact:** Zero breaking changes, transparent fix, fully tested
**Status:** ✅ Deployed and working

Pipeline can now checkpoint successfully with numpy values from all detection stages! 🎉
