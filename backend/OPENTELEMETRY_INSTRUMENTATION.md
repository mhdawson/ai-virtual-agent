# OpenTelemetry Instrumentation for AI Virtual Assistant Backend

This document describes the manual OpenTelemetry instrumentation that has been added to the AI Virtual Assistant backend components to provide comprehensive observability and distributed tracing.

## Overview

The backend now includes both **automatic** and **manual** OpenTelemetry instrumentation to provide detailed visibility into application performance, database operations, external service calls, and user interactions.

## Components Instrumented

### 1. OpenTelemetry Configuration Module (`utils/telemetry.py`)

**Purpose**: Centralized OpenTelemetry setup and helper functions

**Features**:
- Automatic detection of OpenTelemetry environment variables
- OTLP HTTP exporter configuration
- Resource attribute configuration
- Tracer provider and span processor setup
- Helper functions for manual instrumentation
- Decorators for function tracing

**Key Functions**:
- `setup_telemetry()` - Initialize OpenTelemetry tracing
- `get_tracer()` - Get tracer instance for manual spans
- `create_span()` - Create spans with attributes
- `@trace_async_function()` - Decorator for async function tracing
- `@trace_function()` - Decorator for sync function tracing

### 2. Main Application (`main.py`)

**Instrumentation**:
- FastAPI auto-instrumentation via `FastAPIInstrumentor`
- Application startup tracing initialization
- Integration with OpenTelemetry configuration

**Traces Captured**:
- HTTP request/response cycles
- Middleware execution
- Route handler performance
- Application startup events

### 3. Database Layer (`database.py`)

**Instrumentation**:
- SQLAlchemy auto-instrumentation for query tracing
- Manual span creation for database session management
- Database connection pooling visibility

**Traces Captured**:
- SQL query execution with parameters
- Database connection acquisition/release
- Transaction boundaries
- Query performance metrics

**Attributes Added**:
- `db.system`: "postgresql"
- `db.operation`: Operation type (select, insert, update, delete)
- `db.table`: Target table name

### 4. API Routes

#### User Management (`routes/users.py`)

**Instrumentation**:
- Decorator-based function tracing
- Manual span creation for sub-operations
- Authentication flow tracing
- Database lookup instrumentation

**Traces Captured**:
- User profile retrieval
- Authentication header extraction
- User database lookups
- Authorization checks

**Attributes Added**:
- `endpoint`: API endpoint path
- `operation`: CRUD operation type
- `auth.username`: Authenticated username
- `auth.email`: User email
- `user.id`: User identifier
- `user.role`: User role
- `user.found`: Whether user was found

#### Chat Sessions (`routes/chat_sessions.py`)

**Instrumentation**:
- Function-level tracing for session operations
- LlamaStack API call tracing

**Traces Captured**:
- Chat session creation
- Session listing operations
- LlamaStack integration calls

**Attributes Added**:
- `endpoint`: API endpoint
- `operation`: Session operation type
- `agent_id`: Associated agent identifier

### 5. Services Layer

#### LlamaStack Sync Service (`services/llamastack_sync.py`)

**Instrumentation**:
- External service call tracing
- Knowledge base synchronization operations
- Error handling and status tracking

**Traces Captured**:
- Knowledge base creation sync
- Vector database registration
- LlamaStack API interactions

**Attributes Added**:
- `service`: "llamastack"
- `operation`: Sync operation type
- `kb.name`: Knowledge base name
- `kb.vector_db_name`: Vector database identifier
- `kb.embedding_model`: Embedding model used
- `sync.status`: Operation status (success/error)

## Automatic Instrumentation

The following libraries are automatically instrumented:

1. **FastAPI**: HTTP requests, route handlers, middleware
2. **SQLAlchemy**: Database queries, connections, transactions
3. **HTTPX**: External HTTP client calls
4. **Logging**: Log correlation with trace context

## Manual Instrumentation Patterns

### Function Decorators

```python
@trace_async_function("operation_name", {"attribute": "value"})
async def my_function():
    # Function body automatically traced
    pass
```

### Manual Span Creation

```python
tracer = get_tracer(__name__)
with tracer.start_as_current_span("operation_name") as span:
    span.set_attributes({
        "custom.attribute": "value",
        "operation.type": "database_query"
    })
    # Operation code here
```

### Error Handling

```python
try:
    # Operation code
    span.set_attributes({"operation.status": "success"})
except Exception as e:
    span.set_attributes({
        "operation.status": "error",
        "error.message": str(e)
    })
    span.record_exception(e)
    raise
```

## Trace Attributes Standards

The instrumentation follows OpenTelemetry semantic conventions:

### HTTP Attributes
- `http.method`: HTTP method (GET, POST, etc.)
- `http.url`: Request URL
- `http.status_code`: Response status code

### Database Attributes  
- `db.system`: Database system ("postgresql")
- `db.operation`: Operation type
- `db.table`: Table name
- `db.statement`: SQL statement (auto-added)

### Custom Attributes
- `endpoint`: API endpoint path
- `operation`: High-level operation type
- `user.id`: User identifier
- `service`: External service name
- `sync.status`: Operation result status

## Configuration

### Environment Variables

The instrumentation is activated when these environment variables are present:

```bash
OTEL_SERVICE_NAME=ai-virtual-assistant-backend
OTEL_SERVICE_VERSION=1.0.0
OTEL_SERVICE_NAMESPACE=ai-virtual-agent
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector-collector.observability-hub.svc.cluster.local:4318/v1/traces
DEPLOYMENT_ENVIRONMENT=production
```

### Resource Attributes

Automatically configured resource attributes:
- `service.name`: Service identifier
- `service.version`: Application version
- `service.namespace`: Kubernetes namespace
- `deployment.environment`: Environment (dev/staging/prod)

## Benefits

1. **Performance Monitoring**: Track request latency and database query performance
2. **Error Tracking**: Automatic exception recording and error rate monitoring
3. **Dependency Mapping**: Visualize service dependencies and call flows
4. **Database Insights**: Monitor SQL query performance and optimization opportunities
5. **User Journey Tracking**: Trace user interactions across API endpoints
6. **Service Health**: Monitor external service integration health

## Dependencies Added

The following OpenTelemetry packages have been added to `requirements.txt`:

```
opentelemetry-api
opentelemetry-sdk
opentelemetry-exporter-otlp-proto-http
opentelemetry-instrumentation-fastapi
opentelemetry-instrumentation-httpx
opentelemetry-instrumentation-sqlalchemy
opentelemetry-instrumentation-logging
```

## Future Enhancements

1. **Additional Route Instrumentation**: Add tracing to remaining API routes
2. **Business Logic Tracing**: Instrument complex business operations
3. **Custom Metrics**: Add OpenTelemetry metrics collection
4. **Span Links**: Connect related operations across services
5. **Sampling Configuration**: Implement intelligent trace sampling
6. **Performance Profiling**: Add detailed performance instrumentation

## Testing

To verify instrumentation is working:

1. **Check Logs**: Look for "OpenTelemetry tracing initialized" messages
2. **Make API Calls**: Generate trace data through normal API usage
3. **View Traces**: Check your observability platform for trace data
4. **Verify Spans**: Ensure spans contain expected attributes and timing data

The instrumentation will automatically export traces to the configured OTLP endpoint when the application is deployed with the OpenTelemetry auto-instrumentation we configured in the Helm charts. 