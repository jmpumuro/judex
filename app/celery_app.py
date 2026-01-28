"""
Celery application configuration for Judex task queue.

Provides sequential video processing to prevent OOM crashes.
"""
import os
from celery import Celery
from celery.signals import task_success, task_failure

# Redis URL from environment or default
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "judex",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks.video_tasks"]
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # CRITICAL: Process only ONE task at a time per worker to prevent OOM
    worker_concurrency=1,
    worker_prefetch_multiplier=1,
    
    # Task result settings
    result_expires=3600,  # 1 hour
    
    # Task tracking
    task_track_started=True,
    task_send_sent_event=True,
    
    # Retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Memory optimization
    worker_max_tasks_per_child=5,  # Restart worker after 5 tasks to free memory
)


# Signal handlers for task completion
@task_success.connect
def on_task_success(sender=None, result=None, **kwargs):
    """Handle successful task completion."""
    from app.core.logging import get_logger
    logger = get_logger("celery.signals")
    
    if result and isinstance(result, dict):
        video_id = result.get("video_id")
        batch_id = result.get("batch_id")
        verdict = result.get("verdict")
        logger.info(f"Task completed: video={video_id}, batch={batch_id}, verdict={verdict}")


@task_failure.connect  
def on_task_failure(sender=None, task_id=None, exception=None, **kwargs):
    """Handle task failure."""
    from app.core.logging import get_logger
    logger = get_logger("celery.signals")
    logger.error(f"Task {task_id} failed: {exception}")


if __name__ == "__main__":
    celery_app.start()
