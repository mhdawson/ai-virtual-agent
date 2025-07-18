"""
Database configuration and session management for PostgreSQL with SQLAlchemy async.

This module sets up the async database engine and provides session management
for the AI Virtual Assistant application.
"""

import os

from dotenv import load_dotenv
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from .utils.telemetry import create_operation_span

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=True)

# Instrument SQLAlchemy for OpenTelemetry tracing
if os.getenv("OTEL_SERVICE_NAME"):
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db():
    """
    Dependency function that provides database sessions for FastAPI endpoints.

    Yields:
        AsyncSession: Database session that automatically handles cleanup
    """

    with create_operation_span(
        "database_session",
        {
            "db.connection_string": (
                DATABASE_URL.replace(DATABASE_URL.split("@")[0] + "@", "@***:***@")
                if DATABASE_URL
                else "unknown"
            ),
        },
    ):
        async with AsyncSessionLocal() as session:
            yield session
