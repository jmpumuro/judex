"""
LangGraph-native callback system for pipeline progress reporting.

This module implements the industry-standard approach for handling
non-serializable callbacks in LangGraph pipelines by using the
config["callbacks"] mechanism.

Usage:
    1. Create a ProgressCallbackHandler with your broadcast function
    2. Pass it via config["callbacks"] to graph.ainvoke()
    3. In nodes, extract and call callbacks from config

This approach:
    - Keeps state fully serializable (checkpoint-safe)
    - Uses LangGraph's native callback propagation
    - Follows LangChain/LangGraph best practices
"""
import asyncio
from typing import Any, Callable, Dict, List, Optional, Union
from dataclasses import dataclass, field
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableConfig

from app.core.logging import get_logger

logger = get_logger("pipeline.callbacks")


@dataclass
class ProgressEvent:
    """Structured progress event."""
    stage: str
    message: str
    progress: int  # 0-100
    video_id: Optional[str] = None
    status: str = "running"  # running, completed, failed, skipped


class ProgressCallbackHandler(BaseCallbackHandler):
    """
    LangGraph-native callback handler for pipeline progress.
    
    This handler receives events from the pipeline and broadcasts
    them to connected clients (via SSE, WebSocket, etc.)
    
    Industry standard: Callbacks are passed via config, not state,
    keeping state serializable for checkpointing.
    """
    
    def __init__(
        self,
        video_id: str,
        broadcast_fn: Optional[Callable] = None,
    ):
        """
        Initialize the progress handler.
        
        Args:
            video_id: ID of the video being processed
            broadcast_fn: Async function to broadcast progress (e.g., SSE)
        """
        super().__init__()
        self.video_id = video_id
        self.broadcast_fn = broadcast_fn
        self._progress_history: List[ProgressEvent] = []
    
    @property
    def progress_history(self) -> List[ProgressEvent]:
        """Get the history of progress events."""
        return self._progress_history
    
    async def send_progress(
        self,
        stage: str,
        message: str,
        progress: int,
        status: str = "running",
    ) -> None:
        """
        Send a progress update.
        
        This is the main method nodes should call to report progress.
        """
        event = ProgressEvent(
            stage=stage,
            message=message,
            progress=progress,
            video_id=self.video_id,
            status=status,
        )
        self._progress_history.append(event)
        
        logger.debug(f"Progress: {stage} - {message} ({progress}%)")
        
        if self.broadcast_fn:
            try:
                result = self.broadcast_fn(stage, message, progress)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning(f"Failed to broadcast progress: {e}")
    
    def send_progress_sync(
        self,
        stage: str,
        message: str,
        progress: int,
        status: str = "running",
    ) -> None:
        """
        Synchronous version for non-async contexts.
        
        Creates an event loop if needed to run the async broadcast.
        """
        event = ProgressEvent(
            stage=stage,
            message=message,
            progress=progress,
            video_id=self.video_id,
            status=status,
        )
        self._progress_history.append(event)
        
        if self.broadcast_fn:
            try:
                result = self.broadcast_fn(stage, message, progress)
                if asyncio.iscoroutine(result):
                    # Try to run in existing loop or create new one
                    try:
                        loop = asyncio.get_running_loop()
                        # We're in an async context, create task
                        asyncio.ensure_future(result)
                    except RuntimeError:
                        # No running loop, run directly
                        asyncio.run(result)
            except Exception as e:
                logger.warning(f"Failed to broadcast progress: {e}")
    
    # LangChain callback interface methods
    def on_chain_start(self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs) -> None:
        """Called when a chain starts."""
        pass
    
    def on_chain_end(self, outputs: Dict[str, Any], **kwargs) -> None:
        """Called when a chain ends."""
        pass


def get_progress_callback(config: Optional[RunnableConfig]) -> Optional[ProgressCallbackHandler]:
    """
    Extract ProgressCallbackHandler from LangGraph config.
    
    Industry standard: Callbacks are stored in config["callbacks"],
    which LangGraph may wrap in an AsyncCallbackManager.
    
    Args:
        config: RunnableConfig passed to node functions
        
    Returns:
        ProgressCallbackHandler if found, None otherwise
    """
    if not config:
        return None
    
    callbacks = config.get("callbacks")
    if not callbacks:
        return None
    
    # LangGraph wraps callbacks in a CallbackManager
    # We need to extract the handlers from it
    handlers = []
    
    # Check if it's a CallbackManager (has 'handlers' attribute)
    if hasattr(callbacks, 'handlers'):
        handlers = callbacks.handlers
    elif hasattr(callbacks, 'inheritable_handlers'):
        handlers = callbacks.inheritable_handlers
    elif isinstance(callbacks, (list, tuple)):
        handlers = callbacks
    else:
        # Try to iterate if possible, otherwise return None
        try:
            handlers = list(callbacks)
        except TypeError:
            logger.debug(f"Cannot iterate callbacks of type {type(callbacks)}")
            return None
    
    for callback in handlers:
        if isinstance(callback, ProgressCallbackHandler):
            return callback
    
    return None


def send_progress(
    config: Optional[RunnableConfig],
    stage: str,
    message: str,
    progress: int,
    status: str = "running",
) -> None:
    """
    Convenience function to send progress from a node.
    
    This is the main function nodes should use:
    
        def my_node(state: State, config: RunnableConfig) -> State:
            send_progress(config, "my_stage", "Processing...", 50)
            # ... do work ...
            return state
    
    Args:
        config: RunnableConfig from node function signature
        stage: Stage identifier
        message: Human-readable message
        progress: Progress percentage (0-100)
        status: Status string (running, completed, failed, skipped)
    """
    handler = get_progress_callback(config)
    if handler:
        handler.send_progress_sync(stage, message, progress, status)


def create_pipeline_config(
    video_id: str,
    progress_callback: Optional[Callable] = None,
    evaluation_criteria: Any = None,
) -> RunnableConfig:
    """
    Create a LangGraph config with callbacks and metadata.
    
    Industry standard: All non-serializable items go in config,
    not state. This keeps state checkpoint-safe.
    
    Args:
        video_id: Video/thread ID for checkpointing
        progress_callback: Function to broadcast progress updates
        evaluation_criteria: EvaluationCriteria object
        
    Returns:
        RunnableConfig ready to pass to graph.ainvoke()
    """
    handler = ProgressCallbackHandler(
        video_id=video_id,
        broadcast_fn=progress_callback,
    )
    
    return {
        "configurable": {
            "thread_id": video_id,
            # Store criteria in configurable (accessible but not in state)
            "evaluation_criteria": evaluation_criteria,
        },
        "callbacks": [handler],
    }


def get_evaluation_criteria(config: Optional[RunnableConfig]) -> Any:
    """
    Extract evaluation criteria from config.
    
    Args:
        config: RunnableConfig from node function
        
    Returns:
        EvaluationCriteria object or None
    """
    if not config:
        return None
    
    configurable = config.get("configurable", {})
    return configurable.get("evaluation_criteria")
