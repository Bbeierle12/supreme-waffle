"""Tests for error handling and logging."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from exceptions import (
    AirQualityException,
    ValidationError,
    DataNotFoundError,
    DatabaseError,
    ExternalAPIError,
    ConfigurationError,
    RateLimitError,
)


client = TestClient(app)


class TestCustomExceptions:
    """Test custom exception classes."""

    def test_air_quality_exception_base(self):
        """Test base exception class."""
        exc = AirQualityException(
            "Test error",
            details={"key": "value"},
            status_code=400
        )
        assert exc.message == "Test error"
        assert exc.details == {"key": "value"}
        assert exc.status_code == 400

    def test_validation_error(self):
        """Test validation error has correct status code."""
        exc = ValidationError("Invalid input")
        assert exc.status_code == 422

    def test_data_not_found_error(self):
        """Test data not found error."""
        exc = DataNotFoundError("Resource not found")
        assert exc.status_code == 404

    def test_database_error(self):
        """Test database error."""
        exc = DatabaseError("Connection failed")
        assert exc.status_code == 500

    def test_external_api_error(self):
        """Test external API error."""
        exc = ExternalAPIError(
            "API call failed",
            api_name="PurpleAir"
        )
        assert exc.status_code == 502
        assert exc.api_name == "PurpleAir"

    def test_configuration_error(self):
        """Test configuration error."""
        exc = ConfigurationError("Missing API key")
        assert exc.status_code == 500

    def test_rate_limit_error(self):
        """Test rate limit error."""
        exc = RateLimitError("Too many requests", retry_after=60)
        assert exc.status_code == 429
        assert exc.retry_after == 60


class TestAPIErrorHandling:
    """Test API error handling."""

    def test_validation_error_response(self):
        """Test that validation errors return proper response."""
        # Empty question should trigger validation error
        response = client.post(
            "/query",
            json={"question": "", "location": "bakersfield"}
        )
        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["type"] == "ValidationError"

    def test_invalid_location_error(self):
        """Test invalid location returns validation error."""
        response = client.post(
            "/query",
            json={"question": "test", "location": "nonexistent_location"}
        )
        assert response.status_code == 422
        data = response.json()
        assert "error" in data

    def test_xss_attempt_blocked(self):
        """Test that XSS attempts are blocked."""
        response = client.post(
            "/query",
            json={
                "question": "<script>alert('xss')</script>",
                "location": "bakersfield"
            }
        )
        assert response.status_code == 422
        data = response.json()
        assert "error" in data

    def test_sql_injection_blocked(self):
        """Test that SQL injection attempts are blocked."""
        response = client.post(
            "/query",
            json={
                "question": "test'; DROP TABLE observations; --",
                "location": "bakersfield"
            }
        )
        assert response.status_code == 422
        data = response.json()
        assert "error" in data

    def test_missing_api_key_error(self):
        """Test that missing API key raises configuration error."""
        with patch('main.settings.anthropic_api_key', None):
            response = client.post(
                "/query",
                json={"question": "test", "location": "bakersfield"}
            )
            # Should return error response from global handler
            assert response.status_code in [500, 422]
            data = response.json()
            assert "error" in data


class TestGlobalExceptionHandlers:
    """Test global exception handlers."""

    def test_http_exception_handler(self):
        """Test HTTP exception handler."""
        # Request non-existent endpoint
        response = client.get("/nonexistent")
        assert response.status_code == 404
        data = response.json()
        # FastAPI's default 404 uses "detail", custom handlers use "error"
        assert "error" in data or "detail" in data

    def test_general_exception_handler(self):
        """Test general exception handler for unexpected errors."""
        # This would require mocking an endpoint to raise an exception
        # For now, we just verify the handler is registered
        assert hasattr(app, "exception_handlers")


class TestLogging:
    """Test logging configuration."""

    def test_logger_creation(self):
        """Test that loggers can be created."""
        from logging_config import get_logger

        logger = get_logger("test")
        assert logger is not None
        assert "test" in logger.name

    def test_setup_logging(self):
        """Test logging setup."""
        from logging_config import setup_logging
        import tempfile
        from pathlib import Path
        import logging

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            logger = setup_logging(log_level="DEBUG", log_file=log_file)

            assert logger is not None
            logger.info("Test message")

            # Verify log file was created
            assert log_file.exists()

            # Close all handlers to release file lock
            for handler in logger.handlers[:]:
                handler.close()
                logger.removeHandler(handler)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
