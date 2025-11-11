"""Custom exceptions for Air Quality NotebookLM."""
from typing import Optional, Dict, Any


class AirQualityException(Exception):
    """Base exception for all application errors."""

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 500
    ):
        """
        Initialize exception.

        Args:
            message: Human-readable error message
            details: Additional error details
            status_code: HTTP status code for API responses
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.status_code = status_code


class ValidationError(AirQualityException):
    """Raised when input validation fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details, status_code=422)


class DataNotFoundError(AirQualityException):
    """Raised when requested data is not found."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details, status_code=404)


class DatabaseError(AirQualityException):
    """Raised when database operations fail."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details, status_code=500)


class ExternalAPIError(AirQualityException):
    """Raised when external API calls fail."""

    def __init__(
        self,
        message: str,
        api_name: str,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, details, status_code=502)
        self.api_name = api_name


class ConfigurationError(AirQualityException):
    """Raised when configuration is invalid or missing."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details, status_code=500)


class DataQualityError(AirQualityException):
    """Raised when data quality checks fail."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details, status_code=422)


class RateLimitError(AirQualityException):
    """Raised when rate limits are exceeded."""

    def __init__(self, message: str, retry_after: Optional[int] = None):
        details = {"retry_after": retry_after} if retry_after else {}
        super().__init__(message, details, status_code=429)
        self.retry_after = retry_after


class AuthenticationError(AirQualityException):
    """Raised when authentication fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details, status_code=401)


class AuthorizationError(AirQualityException):
    """Raised when authorization fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details, status_code=403)
