"""Main FastAPI application for Air Quality NotebookLM."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator, ConfigDict, ValidationError as PydanticValidationError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import json
import re
import traceback

from config import settings, location_config
from storage.database import get_db
from services import QueryService, StatusService, IngestionService
from exceptions import (
    AirQualityException,
    ValidationError,
    DataNotFoundError,
    DatabaseError,
    ExternalAPIError,
    ConfigurationError,
    RateLimitError,
)
from logging_config import setup_logging, get_logger
from rate_limiting import limiter, RATE_LIMITS
from slowapi.errors import RateLimitExceeded


# Set up logging
log_dir = settings.database_path.parent / "logs"
logger = setup_logging(
    log_level=settings.log_level,
    log_file=log_dir / "app.log" if log_dir else None
)

# Scheduler for periodic data updates
scheduler = AsyncIOScheduler()

# Service instances (initialized in lifespan)
query_service: Optional[QueryService] = None
status_service: Optional[StatusService] = None
ingestion_service: Optional[IngestionService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    global query_service, status_service, ingestion_service

    # Startup
    logger.info("Starting Air Quality NotebookLM...")

    # Initialize database
    db = get_db()
    logger.info(f"Database initialized at {settings.database_path}")

    # Initialize services
    query_service = QueryService(settings.anthropic_api_key) if settings.anthropic_api_key else None
    status_service = StatusService(db, settings.database_path)
    ingestion_service = IngestionService(
        db,
        location_config,
        settings.purpleair_api_key,
        settings.openweather_api_key,
        settings.default_location
    )
    logger.info("Services initialized")

    # Schedule data updates (every 10 minutes)
    if settings.purpleair_api_key:
        scheduler.add_job(
            update_air_quality,
            "interval",
            minutes=10,
            id="update_aq",
            replace_existing=True
        )

        scheduler.add_job(
            update_weather,
            "interval",
            minutes=15,
            id="update_weather",
            replace_existing=True
        )

        scheduler.start()
        print("Scheduler started")

    yield

    # Shutdown
    scheduler.shutdown()
    db.close()
    print("Shutdown complete")


app = FastAPI(
    title="Air Quality NotebookLM",
    description="Personal research assistant for air quality data analysis",
    version="0.1.0",
    lifespan=lifespan
)

# Add rate limiter to app state
app.state.limiter = limiter

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handlers
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceeded errors."""
    logger.warning(
        f"Rate limit exceeded for {request.url.path}",
        extra={
            "path": request.url.path,
            "client": request.client.host if request.client else "unknown"
        }
    )
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "error": "Rate limit exceeded",
            "detail": "Too many requests. Please try again later.",
            "type": "RateLimitError"
        },
        headers={"Retry-After": "60"}  # Suggest retry after 60 seconds
    )


@app.exception_handler(AirQualityException)
async def air_quality_exception_handler(request: Request, exc: AirQualityException):
    """Handle custom application exceptions."""
    logger.error(
        f"Application error: {exc.message}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "details": exc.details,
            "status_code": exc.status_code
        }
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "details": exc.details,
            "type": exc.__class__.__name__
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors."""
    logger.warning(
        f"Validation error on {request.url.path}: {exc.errors()}",
        extra={"path": request.url.path, "method": request.method}
    )

    # Serialize errors properly (Pydantic V2 may include non-serializable objects)
    errors = []
    for error in exc.errors():
        error_dict = {
            "type": error.get("type"),
            "loc": error.get("loc"),
            "msg": error.get("msg"),
            "input": str(error.get("input")) if error.get("input") else None
        }
        # Convert ctx values to strings if they exist
        if "ctx" in error and error["ctx"]:
            error_dict["ctx"] = {k: str(v) for k, v in error["ctx"].items()}
        errors.append(error_dict)

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation failed",
            "details": errors,
            "type": "ValidationError"
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle FastAPI HTTP exceptions."""
    logger.warning(
        f"HTTP {exc.status_code} on {request.url.path}: {exc.detail}",
        extra={"path": request.url.path, "method": request.method}
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "type": "HTTPException"
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(
        f"Unexpected error on {request.url.path}: {str(exc)}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "traceback": traceback.format_exc()
        }
    )
    # Don't expose internal error details in production
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "An unexpected error occurred",
            "type": "InternalServerError",
            # Only include details in development
            "details": str(exc) if settings.reload else None
        }
    )


# Request/Response models
class QueryRequest(BaseModel):
    """Request model for query endpoint with comprehensive validation."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The question to ask about air quality data"
    )
    location: str = Field(
        default="bakersfield",
        min_length=1,
        max_length=50,
        pattern="^[a-z0-9_-]+$",
        description="Location identifier (lowercase alphanumeric, underscores, and hyphens only)"
    )

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator('question')
    @classmethod
    def validate_question(cls, v: str) -> str:
        """Validate question content."""
        if not v.strip():
            raise ValueError('Question cannot be empty or only whitespace')

        # Check for potential injection attempts
        suspicious_patterns = [
            # XSS patterns
            r'<script',
            r'javascript:',
            r'onerror=',
            # Code injection patterns
            r'eval\(',
            r'__import__',
            r'exec\(',
            # SQL injection patterns
            r';\s*drop\s+table',
            r';\s*delete\s+from',
            r';\s*update\s+',
            r';\s*insert\s+into',
            r'union\s+select',
            r'--\s*$',
        ]

        for pattern in suspicious_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError(f'Question contains potentially unsafe content')

        return v.strip()

    @field_validator('location')
    @classmethod
    def validate_location(cls, v: str) -> str:
        """Validate location exists in configuration."""
        v = v.lower().strip()

        # Check if location exists
        available_locations = location_config.list_locations()
        if v not in available_locations:
            raise ValueError(
                f'Invalid location: {v}. Available locations: {", ".join(available_locations)}'
            )

        return v


class ToolCall(BaseModel):
    """Model for individual tool call."""
    tool_name: str = Field(..., max_length=100)
    tool_input: dict
    result: Optional[dict] = None


class Answer(BaseModel):
    """Model for query answer."""
    text: str = Field(..., min_length=1)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    sources: Optional[list[str]] = None


class QueryResponse(BaseModel):
    """Response model for query endpoint."""
    answer: Answer
    tool_calls: list[ToolCall]
    rounds: int = Field(..., ge=1, le=100)
    model: str = Field(..., max_length=100)


class StatusResponse(BaseModel):
    """Response model for status endpoint."""
    status: str = Field(..., pattern="^(healthy|degraded|unhealthy)$")
    database: str
    data_range: Optional[dict] = None
    sensors: list[str]


# Background tasks
async def update_air_quality():
    """Background task to update air quality data."""
    if ingestion_service:
        try:
            await ingestion_service.ingest_air_quality()
        except Exception:
            # Errors are already logged in the service
            pass


async def update_weather():
    """Background task to update weather data."""
    if ingestion_service:
        try:
            await ingestion_service.ingest_weather()
        except Exception:
            # Errors are already logged in the service
            pass


# API endpoints
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Air Quality NotebookLM",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/status", response_model=StatusResponse)
@limiter.limit(RATE_LIMITS["status"])
async def get_status(request: Request):
    """Get system status and data availability."""
    if not status_service:
        raise ConfigurationError("Status service not initialized")

    status_data = status_service.get_system_status()
    return StatusResponse(**status_data)


@app.post("/query", response_model=QueryResponse)
@limiter.limit(RATE_LIMITS["query"])
async def query(request: Request, query_request: QueryRequest):
    """
    Answer a research question about air quality data.

    This endpoint uses Claude with safe tool calling to analyze data.
    """
    if not query_service:
        raise ConfigurationError(
            "Query service not initialized",
            details={"setting": "ANTHROPIC_API_KEY"}
        )

    # Process query through service
    result = query_service.process_query(
        question=query_request.question,
        location=query_request.location
    )

    # Build response models
    answer = Answer(**result["answer"])
    tool_calls = [ToolCall(**tc) for tc in result["tool_calls"]]

    return QueryResponse(
        answer=answer,
        tool_calls=tool_calls,
        rounds=result["rounds"],
        model=result["model"]
    )


@app.post("/query/stream")
@limiter.limit(RATE_LIMITS["query_stream"])
async def query_stream(request: Request, query_request: QueryRequest):
    """
    Stream answer to a research question (SSE).

    This provides real-time updates as tools are called and results arrive.
    """
    async def generate():
        """Generator for SSE stream."""
        orchestrator = AnalysisOrchestrator(settings.anthropic_api_key)

        # Send initial message
        yield f"data: {json.dumps({'type': 'start', 'question': query_request.question})}\n\n"

        try:
            # This is a simplified version - would need to modify orchestrator
            # to yield intermediate results
            result = orchestrator.answer_query(
                question=query_request.question,
                location=query_request.location
            )

            # Send tool calls
            for tool_call in result["tool_calls"]:
                yield f"data: {json.dumps({'type': 'tool', 'data': tool_call})}\n\n"
                await asyncio.sleep(0.1)  # Small delay for UX

            # Send final answer
            yield f"data: {json.dumps({'type': 'answer', 'data': result['answer']})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )


class IngestResponse(BaseModel):
    """Response model for ingestion trigger."""
    status: str = Field(..., pattern="^(completed|failed|partial|in_progress)$")
    message: Optional[str] = None


@app.post("/ingest/trigger", response_model=IngestResponse)
@limiter.limit(RATE_LIMITS["ingest"])
async def trigger_ingestion(request: Request):
    """
    Manually trigger data ingestion (useful for testing).

    Note: In production, this endpoint should require authentication.
    """
    if not ingestion_service:
        raise ConfigurationError("Ingestion service not initialized")

    # Trigger ingestion through service
    result = await ingestion_service.ingest_all()

    return IngestResponse(
        status=result["status"],
        message=f"Ingestion {result['status']}: {result.get('timestamp', '')}"
    )


@app.get("/locations")
@limiter.limit(RATE_LIMITS["locations"])
async def list_locations(request: Request):
    """List available locations."""
    locations = location_config.list_locations()

    return {
        "locations": [
            {
                "id": loc_id,
                "config": location_config.get_location(loc_id)
            }
            for loc_id in locations
        ]
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.lower()
    )
