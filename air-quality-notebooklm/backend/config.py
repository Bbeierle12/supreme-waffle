"""Configuration management using Pydantic settings."""
import os
from pathlib import Path
from typing import Dict, List
from pydantic import Field
from pydantic_settings import BaseSettings
import yaml


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Keys
    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    purpleair_api_key: str = Field(..., alias="PURPLEAIR_API_KEY")
    openweather_api_key: str = Field(default="", alias="OPENWEATHER_API_KEY")

    # Paths
    database_path: Path = Field(default=Path("../data/airquality.db"))
    parquet_path: Path = Field(default=Path("../data/parquet"))
    papers_path: Path = Field(default=Path("../data/papers"))
    config_path: Path = Field(default=Path("../config"))

    # Application
    log_level: str = Field(default="INFO")
    timezone: str = Field(default="America/Los_Angeles")
    default_location: str = Field(default="bakersfield")

    # Server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    reload: bool = Field(default=True)

    class Config:
        env_file = ".env"
        case_sensitive = False


class LocationConfig:
    """Location-specific configuration loaded from YAML."""

    def __init__(self, config_path: Path):
        self.config_path = config_path / "locations.yaml"
        self._locations = self._load_locations()

    def _load_locations(self) -> Dict:
        """Load location configurations from YAML."""
        if not self.config_path.exists():
            return {}

        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def get_location(self, location_id: str) -> Dict:
        """Get configuration for a specific location."""
        if location_id not in self._locations:
            raise ValueError(f"Location '{location_id}' not found in configuration")
        return self._locations[location_id]

    def list_locations(self) -> List[str]:
        """List all available location IDs."""
        return list(self._locations.keys())


# Global settings instance
settings = Settings()
location_config = LocationConfig(settings.config_path)
