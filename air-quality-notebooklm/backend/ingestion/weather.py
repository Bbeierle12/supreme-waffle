"""Weather data ingestion from OpenWeather API."""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional
import httpx
import pandas as pd
import numpy as np


class WeatherClient:
    """Client for OpenWeather API."""

    BASE_URL = "https://api.openweathermap.org/data/2.5"

    def __init__(self, api_key: str):
        """
        Initialize weather client.

        Args:
            api_key: OpenWeather API key
        """
        self.api_key = api_key

    async def get_current_weather(
        self,
        lat: float,
        lon: float
    ) -> Optional[Dict]:
        """
        Get current weather for location.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Weather data dictionary
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    f"{self.BASE_URL}/weather",
                    params={
                        "lat": lat,
                        "lon": lon,
                        "appid": self.api_key,
                        "units": "metric"
                    }
                )
                response.raise_for_status()
                return response.json()

            except httpx.HTTPError as e:
                print(f"Error fetching weather: {e}")
                return None

    def calculate_stability_index(
        self,
        temp_c: float,
        wind_speed_ms: float,
        cloud_cover: float
    ) -> float:
        """
        Calculate a simple atmospheric stability index.

        This is a proxy in absence of vertical profile data.
        Higher values indicate more stable (inversion-prone) conditions.

        Args:
            temp_c: Temperature in Celsius
            wind_speed_ms: Wind speed in m/s
            cloud_cover: Cloud cover fraction (0-1)

        Returns:
            Stability index (0-1, higher = more stable)
        """
        # Low wind contributes to stability
        wind_factor = max(0, 1 - (wind_speed_ms / 10.0))

        # Clear skies at night favor inversions (radiative cooling)
        # This would need time-of-day info for better accuracy
        cloud_factor = 1 - cloud_cover

        # Simple weighted average
        stability = 0.6 * wind_factor + 0.4 * cloud_factor

        return np.clip(stability, 0.0, 1.0)

    def process_weather_data(
        self,
        raw_data: Dict,
        station_id: str = "openweather"
    ) -> Optional[Dict]:
        """
        Process raw weather data into standard format.

        Args:
            raw_data: Raw weather data from API
            station_id: Station identifier

        Returns:
            Processed weather observation
        """
        if not raw_data:
            return None

        try:
            main = raw_data.get("main", {})
            wind = raw_data.get("wind", {})
            clouds = raw_data.get("clouds", {})
            coord = raw_data.get("coord", {})

            temp_c = main.get("temp")
            rh = main.get("humidity")
            wind_speed_ms = wind.get("speed", 0)
            wind_dir_deg = wind.get("deg", 0)
            pressure_mb = main.get("pressure")
            cloud_cover = clouds.get("all", 0) / 100.0

            # Calculate stability proxy
            stability_idx = self.calculate_stability_index(
                temp_c, wind_speed_ms, cloud_cover
            )

            obs = {
                "ts": datetime.fromtimestamp(raw_data.get("dt")),
                "station_id": station_id,
                "temp_c": temp_c,
                "rh": rh,
                "wind_speed_ms": wind_speed_ms,
                "wind_dir_deg": wind_dir_deg,
                "pressure_mb": pressure_mb,
                "stability_idx": stability_idx,
                "mixing_height_m": None,  # Not available from API
                "window": "10m",
                "lat": coord.get("lat", 0),
                "lon": coord.get("lon", 0)
            }

            return obs

        except Exception as e:
            print(f"Error processing weather data: {e}")
            return None


async def fetch_and_store_weather(
    api_key: str,
    location_config: Dict,
    db
):
    """
    Fetch current weather and store in database.

    Args:
        api_key: OpenWeather API key
        location_config: Location configuration
        db: Database instance
    """
    client = WeatherClient(api_key)

    # Get center point of location bounds
    bounds = location_config.get("bounds", {})
    lat_range = bounds.get("lat", [0, 0])
    lon_range = bounds.get("lon", [0, 0])

    center_lat = (lat_range[0] + lat_range[1]) / 2
    center_lon = (lon_range[0] + lon_range[1]) / 2

    # Fetch weather
    raw_data = await client.get_current_weather(center_lat, center_lon)

    if not raw_data:
        print("No weather data fetched")
        return

    # Process
    obs = client.process_weather_data(
        raw_data,
        station_id=f"openweather_{location_config['name']}"
    )

    if not obs:
        print("Failed to process weather data")
        return

    # Store
    df = pd.DataFrame([obs])
    db.write_parquet(df, data_type="met")

    print(f"Stored weather observation for {location_config['name']}")


def detect_evening_cooling(
    temps: pd.Series,
    timestamps: pd.Series
) -> float:
    """
    Detect temperature drop from afternoon to evening.

    This is an indicator of potential inversion formation.

    Args:
        temps: Temperature time series
        timestamps: Corresponding timestamps

    Returns:
        Temperature drop in Celsius
    """
    df = pd.DataFrame({"ts": timestamps, "temp": temps})
    df["hour"] = pd.to_datetime(df["ts"]).dt.hour

    # Get afternoon (15:00) and evening (20:00) temperatures
    afternoon = df[df["hour"] == 15]["temp"]
    evening = df[df["hour"] == 20]["temp"]

    if afternoon.empty or evening.empty:
        return 0.0

    return afternoon.mean() - evening.mean()
