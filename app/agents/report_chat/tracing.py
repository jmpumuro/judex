"""
Tracing module for ReportChat agent.

Industry Standard: LangSmith-style tracing for observability.
- Trace tool calls with latency and outcomes
- Trace graph steps
- Store lightweight trace summaries for debugging
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from contextlib import contextmanager
import time
import uuid
import functools

from app.core.logging import get_logger

logger = get_logger("agents.report_chat.tracing")


class TraceStep:
    """A single step in an agent trace."""
    
    def __init__(
        self,
        name: str,
        step_type: str = "node",  # node, tool, llm
        parent_id: Optional[str] = None,
    ):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.step_type = step_type
        self.parent_id = parent_id
        self.start_time = datetime.utcnow()
        self.end_time: Optional[datetime] = None
        self.latency_ms: Optional[int] = None
        self.status: str = "running"
        self.inputs: Dict[str, Any] = {}
        self.outputs: Dict[str, Any] = {}
        self.error: Optional[str] = None
        self.metadata: Dict[str, Any] = {}
    
    def complete(self, status: str = "success", outputs: Dict[str, Any] = None, error: str = None):
        """Mark step as complete."""
        self.end_time = datetime.utcnow()
        self.latency_ms = int((self.end_time - self.start_time).total_seconds() * 1000)
        self.status = status
        if outputs:
            self.outputs = outputs
        if error:
            self.error = error
            self.status = "error"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.step_type,
            "parent_id": self.parent_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "latency_ms": self.latency_ms,
            "status": self.status,
            "inputs": self._safe_serialize(self.inputs),
            "outputs": self._safe_serialize(self.outputs),
            "error": self.error,
            "metadata": self.metadata,
        }
    
    def _safe_serialize(self, data: Any, max_length: int = 1000) -> Any:
        """Safely serialize data for logging, truncating large values."""
        if isinstance(data, dict):
            return {k: self._safe_serialize(v, max_length) for k, v in data.items()}
        elif isinstance(data, list):
            if len(data) > 10:
                return self._safe_serialize(data[:10], max_length) + [f"... ({len(data) - 10} more)"]
            return [self._safe_serialize(item, max_length) for item in data]
        elif isinstance(data, str) and len(data) > max_length:
            return data[:max_length] + "..."
        elif isinstance(data, (int, float, bool, type(None))):
            return data
        else:
            s = str(data)
            return s[:max_length] + "..." if len(s) > max_length else s


class AgentTrace:
    """
    Full trace of an agent execution.
    
    Contains all steps (nodes, tool calls, LLM invocations).
    """
    
    def __init__(self, trace_id: Optional[str] = None):
        self.id = trace_id or str(uuid.uuid4())[:12]
        self.start_time = datetime.utcnow()
        self.end_time: Optional[datetime] = None
        self.steps: List[TraceStep] = []
        self.current_step: Optional[TraceStep] = None
        self.metadata: Dict[str, Any] = {}
        self.status: str = "running"
    
    def start_step(
        self, 
        name: str, 
        step_type: str = "node",
        inputs: Dict[str, Any] = None,
    ) -> TraceStep:
        """Start a new step in the trace."""
        step = TraceStep(
            name=name, 
            step_type=step_type,
            parent_id=self.current_step.id if self.current_step else None
        )
        if inputs:
            step.inputs = inputs
        
        self.steps.append(step)
        self.current_step = step
        
        logger.debug(f"[trace:{self.id}] Started {step_type}: {name}")
        return step
    
    def end_step(
        self, 
        status: str = "success", 
        outputs: Dict[str, Any] = None,
        error: str = None
    ):
        """End the current step."""
        if self.current_step:
            self.current_step.complete(status, outputs, error)
            logger.debug(
                f"[trace:{self.id}] Completed {self.current_step.name} "
                f"in {self.current_step.latency_ms}ms ({status})"
            )
            self.current_step = None
    
    def complete(self, status: str = "success"):
        """Complete the entire trace."""
        self.end_time = datetime.utcnow()
        self.status = status
        
        total_ms = int((self.end_time - self.start_time).total_seconds() * 1000)
        logger.info(
            f"[trace:{self.id}] Completed in {total_ms}ms with {len(self.steps)} steps ({status})"
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": int((self.end_time - self.start_time).total_seconds() * 1000) if self.end_time else None,
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "metadata": self.metadata,
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a lightweight summary for storage."""
        tool_calls = [s for s in self.steps if s.step_type == "tool"]
        return {
            "trace_id": self.id,
            "duration_ms": int((self.end_time - self.start_time).total_seconds() * 1000) if self.end_time else None,
            "status": self.status,
            "step_count": len(self.steps),
            "tool_calls": [
                {
                    "name": t.name, 
                    "latency_ms": t.latency_ms, 
                    "status": t.status
                } 
                for t in tool_calls
            ],
        }


# Context manager for tracing
@contextmanager
def trace_context(name: str = "agent_run"):
    """Context manager for tracing an agent run."""
    trace = AgentTrace()
    trace.metadata["name"] = name
    
    try:
        yield trace
        trace.complete("success")
    except Exception as e:
        trace.complete("error")
        raise
    finally:
        # Log trace summary
        logger.info(f"Trace summary: {trace.get_summary()}")


def trace_tool(func):
    """
    Decorator to trace tool calls.
    
    Usage:
        @trace_tool
        def my_tool(evaluation_id: str):
            ...
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        tool_name = func.__name__
        
        try:
            result = func(*args, **kwargs)
            latency_ms = int((time.time() - start_time) * 1000)
            logger.debug(f"[tool:{tool_name}] Completed in {latency_ms}ms")
            return result
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(f"[tool:{tool_name}] Failed in {latency_ms}ms: {e}")
            raise
    
    return wrapper


# Global trace for current request (optional, for advanced use)
_current_trace: Optional[AgentTrace] = None

def get_current_trace() -> Optional[AgentTrace]:
    """Get the current active trace, if any."""
    return _current_trace

def set_current_trace(trace: Optional[AgentTrace]):
    """Set the current active trace."""
    global _current_trace
    _current_trace = trace
