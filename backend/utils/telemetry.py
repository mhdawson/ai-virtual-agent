"""
OpenTelemetry configuration and instrumentation setup for AI Virtual Assistant backend.

This module provides centralized configuration for OpenTelemetry tracing, including
automatic and manual instrumentation setup for FastAPI, database operations,
and external service calls.
"""

from typing import Optional

from opentelemetry import trace

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
            "/favicon.ico",
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
        if path in self.health_check_paths or "kube-probe" in user_agent:
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
                "http.user_agent": dict(scope.get("headers", []))
                .get(b"user-agent", b"")
                .decode(),
            },
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
    return tracer.start_as_current_span(operation_name, attributes=attributes or {})


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
