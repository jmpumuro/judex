"""
LangGraph Checkpointing with PostgreSQL.

This module provides proper industry-standard checkpointing for the pipeline,
enabling:
- State persistence at each node boundary
- Resume from any checkpoint
- Parallel execution safety
- Full state serialization (no patching needed)

Usage:
    from app.pipeline.checkpointer import get_checkpointer, get_graph_with_checkpointing
    
    # Get checkpointed graph
    graph = get_graph_with_checkpointing()
    
    # Run with thread_id for checkpointing
    result = await graph.ainvoke(state, config={"configurable": {"thread_id": video_id}})
    
    # Resume from checkpoint
    result = await graph.ainvoke(None, config={"configurable": {"thread_id": video_id}})
"""
import os
from typing import Optional
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.core.config import settings
from app.core.logging import get_logger
from app.pipeline.serializer import get_numpy_safe_serializer

logger = get_logger("checkpointer")

# Singleton checkpointers
_sync_checkpointer: Optional[PostgresSaver] = None
_async_checkpointer: Optional[AsyncPostgresSaver] = None
_async_connection_pool = None


def get_database_url() -> str:
    """Get PostgreSQL connection URL for checkpointing."""
    # Use the same DATABASE_URL as the main app (from docker-compose env)
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url
    
    # Fallback to individual env vars
    db_host = os.getenv("DB_HOST", "host.docker.internal")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "judex")
    db_user = os.getenv("DB_USER", "docker")
    db_pass = os.getenv("DB_PASS", "docker")
    
    return f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"


def _ensure_tables_exist():
    """Ensure checkpoint tables exist (run once at startup)."""
    import psycopg
    database_url = get_database_url()
    
    # Setup tables using autocommit connection
    # This is required because CREATE INDEX CONCURRENTLY cannot run in a transaction
    with psycopg.connect(database_url, autocommit=True) as setup_conn:
        setup_saver = PostgresSaver(setup_conn, serde=get_numpy_safe_serializer())
        setup_saver.setup()
        logger.info("✓ Checkpoint tables created/verified")


def get_checkpointer() -> PostgresSaver:
    """
    Get or create the sync PostgreSQL checkpointer singleton.
    Use this for synchronous operations only.
    """
    global _sync_checkpointer
    
    if _sync_checkpointer is None:
        try:
            import psycopg
            database_url = get_database_url()
            logger.info("Initializing sync PostgreSQL checkpointer")
            
            _ensure_tables_exist()

            conn = psycopg.connect(database_url)
            _sync_checkpointer = PostgresSaver(conn, serde=get_numpy_safe_serializer())

            logger.info("✓ Sync PostgreSQL checkpointer initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize sync checkpointer: {e}")
            raise
    
    return _sync_checkpointer


async def get_async_checkpointer() -> AsyncPostgresSaver:
    """
    Get or create the async PostgreSQL checkpointer singleton.
    Use this for async pipeline operations (ainvoke).
    """
    global _async_checkpointer, _async_connection_pool
    
    if _async_checkpointer is None:
        try:
            from psycopg_pool import AsyncConnectionPool
            
            database_url = get_database_url()
            logger.info("Initializing async PostgreSQL checkpointer")
            
            # Ensure tables exist (sync operation, run once)
            _ensure_tables_exist()
            
            # Create async connection pool
            _async_connection_pool = AsyncConnectionPool(
                conninfo=database_url,
                max_size=10,
                open=False,  # Don't open yet
            )
            await _async_connection_pool.open()

            _async_checkpointer = AsyncPostgresSaver(_async_connection_pool, serde=get_numpy_safe_serializer())

            logger.info("✓ Async PostgreSQL checkpointer initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize async checkpointer: {e}")
            raise
    
    return _async_checkpointer


def reset_checkpointer():
    """Reset the checkpointer singletons (for testing)."""
    global _sync_checkpointer, _async_checkpointer, _async_connection_pool
    _sync_checkpointer = None
    _async_checkpointer = None
    _async_connection_pool = None


async def get_checkpoint_state(thread_id: str) -> Optional[dict]:
    """
    Get the latest checkpoint state for a thread.
    
    Args:
        thread_id: Unique identifier (usually video_id or item_id)
        
    Returns:
        The checkpointed state dict, or None if no checkpoint exists
    """
    try:
        checkpointer = get_checkpointer()
        
        # Get the latest checkpoint
        config = {"configurable": {"thread_id": thread_id}}
        checkpoint = checkpointer.get(config)
        
        if checkpoint and checkpoint.get("channel_values"):
            return checkpoint["channel_values"]
        
        return None
        
    except Exception as e:
        logger.warning(f"Failed to get checkpoint for {thread_id}: {e}")
        return None


async def delete_checkpoint(thread_id: str) -> bool:
    """
    Delete all checkpoints for a thread.
    
    Args:
        thread_id: Unique identifier
        
    Returns:
        True if deleted, False otherwise
    """
    try:
        checkpointer = get_checkpointer()
        
        # Delete checkpoints for this thread
        config = {"configurable": {"thread_id": thread_id}}
        
        # LangGraph checkpoint deletion - iterate and delete
        for checkpoint in checkpointer.list(config):
            checkpointer.delete(checkpoint.config)
        
        logger.info(f"Deleted checkpoints for thread {thread_id}")
        return True
        
    except Exception as e:
        logger.warning(f"Failed to delete checkpoint for {thread_id}: {e}")
        return False


def get_last_completed_node(thread_id: str) -> Optional[str]:
    """
    Get the name of the last successfully completed node for a thread.
    
    Args:
        thread_id: Unique identifier
        
    Returns:
        Node name or None if no checkpoint exists
    """
    try:
        checkpointer = get_checkpointer()
        config = {"configurable": {"thread_id": thread_id}}
        
        checkpoint = checkpointer.get(config)
        if checkpoint:
            # The checkpoint metadata contains info about which node was last
            metadata = checkpoint.get("metadata", {})
            return metadata.get("source", None)
        
        return None
        
    except Exception as e:
        logger.warning(f"Failed to get last node for {thread_id}: {e}")
        return None


# Pipeline node order for resume calculation
PIPELINE_NODES = [
    "ingest_video",
    "segment_video", 
    "run_pipeline",
    "fuse_policy",
    "generate_llm_report",
]


def can_resume_from(thread_id: str, target_node: str) -> bool:
    """
    Check if we can resume from a specific node.
    
    Args:
        thread_id: Unique identifier
        target_node: The node we want to resume from
        
    Returns:
        True if the checkpoint exists and includes all data up to target_node
    """
    last_node = get_last_completed_node(thread_id)
    if not last_node:
        return False
    
    try:
        last_idx = PIPELINE_NODES.index(last_node)
        target_idx = PIPELINE_NODES.index(target_node)
        
        # Can resume if we've completed at least the node before target
        return last_idx >= target_idx - 1
        
    except ValueError:
        return False
