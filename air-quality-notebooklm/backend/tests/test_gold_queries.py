"""Gold standard query tests."""
import pytest
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from storage.database import Database
from analytics import primitives
from pathlib import Path
import tempfile


@pytest.fixture
def test_db():
    """Create a test database with sample data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        parquet_path = Path(tmpdir) / "parquet"

        db = Database(db_path, parquet_path)
        db.connect()

        # Insert sample air quality data
        base_time = datetime(2024, 11, 8, 0, 0, 0)
        aq_data = []

        for i in range(24 * 6):  # 24 hours, 10-minute intervals
            ts = base_time + timedelta(minutes=i * 10)

            # Simulate daily pattern with spike
            hour = ts.hour
            base_pm = 20 + 10 * np.sin(2 * np.pi * hour / 24)

            # Add spike at 19:00
            if hour == 19:
                base_pm = 47.3

            aq_data.append({
                "ts": ts,
                "source": "purpleair",
                "sensor_id": "test_sensor_1",
                "pm25_raw": base_pm * 1.1,
                "pm25_corr": base_pm,
                "pm10_raw": base_pm * 1.5,
                "qa_flags": 0,
                "window": "10m",
                "lat": 35.35,
                "lon": -119.0
            })

        aq_df = pd.DataFrame(aq_data)
        db.write_parquet(aq_df, data_type="aq")

        # Insert sample weather data
        met_data = []
        for i in range(24):
            ts = base_time + timedelta(hours=i)

            # Simulate evening cooling
            temp_c = 25 - 5 * np.sin(2 * np.pi * (i - 6) / 24)
            wind_speed = 1.5 if i >= 17 else 3.0  # Low wind in evening

            met_data.append({
                "ts": ts,
                "station_id": "test_station",
                "temp_c": temp_c,
                "rh": 55.0,
                "wind_speed_ms": wind_speed,
                "wind_dir_deg": 180.0,
                "pressure_mb": 1013.0,
                "stability_idx": 0.6 if i >= 17 else 0.2,
                "mixing_height_m": None,
                "window": "1h",
                "lat": 35.35,
                "lon": -119.0
            })

        met_df = pd.DataFrame(met_data)
        db.write_parquet(met_df, data_type="met")

        yield db

        db.close()


def test_gold_query_max_pm25(test_db):
    """Test: What was the max PM2.5 on 2024-11-08?"""
    start = datetime(2024, 11, 8, 0, 0, 0)
    end = datetime(2024, 11, 9, 0, 0, 0)

    result = test_db.query("""
        SELECT MAX(pm25_corr) as max_pm25
        FROM observations_aq
        WHERE ts BETWEEN ? AND ?
    """, {"start": start, "end": end})

    assert not result.empty
    max_pm25 = result.iloc[0]["max_pm25"]

    # Should be close to 47.3 (the spike we inserted)
    assert abs(max_pm25 - 47.3) < 1.0


def test_gold_query_exceedances(test_db):
    """Test: How many hours exceeded EPA standards?"""
    start = datetime(2024, 11, 8, 0, 0, 0)
    end = datetime(2024, 11, 9, 0, 0, 0)

    df = primitives.detect_exceedances(
        test_db,
        threshold=35.0,
        window="1h",
        start=start,
        end=end
    )

    # Should have at least one exceedance (the spike hour)
    assert len(df) > 0


def test_gold_query_24h_average(test_db):
    """Test: What was the 24-hour average?"""
    start = datetime(2024, 11, 8, 0, 0, 0)
    end = datetime(2024, 11, 9, 0, 0, 0)

    result = test_db.query("""
        SELECT AVG(pm25_corr) as avg_pm25
        FROM observations_aq
        WHERE ts BETWEEN ? AND ?
    """, {"start": start, "end": end})

    assert not result.empty
    avg_pm25 = result.iloc[0]["avg_pm25"]

    # Should be between 20-30 (base pattern is ~20-30)
    assert 15 < avg_pm25 < 35


def test_gold_query_nonexistent_sensor(test_db):
    """Test: Analyze data for sensor that doesn't exist"""
    result = test_db.query("""
        SELECT COUNT(*) as count
        FROM observations_aq
        WHERE sensor_id = 'nonexistent_sensor'
    """)

    assert result.iloc[0]["count"] == 0


def test_gold_query_future_dates(test_db):
    """Test: Compare future dates (should return no data)"""
    start = datetime(2025, 1, 1, 0, 0, 0)
    end = datetime(2025, 1, 2, 0, 0, 0)

    result = test_db.query("""
        SELECT COUNT(*) as count
        FROM observations_aq
        WHERE ts BETWEEN ? AND ?
    """, {"start": start, "end": end})

    assert result.iloc[0]["count"] == 0


def test_correlation_with_controls(test_db):
    """Test: Is there a correlation between wind and PM2.5?"""
    start = datetime(2024, 11, 8, 0, 0, 0)
    end = datetime(2024, 11, 9, 0, 0, 0)

    result = primitives.correlate(
        test_db,
        x_metric="pm25_corr",
        y_metric="wind_speed_ms",
        method="spearman",
        controls=["hour"],
        start=start,
        end=end
    )

    # Should return valid correlation result
    assert result is not None
    assert "correlation" in result
    assert "p_value" in result
    assert "n_samples" in result


def test_inversion_detection(test_db):
    """Test: Detect inversions"""
    start = datetime(2024, 11, 8, 0, 0, 0)
    end = datetime(2024, 11, 9, 0, 0, 0)

    inversions = primitives.infer_inversion(
        test_db,
        min_confidence=0.5,
        start=start,
        end=end
    )

    # Should be a list (may be empty or have detected inversions)
    assert isinstance(inversions, list)


# Integration test for full query workflow
def test_full_query_workflow(test_db):
    """Test complete workflow from query to answer."""
    from llm.tools import execute_tool
    from models import GetMetricSummary

    # Test get_metric_summary tool
    params = {
        "metric": "pm25_corr",
        "window": "1h",
        "start": datetime(2024, 11, 8, 0, 0, 0),
        "end": datetime(2024, 11, 9, 0, 0, 0),
        "location": "bakersfield",
        "aggregate": "max"
    }

    result = execute_tool("get_metric_summary", params)

    assert result["success"] is True
    assert "result" in result
    assert result["result"]["value"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
