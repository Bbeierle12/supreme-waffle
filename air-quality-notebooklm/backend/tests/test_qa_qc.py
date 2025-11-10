"""Tests for QA/QC module."""
import pytest
import numpy as np
from analytics.qa_qc import (
    correct_pm25_barkjohn,
    validate_ab_channels,
    detect_outliers_mad,
    validate_reading,
    quality_score
)
from models import QAFlags


def test_barkjohn_correction_with_humidity():
    """Test PM2.5 correction with humidity."""
    pm25_cf1 = 50.0
    humidity = 60.0

    corrected = correct_pm25_barkjohn(pm25_cf1, humidity)

    # Expected: 0.52 * 50 - 0.085 * 60 + 5.71 = 26.0 - 5.1 + 5.71 = 26.61
    assert abs(corrected - 26.61) < 0.01


def test_barkjohn_correction_without_humidity():
    """Test PM2.5 correction without humidity."""
    pm25_cf1 = 50.0

    corrected = correct_pm25_barkjohn(pm25_cf1, None)

    # Expected: 0.52 * 50 + 3.86 = 26.0 + 3.86 = 29.86
    assert abs(corrected - 29.86) < 0.01


def test_barkjohn_correction_negative():
    """Test that correction never returns negative values."""
    pm25_cf1 = 0.0
    humidity = 100.0

    corrected = correct_pm25_barkjohn(pm25_cf1, humidity)

    assert corrected >= 0.0


def test_ab_channel_validation_pass():
    """Test A/B channel validation with good agreement."""
    channel_a = 25.0
    channel_b = 26.0

    is_valid, diff = validate_ab_channels(channel_a, channel_b)

    assert is_valid is True
    assert diff == 1.0


def test_ab_channel_validation_fail():
    """Test A/B channel validation with poor agreement."""
    channel_a = 25.0
    channel_b = 50.0  # Large difference

    is_valid, diff = validate_ab_channels(channel_a, channel_b)

    assert is_valid is False
    assert diff == 25.0


def test_outlier_detection():
    """Test MAD-based outlier detection."""
    # Normal distribution with one outlier
    values = np.array([10, 11, 10.5, 11.5, 10.8, 50])  # 50 is outlier

    outliers = detect_outliers_mad(values, z_threshold=3.0)

    assert outliers[-1] is True  # Last value is outlier
    assert outliers[:-1].sum() == 0  # Others are not


def test_validate_reading():
    """Test comprehensive reading validation."""
    config = {
        "ab_diff_absolute": 5.0,
        "ab_diff_relative": 0.20,
        "high_humidity_threshold": 85.0,
        "stale_data_hours": 2.0
    }

    # Good reading
    corrected, flags, metadata = validate_reading(
        pm25_a=25.0,
        pm25_b=26.0,
        humidity=60.0,
        timestamp=1000,
        current_time=1100,  # 100 seconds = fresh
        config=config,
        historical_values=np.array([24, 25, 26, 25])
    )

    assert flags == QAFlags.NONE
    assert corrected > 0


def test_validate_reading_high_humidity():
    """Test validation with high humidity."""
    config = {
        "ab_diff_absolute": 5.0,
        "ab_diff_relative": 0.20,
        "high_humidity_threshold": 85.0,
        "stale_data_hours": 2.0
    }

    corrected, flags, metadata = validate_reading(
        pm25_a=25.0,
        pm25_b=26.0,
        humidity=90.0,  # High humidity
        timestamp=1000,
        current_time=1100,
        config=config
    )

    assert flags & QAFlags.HIGH_HUMIDITY


def test_validate_reading_stale():
    """Test validation with stale data."""
    config = {
        "ab_diff_absolute": 5.0,
        "ab_diff_relative": 0.20,
        "high_humidity_threshold": 85.0,
        "stale_data_hours": 2.0
    }

    corrected, flags, metadata = validate_reading(
        pm25_a=25.0,
        pm25_b=26.0,
        humidity=60.0,
        timestamp=1000,
        current_time=11000,  # 10000 seconds = stale
        config=config
    )

    assert flags & QAFlags.STALE_DATA


def test_quality_score():
    """Test quality score calculation."""
    # Perfect quality
    score = quality_score(QAFlags.NONE)
    assert score == 1.0

    # Single flag
    score = quality_score(QAFlags.HIGH_HUMIDITY)
    assert score == 0.9

    # Multiple flags
    score = quality_score(QAFlags.AB_MISMATCH | QAFlags.OUTLIER)
    assert score == 0.5  # 0.2 + 0.3 penalty

    # Offline sensor
    score = quality_score(QAFlags.SENSOR_OFFLINE)
    assert score == 0.0
