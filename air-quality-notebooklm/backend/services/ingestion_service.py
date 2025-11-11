"""Service for data ingestion operations."""
from typing import Dict, Any
from datetime import datetime

from storage.database import Database
from config import LocationConfig
from ingestion.purpleair import fetch_and_store
from ingestion.weather import fetch_and_store_weather
from exceptions import ExternalAPIError, DatabaseError, ConfigurationError
from logging_config import get_logger


class IngestionService:
    """Service for coordinating data ingestion from external APIs."""

    def __init__(
        self,
        database: Database,
        location_config: LocationConfig,
        purpleair_api_key: str,
        openweather_api_key: str,
        default_location: str
    ):
        """
        Initialize ingestion service.

        Args:
            database: Database instance
            location_config: Location configuration
            purpleair_api_key: PurpleAir API key
            openweather_api_key: OpenWeather API key
            default_location: Default location identifier

        Raises:
            ConfigurationError: If required configuration is missing
        """
        self.db = database
        self.location_config = location_config
        self.purpleair_api_key = purpleair_api_key
        self.openweather_api_key = openweather_api_key
        self.default_location = default_location
        self.logger = get_logger("services.ingestion")

        # Validate configuration
        if not purpleair_api_key:
            self.logger.warning("PurpleAir API key not configured")

        if not openweather_api_key:
            self.logger.warning("OpenWeather API key not configured")

    async def ingest_air_quality(self, location_id: str = None) -> Dict[str, Any]:
        """
        Ingest air quality data from PurpleAir.

        Args:
            location_id: Optional location ID (defaults to default_location)

        Returns:
            Dictionary with ingestion results

        Raises:
            ConfigurationError: If API key is not configured
            ExternalAPIError: If API request fails
            DatabaseError: If database write fails
        """
        if not self.purpleair_api_key:
            raise ConfigurationError(
                "PurpleAir API key not configured",
                details={"setting": "PURPLEAIR_API_KEY"}
            )

        location_id = location_id or self.default_location

        try:
            self.logger.info(f"Starting air quality ingestion for {location_id}")

            location = self.location_config.get_location(location_id)
            sensor_ids = location["sensors"]["purpleair"]

            await fetch_and_store(
                self.purpleair_api_key,
                sensor_ids,
                location,
                self.db
            )

            self.logger.info(f"Successfully ingested air quality data at {datetime.now()}")

            return {
                "status": "completed",
                "location": location_id,
                "sensor_count": len(sensor_ids),
                "timestamp": datetime.now().isoformat()
            }

        except KeyError as e:
            error_msg = f"Configuration error: Missing key {e}"
            self.logger.error(error_msg)
            raise ConfigurationError(error_msg, details={"key": str(e)})

        except ExternalAPIError as e:
            self.logger.error(f"PurpleAir API error: {e.message}", extra={"details": e.details})
            raise

        except DatabaseError as e:
            self.logger.error(f"Database error during air quality ingestion: {e.message}")
            raise

        except Exception as e:
            self.logger.exception(f"Unexpected error during air quality ingestion: {e}")
            raise DatabaseError(
                "Failed to ingest air quality data",
                details={"error": str(e)}
            )

    async def ingest_weather(self, location_id: str = None) -> Dict[str, Any]:
        """
        Ingest weather data from OpenWeather.

        Args:
            location_id: Optional location ID (defaults to default_location)

        Returns:
            Dictionary with ingestion results

        Raises:
            ConfigurationError: If API key is not configured
            ExternalAPIError: If API request fails
            DatabaseError: If database write fails
        """
        if not self.openweather_api_key:
            raise ConfigurationError(
                "OpenWeather API key not configured",
                details={"setting": "OPENWEATHER_API_KEY"}
            )

        location_id = location_id or self.default_location

        try:
            self.logger.info(f"Starting weather ingestion for {location_id}")

            location = self.location_config.get_location(location_id)

            await fetch_and_store_weather(
                self.openweather_api_key,
                location,
                self.db
            )

            self.logger.info(f"Successfully ingested weather data at {datetime.now()}")

            return {
                "status": "completed",
                "location": location_id,
                "timestamp": datetime.now().isoformat()
            }

        except KeyError as e:
            error_msg = f"Configuration error: Missing key {e}"
            self.logger.error(error_msg)
            raise ConfigurationError(error_msg, details={"key": str(e)})

        except ExternalAPIError as e:
            self.logger.error(f"Weather API error: {e.message}", extra={"details": e.details})
            raise

        except DatabaseError as e:
            self.logger.error(f"Database error during weather ingestion: {e.message}")
            raise

        except Exception as e:
            self.logger.exception(f"Unexpected error during weather ingestion: {e}")
            raise DatabaseError(
                "Failed to ingest weather data",
                details={"error": str(e)}
            )

    async def ingest_all(self, location_id: str = None) -> Dict[str, Any]:
        """
        Ingest both air quality and weather data.

        Args:
            location_id: Optional location ID (defaults to default_location)

        Returns:
            Dictionary with combined ingestion results
        """
        location_id = location_id or self.default_location

        self.logger.info(f"Starting full data ingestion for {location_id}")

        results = {
            "air_quality": None,
            "weather": None
        }

        # Ingest air quality
        try:
            aq_result = await self.ingest_air_quality(location_id)
            results["air_quality"] = aq_result
        except Exception as e:
            self.logger.error(f"Air quality ingestion failed: {e}")
            results["air_quality"] = {"status": "failed", "error": str(e)}

        # Ingest weather
        try:
            weather_result = await self.ingest_weather(location_id)
            results["weather"] = weather_result
        except Exception as e:
            self.logger.error(f"Weather ingestion failed: {e}")
            results["weather"] = {"status": "failed", "error": str(e)}

        # Determine overall status
        aq_success = results["air_quality"] and results["air_quality"].get("status") == "completed"
        weather_success = results["weather"] and results["weather"].get("status") == "completed"

        if aq_success and weather_success:
            overall_status = "completed"
        elif aq_success or weather_success:
            overall_status = "partial"
        else:
            overall_status = "failed"

        self.logger.info(f"Full ingestion completed with status: {overall_status}")

        return {
            "status": overall_status,
            "location": location_id,
            "timestamp": datetime.now().isoformat(),
            "results": results
        }
