"""Main FastAPI application for Air Quality NotebookLM."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import json

from config import settings, location_config
from storage.database import get_db
from llm.orchestrator import AnalysisOrchestrator
from ingestion.purpleair import fetch_and_store
from ingestion.weather import fetch_and_store_weather


# Scheduler for periodic data updates
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # Startup
    print("Starting Air Quality NotebookLM...")

    # Initialize database
    db = get_db()
    print(f"Database initialized at {settings.database_path}")

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

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response models
class QueryRequest(BaseModel):
    question: str
    location: Optional[str] = "bakersfield"


class QueryResponse(BaseModel):
    answer: dict
    tool_calls: list
    rounds: int
    model: str


class StatusResponse(BaseModel):
    status: str
    database: str
    data_range: Optional[dict] = None
    sensors: list


# Background tasks
async def update_air_quality():
    """Background task to update air quality data."""
    try:
        location = location_config.get_location(settings.default_location)
        sensor_ids = location["sensors"]["purpleair"]

        db = get_db()
        await fetch_and_store(
            settings.purpleair_api_key,
            sensor_ids,
            location,
            db
        )
        print(f"Updated air quality data at {datetime.now()}")

    except Exception as e:
        print(f"Error updating air quality: {e}")


async def update_weather():
    """Background task to update weather data."""
    try:
        location = location_config.get_location(settings.default_location)
        db = get_db()

        await fetch_and_store_weather(
            settings.openweather_api_key,
            location,
            db
        )
        print(f"Updated weather data at {datetime.now()}")

    except Exception as e:
        print(f"Error updating weather: {e}")


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
async def get_status():
    """Get system status and data availability."""
    db = get_db()

    # Get data range
    min_ts, max_ts = db.get_time_range("aq")

    data_range = None
    if min_ts and max_ts:
        data_range = {
            "start": str(min_ts),
            "end": str(max_ts)
        }

    # Get sensors
    sensors = db.get_sensors()

    return StatusResponse(
        status="healthy",
        database=str(settings.database_path),
        data_range=data_range,
        sensors=sensors
    )


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    Answer a research question about air quality data.

    This endpoint uses Claude with safe tool calling to analyze data.
    """
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=500,
            detail="Anthropic API key not configured"
        )

    # Initialize orchestrator
    orchestrator = AnalysisOrchestrator(settings.anthropic_api_key)

    try:
        # Get answer
        result = orchestrator.answer_query(
            question=request.question,
            location=request.location
        )

        return QueryResponse(**result)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing query: {str(e)}"
        )


@app.post("/query/stream")
async def query_stream(request: QueryRequest):
    """
    Stream answer to a research question (SSE).

    This provides real-time updates as tools are called and results arrive.
    """
    async def generate():
        """Generator for SSE stream."""
        orchestrator = AnalysisOrchestrator(settings.anthropic_api_key)

        # Send initial message
        yield f"data: {json.dumps({'type': 'start', 'question': request.question})}\n\n"

        try:
            # This is a simplified version - would need to modify orchestrator
            # to yield intermediate results
            result = orchestrator.answer_query(
                question=request.question,
                location=request.location
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


@app.post("/ingest/trigger")
async def trigger_ingestion():
    """Manually trigger data ingestion (useful for testing)."""
    await update_air_quality()
    await update_weather()

    return {"status": "completed"}


@app.get("/locations")
async def list_locations():
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
