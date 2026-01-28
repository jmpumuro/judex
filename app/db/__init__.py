"""
Database module for SafeVid.
"""
from app.db.connection import get_db, init_db, get_db_session, SessionLocal, engine
from app.db.models import (
    Base,
    Evaluation,
    EvaluationItem,
    EvaluationResult,
    EvaluationEvidence,
    EvaluationStatus,
    Criteria,
    LiveEvent,
    Verdict,
    EvidenceType,
)

__all__ = [
    "get_db",
    "init_db",
    "get_db_session",
    "SessionLocal",
    "engine",
    "Base",
    "Evaluation",
    "EvaluationItem",
    "EvaluationResult",
    "EvaluationEvidence",
    "EvaluationStatus",
    "Criteria",
    "LiveEvent",
    "Verdict",
    "EvidenceType",
]
