"""QA/QC module for air quality data validation and correction."""
import numpy as np
from typing import Dict, Optional, List, Tuple
from scipy import stats
from models import QAFlags


def correct_pm25_barkjohn(pm25_cf1: float, humidity: Optional[float] = None) -> float:
    """
    Apply EPA-recommended Barkjohn correction to PurpleAir PM2.5.

    Reference: Barkjohn et al. (2021)
    "Development and Application of a United States-wide correction for PM2.5 data
    collected with the PurpleAir sensor"

    Args:
        pm25_cf1: PM2.5 reading from CF=1 channel
        humidity: Relative humidity (0-100)

    Returns:
        Corrected PM2.5 value in µg/m³
    """
    if humidity is not None and 0 <= humidity <= 100:
        # Full correction with humidity
        pm25_corrected = 0.52 * pm25_cf1 - 0.085 * humidity + 5.71
    else:
        # Simplified correction without humidity
        pm25_corrected = 0.52 * pm25_cf1 + 3.86

    # Ensure non-negative
    return max(0.0, pm25_corrected)


def validate_ab_channels(
    channel_a: float,
    channel_b: float,
    abs_threshold: float = 5.0,
    rel_threshold: float = 0.20
) -> Tuple[bool, float]:
    """
    Validate PurpleAir A/B channel agreement.

    Args:
        channel_a: PM2.5 from channel A
        channel_b: PM2.5 from channel B
        abs_threshold: Absolute difference threshold (µg/m³)
        rel_threshold: Relative difference threshold (fraction)

    Returns:
        (is_valid, difference): Whether channels agree and the difference
    """
    mean_value = (channel_a + channel_b) / 2
    abs_diff = abs(channel_a - channel_b)

    # Check both absolute and relative thresholds
    abs_check = abs_diff <= abs_threshold
    rel_check = abs_diff <= (rel_threshold * mean_value) if mean_value > 0 else True

    is_valid = abs_check or rel_check
    return is_valid, abs_diff


def detect_outliers_mad(
    values: np.ndarray,
    z_threshold: float = 4.0
) -> np.ndarray:
    """
    Detect outliers using Median Absolute Deviation (MAD).

    MAD is more robust than standard deviation for detecting outliers.

    Args:
        values: Array of values
        z_threshold: Z-score threshold (default 4.0 for conservative detection)

    Returns:
        Boolean array where True indicates outlier
    """
    if len(values) < 3:
        return np.zeros(len(values), dtype=bool)

    median = np.median(values)
    mad = np.median(np.abs(values - median))

    # Modified z-score using MAD
    # MAD * 1.4826 approximates standard deviation for normal distribution
    if mad == 0:
        return np.zeros(len(values), dtype=bool)

    modified_z_scores = 0.6745 * (values - median) / mad
    return np.abs(modified_z_scores) > z_threshold


def validate_reading(
    pm25_a: float,
    pm25_b: float,
    humidity: Optional[float],
    timestamp: float,
    current_time: float,
    config: Dict,
    historical_values: Optional[np.ndarray] = None
) -> Tuple[float, int, Dict]:
    """
    Comprehensive validation and correction of a PurpleAir reading.

    Args:
        pm25_a: Channel A raw value
        pm25_b: Channel B raw value
        humidity: Relative humidity (%)
        timestamp: Reading timestamp (Unix)
        current_time: Current time (Unix)
        config: QA rules from location configuration
        historical_values: Recent historical values for outlier detection

    Returns:
        (corrected_value, qa_flags, metadata)
    """
    qa_flags = QAFlags.NONE
    metadata = {}

    # Average the two channels
    pm25_raw = (pm25_a + pm25_b) / 2

    # Check A/B agreement
    ab_valid, ab_diff = validate_ab_channels(
        pm25_a, pm25_b,
        config.get("ab_diff_absolute", 5.0),
        config.get("ab_diff_relative", 0.20)
    )
    if not ab_valid:
        qa_flags |= QAFlags.AB_MISMATCH
        metadata["ab_difference"] = ab_diff

    # Check humidity
    if humidity is not None and humidity > config.get("high_humidity_threshold", 85.0):
        if humidity > 85.0:  # High humidity flag even with correction
            qa_flags |= QAFlags.HIGH_HUMIDITY
            metadata["humidity"] = humidity

    # Apply correction
    pm25_corrected = correct_pm25_barkjohn(pm25_raw, humidity)
    metadata["correction_method"] = "barkjohn"
    metadata["humidity_used"] = humidity is not None

    # Check for outliers using historical data
    if historical_values is not None and len(historical_values) > 5:
        values_with_current = np.append(historical_values, pm25_corrected)
        outliers = detect_outliers_mad(
            values_with_current,
            config.get("spike_threshold", 4.0)
        )
        if outliers[-1]:  # Current value is outlier
            qa_flags |= QAFlags.OUTLIER
            metadata["outlier_z_score"] = "exceeds_threshold"

    # Check data staleness
    age_hours = (current_time - timestamp) / 3600
    if age_hours > config.get("stale_data_hours", 2.0):
        qa_flags |= QAFlags.STALE_DATA
        metadata["data_age_hours"] = age_hours

    return pm25_corrected, int(qa_flags), metadata


def calculate_rolling_statistics(
    timestamps: np.ndarray,
    values: np.ndarray,
    window_hours: float = 1.0
) -> Dict[str, np.ndarray]:
    """
    Calculate rolling statistics for time series data.

    Args:
        timestamps: Unix timestamps
        values: Corresponding values
        window_hours: Rolling window size in hours

    Returns:
        Dictionary with rolling mean, median, std, min, max
    """
    import pandas as pd

    # Convert to pandas for easy rolling operations
    df = pd.DataFrame({
        'timestamp': pd.to_datetime(timestamps, unit='s'),
        'value': values
    }).set_index('timestamp')

    window_str = f"{int(window_hours)}H"
    rolling = df['value'].rolling(window=window_str, min_periods=1)

    return {
        'mean': rolling.mean().values,
        'median': rolling.median().values,
        'std': rolling.std().values,
        'min': rolling.min().values,
        'max': rolling.max().values,
        'count': rolling.count().values
    }


def quality_score(qa_flags: int) -> float:
    """
    Calculate quality score from QA flags.

    Returns:
        Score from 0.0 (poor) to 1.0 (excellent)
    """
    penalties = {
        QAFlags.AB_MISMATCH: 0.2,
        QAFlags.HIGH_HUMIDITY: 0.1,
        QAFlags.OUTLIER: 0.3,
        QAFlags.STALE_DATA: 0.2,
        QAFlags.SENSOR_OFFLINE: 1.0,
        QAFlags.MAINTENANCE: 0.5
    }

    total_penalty = 0.0
    for flag, penalty in penalties.items():
        if qa_flags & flag:
            total_penalty += penalty

    return max(0.0, 1.0 - total_penalty)


def summarize_qa_flags(qa_flags: int) -> List[str]:
    """
    Convert QA flags to human-readable list.

    Args:
        qa_flags: Integer bit mask

    Returns:
        List of flag descriptions
    """
    descriptions = []

    if qa_flags & QAFlags.AB_MISMATCH:
        descriptions.append("A/B channel disagreement")
    if qa_flags & QAFlags.HIGH_HUMIDITY:
        descriptions.append("High humidity (>85%)")
    if qa_flags & QAFlags.OUTLIER:
        descriptions.append("Statistical outlier")
    if qa_flags & QAFlags.STALE_DATA:
        descriptions.append("Stale data (>2 hours)")
    if qa_flags & QAFlags.SENSOR_OFFLINE:
        descriptions.append("Sensor offline")
    if qa_flags & QAFlags.MAINTENANCE:
        descriptions.append("Maintenance period")

    if not descriptions:
        descriptions.append("No issues")

    return descriptions
