"""Rate limiting configuration for API endpoints."""
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request


def get_client_identifier(request: Request) -> str:
    """
    Get client identifier for rate limiting.

    Uses the client IP address by default. In production with a reverse proxy,
    this should be configured to use the X-Forwarded-For header.

    Args:
        request: FastAPI request object

    Returns:
        Client identifier (IP address)
    """
    # Get real IP from X-Forwarded-For if behind proxy
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # X-Forwarded-For can contain multiple IPs, take the first one
        client_ip = forwarded.split(",")[0].strip()
    else:
        # Fall back to direct connection IP
        client_ip = get_remote_address(request)

    return client_ip


# Create limiter instance
limiter = Limiter(
    key_func=get_client_identifier,
    default_limits=["100/hour"],  # Default: 100 requests per hour
    storage_uri="memory://",  # Use in-memory storage (consider Redis for production)
    strategy="fixed-window",  # Fixed window rate limiting
)


# Rate limit configurations for different endpoint types
RATE_LIMITS = {
    # Query endpoints (expensive LLM calls)
    "query": "10/minute",  # Max 10 queries per minute
    "query_stream": "5/minute",  # Max 5 streaming queries per minute

    # Data ingestion (should be restricted)
    "ingest": "2/minute",  # Max 2 manual ingests per minute

    # Read-only endpoints (more permissive)
    "status": "60/minute",  # Max 60 status checks per minute
    "locations": "30/minute",  # Max 30 location lists per minute
}
