"""
Database configuration and session management for PostgreSQL with SQLAlchemy async.

This module sets up the async database engine and provides session management
for the AI Virtual Assistant application.
"""

import os

from dotenv import load_dotenv
from .utils.logging_config import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


load_dotenv()
logger = get_logger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=True)

AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db():
    """
    Dependency function that provides database sessions for FastAPI endpoints.

    Yields:
        AsyncSession: Database session that automatically handles cleanup
    """
    from .utils.telemetry import get_tracer

    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("database.get_session") as span:
        span.set_attributes({"db.system": "postgresql", "db.operation": "get_session"})

        async with AsyncSessionLocal() as session:
            yield session
