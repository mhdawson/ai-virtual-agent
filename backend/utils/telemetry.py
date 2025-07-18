"""
OpenTelemetry configuration and instrumentation setup for AI Virtual Assistant backend.

This module provides centralized configuration for OpenTelemetry tracing, including
automatic and manual instrumentation setup for FastAPI, database operations,
and external service calls.
"""

import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .logging_config import get_logger

logger = get_logger(__name__)

# Global tracer instance
tracer: Optional[trace.Tracer] = None


class RequestTracingMiddleware:
    """FastAPI middleware that creates a parent span for each HTTP request."""
    
    def __init__(self, app):
        self.app = app
        # Health check paths to exclude from tracing
        self.health_check_paths = {
            "/",
            "/health", 
            "/healthz",
            "/ready",
            "/readiness", 
            "/liveness",
            "/metrics",
            "/favicon.ico"
        }
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Extract request information
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")
        user_agent = dict(scope.get("headers", [])).get(b"user-agent", b"").decode()
        
        # Skip tracing for health checks and probe requests
        if (path in self.health_check_paths or "kube-probe" in user_agent):
            await self.app(scope, receive, send)
            return
        
        # Get tracer instance
        tracer = get_tracer("request_tracer")
        
        # Create parent span for the entire request
        span_name = f"{method} {path}"
        
        with tracer.start_as_current_span(
            span_name,
            kind=trace.SpanKind.SERVER,
            attributes={
                "http.method": method,
                "http.target": path,
                "http.scheme": scope.get("scheme", "http"),
                "http.host": scope.get("server", ["unknown", None])[0],
                "http.user_agent": dict(scope.get("headers", [])).get(b"user-agent", b"").decode(),
            }
        ) as span:
            # Set up response status capture
            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    status_code = message.get("status", 500)
                    span.set_attribute("http.status_code", status_code)
                    if status_code >= 400:
                        span.set_status(trace.Status(trace.StatusCode.ERROR))
                await send(message)
            
            try:
                await self.app(scope, receive, send_wrapper)
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise


def setup_telemetry(app=None, service_name: str = "ai-virtual-assistant-backend"):
    """
    Initialize OpenTelemetry tracing for the application.
    
    Args:
        app: FastAPI application instance (optional)
        service_name: Name of the service for tracing
    """
    global tracer
    
    # Check if OpenTelemetry is enabled
    otel_enabled = os.getenv("OTEL_SERVICE_NAME") is not None
    if not otel_enabled:
        logger.info("OpenTelemetry not configured - skipping instrumentation")
        return

    try:
        # Configure resource attributes
        resource = Resource.create(
            {
                "service.name": service_name,
                "service.version": os.getenv("OTEL_SERVICE_VERSION", "1.0.0"),
                "service.namespace": os.getenv(
                    "OTEL_SERVICE_NAMESPACE", "ai-virtual-agent"
                ),
                "deployment.environment": os.getenv(
                    "DEPLOYMENT_ENVIRONMENT", "development"
                ),
            }
        )

        # Configure trace provider
        trace_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(trace_provider)

        # Configure OTLP exporter
        otlp_exporter = OTLPSpanExporter(
            endpoint=os.getenv(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces"
            ),
            headers={},
        )

        # Add standard batch span processor  
        span_processor = BatchSpanProcessor(otlp_exporter)
        trace_provider.add_span_processor(span_processor)

        # Get tracer instance
        tracer = trace.get_tracer(__name__)

        # Setup automatic instrumentation
        setup_auto_instrumentation(app)

        logger.info(f"OpenTelemetry tracing initialized for service: {service_name}")
        
    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry: {str(e)}")


def setup_auto_instrumentation(app=None):
    """Setup automatic instrumentation for common libraries."""
    try:
        # Instrument FastAPI (we'll filter health checks in middleware)
        if app:
            FastAPIInstrumentor.instrument_app(
                app, 
                tracer_provider=trace.get_tracer_provider()
            )
            logger.info("FastAPI auto-instrumentation enabled")

        # Instrument HTTP client with exclusions for LlamaStack
        llamastack_url = os.getenv("LLAMASTACK_URL", "http://localhost:8321")
        HTTPXClientInstrumentor().instrument(
            excluded_urls=[f"{llamastack_url}.*"]
        )
        logger.info("HTTPX auto-instrumentation enabled (excluding LlamaStack)")

        # Instrument logging
        LoggingInstrumentor().instrument(set_logging_format=True)
        logger.info("Logging auto-instrumentation enabled")

        # Note: SQLAlchemy instrumentation will be done in database.py
        # to have access to the engine instance

    except Exception as e:
        logger.error(f"Failed to setup auto-instrumentation: {str(e)}")


def get_tracer(name: str = __name__) -> trace.Tracer:
    """
    Get a tracer instance for manual instrumentation.

    Args:
        name: Name of the tracer (usually module name)

    Returns:
        OpenTelemetry tracer instance
    """
    return trace.get_tracer(name)


def create_operation_span(operation_name: str, attributes: Optional[dict] = None):
    """
    Create a span for a specific operation within an endpoint.
    
    Args:
        operation_name: Name of the operation (e.g., "database_query", "external_api_call")
        attributes: Optional dictionary of span attributes
    
    Returns:
        Context manager for the span
    
    Example:
        with create_operation_span("user_lookup", {"user_id": user_id}):
            user = await get_user(user_id)
    """
    tracer = get_tracer("operation_tracer")
    return tracer.start_as_current_span(
        operation_name,
        attributes=attributes or {}
    )


def create_span(name: str, attributes: Optional[dict] = None):
    """
    Create a new span with optional attributes.

    Args:
        name: Name of the span
        attributes: Optional dictionary of span attributes

    Returns:
        Span context manager
    """
    tracer = get_tracer()
    span = tracer.start_as_current_span(name)

    if attributes:
        span.set_attributes(attributes)

    return span


def add_span_attributes(span, attributes: dict):
    """
    Add attributes to an existing span.

    Args:
        span: OpenTelemetry span
        attributes: Dictionary of attributes to add
    """
    if span and attributes:
        span.set_attributes(attributes)


def record_exception(span, exception: Exception):
    """
    Record an exception in the current span.

    Args:
        span: OpenTelemetry span
        exception: Exception to record
    """
    if span:
        span.record_exception(exception)
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(exception)))


def trace_async_function(func_name: str, attributes: Optional[dict] = None):
    """
    Decorator for tracing async functions.

    Args:
        func_name: Name for the span
        attributes: Optional span attributes
    """

    def decorator(func):
        import functools
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.start_as_current_span(func_name) as span:
                if attributes:
                    add_span_attributes(span, attributes)

                try:
                    result = await func(*args, **kwargs)
                    span.set_status(trace.Status(trace.StatusCode.OK))
                    return result
                except Exception as e:
                    record_exception(span, e)
                    raise

        return wrapper

    return decorator


def trace_function(func_name: str, attributes: Optional[dict] = None):
    """
    Decorator for tracing synchronous functions.

    Args:
        func_name: Name for the span
        attributes: Optional span attributes
    """

    def decorator(func):
        import functools
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.start_as_current_span(func_name) as span:
                if attributes:
                    add_span_attributes(span, attributes)

                try:
                    result = func(*args, **kwargs)
                    span.set_status(trace.Status(trace.StatusCode.OK))
                    return result
                except Exception as e:
                    record_exception(span, e)
                    raise

        return wrapper

    return decorator
