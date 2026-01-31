"""
Database connection and session management.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
from typing import Generator, Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("db.connection")

# Lazy initialization - don't connect at import time
_engine = None
_SessionLocal = None


def _get_engine():
    """Get or create database engine (lazy initialization)."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # Verify connections before use
            pool_timeout=5,  # Don't wait forever for connection
            echo=False  # Set to True for SQL logging
        )
    return _engine


def _get_session_local():
    """Get or create session factory (lazy initialization)."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_get_engine())
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Dependency for getting database session."""
    SessionLocal = _get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for database session."""
    SessionLocal = _get_session_local()
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    from app.db.models import Base
    
    logger.info("Creating database tables...")
    engine = _get_engine()
    # checkfirst=True skips creating tables/indexes that already exist
    Base.metadata.create_all(bind=engine, checkfirst=True)
    logger.info("Database tables created successfully")


# Backward compatibility exports
def get_engine():
    """Get database engine (for external use)."""
    return _get_engine()
