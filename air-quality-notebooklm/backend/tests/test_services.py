"""Tests for service layer."""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from services.query_service import QueryService
from services.status_service import StatusService
from services.ingestion_service import IngestionService
from storage.database import Database
from config import LocationConfig
from exceptions import (
    ConfigurationError,
    ValidationError,
    DataNotFoundError
)


class TestQueryService:
    """Test query service."""

    def test_init_without_api_key_raises_error(self):
        """Test that initialization without API key raises ConfigurationError."""
        with pytest.raises(ConfigurationError) as exc_info:
            QueryService(anthropic_api_key="")

        assert "Anthropic API key not configured" in str(exc_info.value)

    def test_init_with_api_key_succeeds(self):
        """Test that initialization with API key succeeds."""
        service = QueryService(anthropic_api_key="test-key")
        assert service is not None
        assert service.orchestrator is not None

    def test_process_query_transforms_response(self):
        """Test that process_query transforms orchestrator response correctly."""
        service = QueryService(anthropic_api_key="test-key")

        # Mock orchestrator response
        mock_result = {
            "answer": {
                "text": "Test answer",
                "confidence": "high",
                "sources": [
                    {"tool": "test_tool", "params": {"param1": "value1"}}
                ]
            },
            "tool_calls": [
                {
                    "tool": "test_tool",
                    "params": {"param1": "value1"},
                    "result": {"data": "test"}
                }
            ],
            "rounds": 2,
            "model": "claude-3-opus"
        }

        service.orchestrator.answer_query = Mock(return_value=mock_result)

        result = service.process_query("test question", "bakersfield")

        assert result["answer"]["text"] == "Test answer"
        assert result["answer"]["confidence"] == 0.9  # high maps to 0.9
        assert len(result["answer"]["sources"]) == 1
        assert len(result["tool_calls"]) == 1
        assert result["rounds"] == 2
        assert result["model"] == "claude-3-opus"

    def test_confidence_mapping(self):
        """Test confidence string to float mapping."""
        service = QueryService(anthropic_api_key="test-key")

        test_cases = [
            ("low", 0.3),
            ("medium", 0.6),
            ("high", 0.9),
            ("unknown", 0.6),  # default to medium
        ]

        for confidence_str, expected_float in test_cases:
            mock_result = {
                "answer": {"text": "Test", "confidence": confidence_str},
                "tool_calls": [],
                "rounds": 1,
                "model": "test"
            }

            service.orchestrator.answer_query = Mock(return_value=mock_result)
            result = service.process_query("test", "bakersfield")

            assert result["answer"]["confidence"] == expected_float


class TestStatusService:
    """Test status service."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            parquet_path = Path(tmpdir) / "parquet"
            db = Database(db_path, parquet_path)
            db.connect()
            yield db, db_path
            db.close()

    def test_get_system_status_with_data(self, temp_db):
        """Test getting system status with available data."""
        db, db_path = temp_db
        service = StatusService(db, db_path)

        # Mock database methods
        db.get_time_range = Mock(return_value=(
            datetime(2024, 1, 1),
            datetime(2024, 1, 31)
        ))
        db.get_sensors = Mock(return_value=["sensor1", "sensor2"])

        status = service.get_system_status()

        assert status["status"] == "healthy"
        assert status["database"] == str(db_path)
        assert status["data_range"] is not None
        assert len(status["sensors"]) == 2

    def test_get_system_status_without_data(self, temp_db):
        """Test getting system status without data."""
        db, db_path = temp_db
        service = StatusService(db, db_path)

        # Mock database methods to return no data
        db.get_time_range = Mock(return_value=(None, None))
        db.get_sensors = Mock(return_value=[])

        status = service.get_system_status()

        assert status["status"] == "unhealthy"
        assert status["data_range"] is None
        assert len(status["sensors"]) == 0

    def test_health_determination(self, temp_db):
        """Test health status determination logic."""
        db, db_path = temp_db
        service = StatusService(db, db_path)

        # Test cases: (data_range, sensors, expected_status)
        test_cases = [
            ({"start": "2024-01-01", "end": "2024-01-31"}, ["sensor1"], "healthy"),
            ({"start": "2024-01-01", "end": "2024-01-31"}, [], "degraded"),
            (None, ["sensor1"], "degraded"),
            (None, [], "unhealthy"),
        ]

        for data_range, sensors, expected_status in test_cases:
            result = service._determine_health_status(data_range, sensors)
            assert result == expected_status

    def test_check_database_connectivity(self, temp_db):
        """Test database connectivity check."""
        db, db_path = temp_db
        service = StatusService(db, db_path)

        # Should succeed with real database
        assert service.check_database_connectivity() is True

        # Should fail if query raises exception
        db.query = Mock(side_effect=Exception("Connection failed"))
        assert service.check_database_connectivity() is False


class TestIngestionService:
    """Test ingestion service."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            parquet_path = Path(tmpdir) / "parquet"
            db = Database(db_path, parquet_path)
            db.connect()
            yield db
            db.close()

    @pytest.fixture
    def mock_location_config(self):
        """Create mock location configuration."""
        config = Mock(spec=LocationConfig)
        config.get_location = Mock(return_value={
            "name": "Bakersfield",
            "lat": 35.3733,
            "lon": -119.0187,
            "sensors": {
                "purpleair": ["sensor1", "sensor2"]
            }
        })
        return config

    def test_init_without_api_keys_logs_warning(self, temp_db, mock_location_config):
        """Test initialization without API keys logs warnings."""
        service = IngestionService(
            temp_db,
            mock_location_config,
            purpleair_api_key="",
            openweather_api_key="",
            default_location="bakersfield"
        )

        assert service is not None

    @pytest.mark.asyncio
    async def test_ingest_air_quality_without_api_key_raises_error(
        self, temp_db, mock_location_config
    ):
        """Test that ingesting without API key raises ConfigurationError."""
        service = IngestionService(
            temp_db,
            mock_location_config,
            purpleair_api_key="",
            openweather_api_key="test-key",
            default_location="bakersfield"
        )

        with pytest.raises(ConfigurationError) as exc_info:
            await service.ingest_air_quality()

        assert "PurpleAir API key not configured" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_ingest_weather_without_api_key_raises_error(
        self, temp_db, mock_location_config
    ):
        """Test that ingesting weather without API key raises ConfigurationError."""
        service = IngestionService(
            temp_db,
            mock_location_config,
            purpleair_api_key="test-key",
            openweather_api_key="",
            default_location="bakersfield"
        )

        with pytest.raises(ConfigurationError) as exc_info:
            await service.ingest_weather()

        assert "OpenWeather API key not configured" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_ingest_all_returns_combined_results(
        self, temp_db, mock_location_config
    ):
        """Test that ingest_all returns combined results."""
        service = IngestionService(
            temp_db,
            mock_location_config,
            purpleair_api_key="test-key",
            openweather_api_key="test-key",
            default_location="bakersfield"
        )

        # Mock the individual ingestion methods
        service.ingest_air_quality = AsyncMock(return_value={
            "status": "completed",
            "timestamp": "2024-01-01T00:00:00"
        })
        service.ingest_weather = AsyncMock(return_value={
            "status": "completed",
            "timestamp": "2024-01-01T00:00:00"
        })

        result = await service.ingest_all()

        assert result["status"] == "completed"
        assert "air_quality" in result["results"]
        assert "weather" in result["results"]
        assert result["results"]["air_quality"]["status"] == "completed"
        assert result["results"]["weather"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_ingest_all_handles_partial_failure(
        self, temp_db, mock_location_config
    ):
        """Test that ingest_all handles partial failures correctly."""
        service = IngestionService(
            temp_db,
            mock_location_config,
            purpleair_api_key="test-key",
            openweather_api_key="test-key",
            default_location="bakersfield"
        )

        # Mock AQ to succeed, weather to fail
        service.ingest_air_quality = AsyncMock(return_value={
            "status": "completed",
            "timestamp": "2024-01-01T00:00:00"
        })
        service.ingest_weather = AsyncMock(side_effect=Exception("API error"))

        result = await service.ingest_all()

        assert result["status"] == "partial"
        assert result["results"]["air_quality"]["status"] == "completed"
        assert result["results"]["weather"]["status"] == "failed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
