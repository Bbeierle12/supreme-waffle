"""PurpleAir API client and data ingestion."""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import httpx
import pandas as pd
import numpy as np
from analytics.qa_qc import validate_reading, correct_pm25_barkjohn
from models import AirQualityObservation


class PurpleAirClient:
    """Client for PurpleAir API with QA/QC."""

    BASE_URL = "https://api.purpleair.com/v1"

    def __init__(self, api_key: str):
        """
        Initialize PurpleAir client.

        Args:
            api_key: PurpleAir API key
        """
        self.api_key = api_key
        self.headers = {"X-API-Key": api_key}

    async def get_sensor_data(
        self,
        sensor_ids: List[int],
        fields: Optional[List[str]] = None,
        average: int = 10  # minutes
    ) -> List[Dict]:
        """
        Get current data from multiple sensors.

        Args:
            sensor_ids: List of sensor IDs
            fields: Fields to retrieve
            average: Averaging period in minutes (0, 10, 30, 60)

        Returns:
            List of sensor data dictionaries
        """
        if fields is None:
            fields = [
                "pm2.5_cf_1",
                "pm2.5_cf_1_a",
                "pm2.5_cf_1_b",
                "pm10.0_cf_1",
                "humidity",
                "temperature",
                "pressure",
                "latitude",
                "longitude",
                "last_seen"
            ]

        results = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for sensor_id in sensor_ids:
                try:
                    response = await client.get(
                        f"{self.BASE_URL}/sensors/{sensor_id}",
                        headers=self.headers,
                        params={
                            "fields": ",".join(fields),
                            "average": average
                        }
                    )
                    response.raise_for_status()
                    data = response.json()

                    if "sensor" in data:
                        results.append(data["sensor"])

                except httpx.HTTPError as e:
                    print(f"Error fetching sensor {sensor_id}: {e}")
                    continue

                # Rate limiting: PurpleAir allows ~1 request per second
                await asyncio.sleep(1.1)

        return results

    async def get_sensor_history(
        self,
        sensor_id: int,
        start_timestamp: int,
        end_timestamp: int,
        average: int = 60,
        fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Get historical data for a sensor.

        Args:
            sensor_id: Sensor ID
            start_timestamp: Start time (Unix timestamp)
            end_timestamp: End time (Unix timestamp)
            average: Averaging period in minutes
            fields: Fields to retrieve

        Returns:
            DataFrame with historical data
        """
        if fields is None:
            fields = [
                "pm2.5_cf_1",
                "pm2.5_cf_1_a",
                "pm2.5_cf_1_b",
                "pm10.0_cf_1",
                "humidity"
            ]

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/sensors/{sensor_id}/history",
                headers=self.headers,
                params={
                    "start_timestamp": start_timestamp,
                    "end_timestamp": end_timestamp,
                    "average": average,
                    "fields": ",".join(fields)
                }
            )
            response.raise_for_status()
            data = response.json()

        # Convert to DataFrame
        if "data" in data and data["data"]:
            df = pd.DataFrame(data["data"], columns=data["fields"])
            df["sensor_id"] = sensor_id
            return df

        return pd.DataFrame()

    def process_sensor_data(
        self,
        raw_data: List[Dict],
        location_config: Dict,
        current_time: Optional[float] = None
    ) -> pd.DataFrame:
        """
        Process raw sensor data with QA/QC.

        Args:
            raw_data: Raw sensor data from API
            location_config: Location configuration with QA rules
            current_time: Current timestamp for staleness check

        Returns:
            DataFrame with processed observations
        """
        if current_time is None:
            current_time = datetime.now().timestamp()

        observations = []

        for sensor in raw_data:
            try:
                # Extract raw values
                pm25_a = sensor.get("pm2.5_cf_1_a")
                pm25_b = sensor.get("pm2.5_cf_1_b")
                humidity = sensor.get("humidity")
                timestamp = sensor.get("last_seen", current_time)

                if pm25_a is None or pm25_b is None:
                    continue

                # Get historical values for outlier detection (if available)
                # In real implementation, would query from database
                historical_values = None

                # Validate and correct
                pm25_corrected, qa_flags, metadata = validate_reading(
                    pm25_a=pm25_a,
                    pm25_b=pm25_b,
                    humidity=humidity,
                    timestamp=timestamp,
                    current_time=current_time,
                    config=location_config.get("qa_rules", {}),
                    historical_values=historical_values
                )

                # Create observation
                obs = {
                    "ts": datetime.fromtimestamp(timestamp),
                    "source": "purpleair",
                    "sensor_id": str(sensor.get("sensor_index", "unknown")),
                    "pm25_raw": (pm25_a + pm25_b) / 2,
                    "pm25_corr": pm25_corrected,
                    "pm10_raw": sensor.get("pm10.0_cf_1"),
                    "qa_flags": qa_flags,
                    "window": "10m",  # Based on API average parameter
                    "lat": sensor.get("latitude", 0.0),
                    "lon": sensor.get("longitude", 0.0),
                    "metadata": metadata
                }

                observations.append(obs)

            except Exception as e:
                print(f"Error processing sensor data: {e}")
                continue

        return pd.DataFrame(observations)


async def fetch_and_store(
    api_key: str,
    sensor_ids: List[int],
    location_config: Dict,
    db
):
    """
    Fetch latest data from PurpleAir and store in database.

    Args:
        api_key: PurpleAir API key
        sensor_ids: List of sensor IDs to fetch
        location_config: Location configuration
        db: Database instance
    """
    client = PurpleAirClient(api_key)

    # Fetch current data
    raw_data = await client.get_sensor_data(sensor_ids)

    if not raw_data:
        print("No data fetched from PurpleAir")
        return

    # Process with QA/QC
    df = client.process_sensor_data(raw_data, location_config)

    if df.empty:
        print("No valid observations after QA/QC")
        return

    # Store in database
    db.write_parquet(df, data_type="aq")

    print(f"Stored {len(df)} observations from {len(raw_data)} sensors")

    # Store lineage
    for sensor in raw_data:
        lineage = {
            "record_id": f"purpleair_{sensor.get('sensor_index')}_{datetime.now().isoformat()}",
            "table_name": "observations_aq",
            "raw_payload": sensor,
            "fetched_at": datetime.now(),
            "api_source": "purpleair_v1",
            "api_version": "1.0"
        }
        # Would insert into lineage table


async def backfill_historical(
    api_key: str,
    sensor_ids: List[int],
    start_date: datetime,
    end_date: datetime,
    location_config: Dict,
    db
):
    """
    Backfill historical data from PurpleAir.

    Args:
        api_key: PurpleAir API key
        sensor_ids: List of sensor IDs
        start_date: Start date for backfill
        end_date: End date for backfill
        location_config: Location configuration
        db: Database instance
    """
    client = PurpleAirClient(api_key)

    # Process in daily chunks to avoid overwhelming API
    current_date = start_date
    while current_date < end_date:
        next_date = min(current_date + timedelta(days=1), end_date)

        start_ts = int(current_date.timestamp())
        end_ts = int(next_date.timestamp())

        print(f"Backfilling {current_date.date()} to {next_date.date()}")

        for sensor_id in sensor_ids:
            try:
                df = await client.get_sensor_history(
                    sensor_id,
                    start_ts,
                    end_ts,
                    average=60  # 1-hour averages
                )

                if not df.empty:
                    # Process and store
                    # Would need to adapt process_sensor_data for historical format
                    db.write_parquet(df, data_type="aq")
                    print(f"  Stored {len(df)} records for sensor {sensor_id}")

            except Exception as e:
                print(f"  Error backfilling sensor {sensor_id}: {e}")

            await asyncio.sleep(1.5)  # Rate limiting

        current_date = next_date
