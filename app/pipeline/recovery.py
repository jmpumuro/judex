"""
Pipeline Recovery - Startup Detection and Resume.

Industry Standard: On container restart, detect stuck evaluations and resume them
using the EXISTING reprocess infrastructure (no redundancy).

This module ONLY handles:
1. Detecting stuck evaluations (status=PROCESSING for too long)
2. Triggering existing reprocess logic to resume them

All actual recovery logic is in:
- app/pipeline/graph.py (run_pipeline, resume_pipeline)
- app/api/evaluations.py (reprocess_evaluation)
- app/pipeline/checkpointer.py (LangGraph checkpointing)
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from app.db.connection import get_db_session
from app.db.models import Evaluation, EvaluationItem, EvaluationStatus
from app.core.logging import get_logger

logger = get_logger("pipeline.recovery")


async def find_stuck_evaluations(
    stuck_threshold_minutes: int = 10  # Reduced from 30 - catch stuck faster
) -> List[Dict[str, Any]]:
    """
    Find evaluations stuck in PROCESSING status.
    
    Returns list of evaluation info dicts.
    """
    stuck_threshold = timedelta(minutes=stuck_threshold_minutes)
    cutoff = datetime.utcnow() - stuck_threshold
    
    stuck = []
    
    with get_db_session() as session:
        evaluations = session.query(Evaluation).filter(
            Evaluation.status == EvaluationStatus.PROCESSING,
            Evaluation.started_at < cutoff
        ).all()
        
        for eval in evaluations:
            stuck.append({
                "evaluation_id": eval.id,
                "started_at": eval.started_at,
                "current_stage": eval.current_stage,
                "items_total": eval.items_total,
                "items_completed": eval.items_completed,
                "criteria_snapshot": eval.criteria_snapshot,
            })
            
            logger.info(
                f"Found stuck evaluation: {eval.id} "
                f"(started: {eval.started_at}, stage: {eval.current_stage})"
            )
    
    return stuck


async def recover_stuck_evaluation(evaluation_id: str) -> Dict[str, Any]:
    """
    Recover a stuck evaluation using existing reprocess infrastructure.
    
    This is a thin wrapper that:
    1. Validates the evaluation exists and is stuck
    2. Calls the existing reprocess logic with skip_early_stages=True
    """
    from app.api.evaluations import reprocess_evaluation_item, EvaluationRepository
    from app.evaluation.criteria import EvaluationCriteria
    
    logger.info(f"Recovering evaluation: {evaluation_id}")
    
    with get_db_session() as session:
        evaluation = session.query(Evaluation).filter(
            Evaluation.id == evaluation_id
        ).first()
        
        if not evaluation:
            return {"status": "not_found", "evaluation_id": evaluation_id}
        
        if evaluation.status == EvaluationStatus.COMPLETED:
            return {"status": "already_complete", "evaluation_id": evaluation_id}
        
        # Get criteria from snapshot
        criteria_snapshot = evaluation.criteria_snapshot
        criteria = EvaluationCriteria(**criteria_snapshot) if criteria_snapshot else None
        
        # Get incomplete items
        incomplete_items = [
            {
                "item_id": item.id,
                "video_path": item.uploaded_video_path or item.source_path,
            }
            for item in evaluation.items
            if item.status in [EvaluationStatus.PROCESSING, EvaluationStatus.PENDING]
        ]
        
        if not incomplete_items:
            # All items complete, just update evaluation
            evaluation.status = EvaluationStatus.COMPLETED
            evaluation.completed_at = datetime.utcnow()
            session.commit()
            return {"status": "completed", "evaluation_id": evaluation_id}
        
        # Mark as recovering
        evaluation.error_message = (
            f"{evaluation.error_message or ''}\n"
            f"Recovery started at {datetime.utcnow().isoformat()}"
        ).strip()
        session.commit()
    
    # Reprocess each incomplete item using existing infrastructure
    recovered = 0
    failed = 0
    
    for item_info in incomplete_items:
        try:
            await reprocess_evaluation_item(
                evaluation_id=evaluation_id,
                item_id=item_info["item_id"],
                video_path=item_info["video_path"],
                criteria=criteria,
                resume_from_checkpoint=True,  # Skip ingest/segment if data exists
            )
            recovered += 1
        except Exception as e:
            logger.error(f"Failed to recover item {item_info['item_id']}: {e}")
            failed += 1
    
    return {
        "status": "recovered",
        "evaluation_id": evaluation_id,
        "items_recovered": recovered,
        "items_failed": failed,
    }


async def recover_all_stuck_evaluations(
    stuck_threshold_minutes: int = 10,  # Match find_stuck_evaluations default
    max_concurrent: int = 2,
) -> Dict[str, Any]:
    """
    Find and recover all stuck evaluations.
    
    Called on application startup.
    """
    logger.info("=== Checking for stuck evaluations ===")
    
    stuck = await find_stuck_evaluations(stuck_threshold_minutes)
    
    if not stuck:
        logger.info("No stuck evaluations found")
        return {"total": 0, "recovered": 0, "failed": 0}
    
    logger.info(f"Found {len(stuck)} stuck evaluations, recovering...")
    
    results = {"total": len(stuck), "recovered": 0, "failed": 0, "details": []}
    
    # Recover with limited concurrency
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def recover_with_semaphore(eval_info):
        async with semaphore:
            return await recover_stuck_evaluation(eval_info["evaluation_id"])
    
    tasks = [recover_with_semaphore(e) for e in stuck]
    task_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in task_results:
        if isinstance(result, Exception):
            results["failed"] += 1
            results["details"].append({"status": "error", "error": str(result)})
        elif result.get("status") in ["recovered", "completed", "already_complete"]:
            results["recovered"] += 1
            results["details"].append(result)
        else:
            results["failed"] += 1
            results["details"].append(result)
    
    logger.info(
        f"Recovery complete: {results['recovered']} recovered, "
        f"{results['failed']} failed out of {results['total']} stuck"
    )
    
    return results


# Convenience alias for startup
recover_interrupted_evaluations = recover_all_stuck_evaluations
