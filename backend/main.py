"""
FastAPI main application module for AI Virtual Assistant.

This module initializes the FastAPI application, configures middleware,
registers API routes, and handles static file serving for the frontend.
The app provides a complete REST API for managing virtual assistants,
knowledge bases, tools, and chat interactions.
"""

import sys

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .database import AsyncSessionLocal
from .routes import (
    chat_sessions,
    guardrails,
    knowledge_bases,
    llama_stack,
    mcp_servers,
    model_servers,
    tools,
    users,
    virtual_assistants,
)
from .utils.logging_config import get_logger, setup_logging
from .utils.telemetry import RequestTracingMiddleware, create_operation_span

load_dotenv()

# Configure centralized logging
setup_logging(level="INFO")
logger = get_logger(__name__)

app = FastAPI()

# Initialize OpenTelemetry tracing
# setup_telemetry(app, "ai-virtual-assistant-backend")  # Disabled: using auto-instrumentation instead

# Add request tracing middleware to create parent spans for each request
app.add_middleware(RequestTracingMiddleware)

origins = ["*"]  # Update this with the frontend domain in production

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    """
    Initialize application on startup by syncing external resources.

    Synchronizes MCP servers, model servers, and knowledge bases with
    their external sources (LlamaStack, etc.) to ensure consistency.
    """
    from .utils.telemetry import get_tracer
    import os
    
    # Create top-level span for application startup if OpenTelemetry is enabled
    tracer = get_tracer("ai-virtual-assistant-startup")
    
    startup_attributes = {
        "app.name": "ai-virtual-assistant",
        "app.version": "1.1.0",
        "app.environment": os.getenv("OTEL_DEPLOYMENT_ENVIRONMENT", "unknown"),
        "startup.phase": "initialization"
    }
    
    with tracer.start_as_current_span("application_startup", attributes=startup_attributes) as main_span:
        logger.info("Starting AI Virtual Assistant application initialization")
        
        # Sync MCP servers
        with tracer.start_as_current_span("startup.sync_mcp_servers") as span:
            span.set_attributes({"sync.component": "mcp_servers"})
            try:
                async with AsyncSessionLocal() as session:
                    await mcp_servers.sync_mcp_servers(session)
                span.set_attributes({"sync.status": "success"})
                logger.info("MCP servers sync completed successfully")
            except Exception as e:
                span.set_attributes({"sync.status": "error", "error.message": str(e)})
                logger.error(f"Failed to sync MCP servers on startup: {str(e)}")

        # Sync model servers
        with tracer.start_as_current_span("startup.sync_model_servers") as span:
            span.set_attributes({"sync.component": "model_servers"})
            async with AsyncSessionLocal() as session:
                try:
                    await model_servers.sync_model_servers(session)
                    span.set_attributes({"sync.status": "success"})
                    logger.info("Model servers sync completed successfully")
                except Exception as e:
                    span.set_attributes({"sync.status": "error", "error.message": str(e)})
                    logger.error(f"Failed to sync model servers on startup: {str(e)}")

        # Sync knowledge bases
        with tracer.start_as_current_span("startup.sync_knowledge_bases") as span:
            span.set_attributes({"sync.component": "knowledge_bases"})
            async with AsyncSessionLocal() as session:
                try:
                    await knowledge_bases.sync_knowledge_bases(session)
                    span.set_attributes({"sync.status": "success"})
                    logger.info("Knowledge bases sync completed successfully")
                except Exception as e:
                    span.set_attributes({"sync.status": "error", "error.message": str(e)})
                    logger.error(f"Failed to sync knowledge bases on startup: {str(e)}")
        
        main_span.set_attributes({"startup.status": "completed"})
        logger.info("AI Virtual Assistant application initialization completed")


app.include_router(users.router, prefix="/api")
app.include_router(mcp_servers.router, prefix="/api")
app.include_router(tools.router, prefix="/api")
app.include_router(knowledge_bases.router, prefix="/api")
app.include_router(virtual_assistants.router, prefix="/api")
app.include_router(guardrails.router, prefix="/api")
app.include_router(model_servers.router, prefix="/api")
app.include_router(llama_stack.router, prefix="/api")
app.include_router(chat_sessions.router, prefix="/api")


# Serve React App (frontend)
class SPAStaticFiles(StaticFiles):
    """
    Custom static file handler for Single Page Application routing.

    Handles dev mode proxying to React dev server and production fallback
    to index.html for client-side routing.
    """

    async def get_response(self, path: str, scope):
        if len(sys.argv) > 1 and sys.argv[1] == "dev":
            # We are in Dev mode, proxy to the React dev server
            async with httpx.AsyncClient() as client:
                response = await client.get(f"http://localhost:8000/{path}")
            return Response(response.text, status_code=response.status_code)
        else:
            try:
                return await super().get_response(path, scope)
            except (HTTPException, StarletteHTTPException) as ex:
                if ex.status_code == 404:
                    return await super().get_response("index.html", scope)
                else:
                    raise ex


app.mount(
    "/", SPAStaticFiles(directory="backend/public", html=True), name="spa-static-files"
)
