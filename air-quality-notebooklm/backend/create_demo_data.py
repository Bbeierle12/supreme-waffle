"""Demo data loader for preview mode."""
import pandas as pd
from datetime import datetime, timedelta
import numpy as np
from pathlib import Path


def create_demo_data():
    """Create sample data for preview."""
    print("Creating demo data...")

    # Create data directory if it doesn't exist
    data_dir = Path("/home/user/supreme-waffle/air-quality-notebooklm/data/parquet/aq")
    data_dir.mkdir(parents=True, exist_ok=True)

    # Generate 7 days of sample data
    base_time = datetime.now() - timedelta(days=7)
    aq_data = []

    for i in range(7 * 24 * 6):  # 7 days, 10-minute intervals
        ts = base_time + timedelta(minutes=i * 10)
        hour = ts.hour

        # Simulate daily pattern
        base_pm = 20 + 15 * np.sin(2 * np.pi * hour / 24)

        # Add some spikes
        if hour in [8, 18] and np.random.random() > 0.7:
            base_pm += np.random.uniform(20, 40)

        # Add noise
        base_pm += np.random.normal(0, 3)
        base_pm = max(0, base_pm)

        aq_data.append({
            "ts": ts,
            "source": "purpleair",
            "sensor_id": "demo_sensor_1",
            "pm25_raw": base_pm * 1.1,
            "pm25_corr": base_pm,
            "pm10_raw": base_pm * 1.5,
            "qa_flags": 0,
            "window": "10m",
            "lat": 35.35,
            "lon": -119.0,
            "date": ts.date()
        })

    df = pd.DataFrame(aq_data)

    # Write to parquet partitioned by date
    for date, group in df.groupby("date"):
        partition_dir = data_dir / f"date={date}"
        partition_dir.mkdir(parents=True, exist_ok=True)

        output_file = partition_dir / "demo_data.parquet"
        group.drop("date", axis=1).to_parquet(
            output_file,
            engine='pyarrow',
            compression='snappy',
            index=False
        )

    print(f"Created {len(df)} demo observations")

    # Create demo weather data
    met_dir = Path("/home/user/supreme-waffle/air-quality-notebooklm/data/parquet/met")
    met_dir.mkdir(parents=True, exist_ok=True)

    met_data = []
    for i in range(7 * 24):  # 7 days, hourly
        ts = base_time + timedelta(hours=i)
        hour = ts.hour

        temp_c = 20 + 8 * np.sin(2 * np.pi * (hour - 6) / 24)
        wind_speed = 1.5 if 18 <= hour <= 23 else 3.5

        met_data.append({
            "ts": ts,
            "station_id": "demo_station",
            "temp_c": temp_c,
            "rh": 55.0 + np.random.normal(0, 5),
            "wind_speed_ms": wind_speed + np.random.normal(0, 0.5),
            "wind_dir_deg": 180.0,
            "pressure_mb": 1013.0,
            "stability_idx": 0.6 if 18 <= hour <= 23 else 0.2,
            "mixing_height_m": None,
            "window": "1h",
            "lat": 35.35,
            "lon": -119.0,
            "date": ts.date()
        })

    met_df = pd.DataFrame(met_data)

    for date, group in met_df.groupby("date"):
        partition_dir = met_dir / f"date={date}"
        partition_dir.mkdir(parents=True, exist_ok=True)

        output_file = partition_dir / "demo_data.parquet"
        group.drop("date", axis=1).to_parquet(
            output_file,
            engine='pyarrow',
            compression='snappy',
            index=False
        )

    print(f"Created {len(met_df)} demo weather observations")
    print("Demo data ready!")


if __name__ == "__main__":
    create_demo_data()
