"""Service for system status and health checks."""
from typing import Dict, Any, List, Optional
from pathlib import Path

from storage.database import Database
from logging_config import get_logger


class StatusService:
    """Service for retrieving system status and health information."""

    def __init__(self, database: Database, database_path: Path):
        """
        Initialize status service.

        Args:
            database: Database instance
            database_path: Path to database file
        """
        self.db = database
        self.database_path = database_path
        self.logger = get_logger("services.status")

    def get_system_status(self) -> Dict[str, Any]:
        """
        Get comprehensive system status.

        Returns:
            Dictionary containing status, database info, data range, and sensors
        """
        self.logger.info("Retrieving system status")

        try:
            # Get data availability
            data_range = self._get_data_range()

            # Get available sensors
            sensors = self._get_sensors()

            # Determine overall health
            status = self._determine_health_status(data_range, sensors)

            return {
                "status": status,
                "database": str(self.database_path),
                "data_range": data_range,
                "sensors": sensors
            }

        except Exception as e:
            self.logger.error(f"Error retrieving system status: {e}")
            return {
                "status": "unhealthy",
                "database": str(self.database_path),
                "data_range": None,
                "sensors": []
            }

    def _get_data_range(self) -> Optional[Dict[str, str]]:
        """
        Get time range of available data.

        Returns:
            Dictionary with start and end timestamps, or None if no data
        """
        try:
            min_ts, max_ts = self.db.get_time_range("aq")

            if min_ts and max_ts:
                return {
                    "start": str(min_ts),
                    "end": str(max_ts)
                }

            return None

        except Exception as e:
            self.logger.warning(f"Could not retrieve data range: {e}")
            return None

    def _get_sensors(self) -> List[str]:
        """
        Get list of available sensors.

        Returns:
            List of sensor IDs
        """
        try:
            return self.db.get_sensors()
        except Exception as e:
            self.logger.warning(f"Could not retrieve sensors: {e}")
            return []

    def _determine_health_status(
        self,
        data_range: Optional[Dict[str, str]],
        sensors: List[str]
    ) -> str:
        """
        Determine overall system health.

        Args:
            data_range: Time range of available data
            sensors: List of available sensors

        Returns:
            Health status: "healthy", "degraded", or "unhealthy"
        """
        if not data_range and not sensors:
            return "unhealthy"

        if not data_range or not sensors:
            return "degraded"

        return "healthy"

    def check_database_connectivity(self) -> bool:
        """
        Check if database is accessible.

        Returns:
            True if database is accessible, False otherwise
        """
        try:
            # Simple connectivity check
            self.db.query("SELECT 1")
            return True
        except Exception as e:
            self.logger.error(f"Database connectivity check failed: {e}")
            return False
