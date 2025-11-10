"""Core analytics primitives exposed as safe LLM tools."""
from datetime import datetime
from typing import List, Dict, Any, Optional, Literal
import pandas as pd
import numpy as np
from scipy import stats
from scipy.stats import spearmanr, pearsonr, mannwhitneyu
import statsmodels.api as sm
from statsmodels.formula.api import ols


def time_series(
    db,
    metric: str,
    sensor_ids: List[str],
    start: datetime,
    end: datetime,
    window: str = "1h",
    agg: str = "mean"
) -> pd.DataFrame:
    """
    Get resampled time series with QA flags.

    Args:
        db: Database instance
        metric: Metric name (pm25_corr, pm25_raw, pm10)
        sensor_ids: List of sensor IDs
        start: Start timestamp
        end: End timestamp
        window: Resampling window
        agg: Aggregation method

    Returns:
        DataFrame with time series
    """
    sensor_list = "','".join(sensor_ids)

    sql = f"""
        SELECT
            ts,
            sensor_id,
            {metric},
            qa_flags
        FROM observations_aq
        WHERE sensor_id IN ('{sensor_list}')
          AND ts BETWEEN ? AND ?
        ORDER BY ts
    """

    df = db.query(sql, {"start": start, "end": end})

    if df.empty:
        return df

    # Resample by window
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.set_index("ts")

    # Group by sensor and resample
    result = df.groupby("sensor_id")[metric].resample(window).agg(agg).reset_index()

    return result


def detect_exceedances(
    db,
    threshold: float = 35.0,
    window: str = "24h",
    start: datetime = None,
    end: datetime = None,
    location: str = "bakersfield"
) -> pd.DataFrame:
    """
    Detect EPA standard exceedances.

    Args:
        db: Database instance
        threshold: Threshold value (µg/m³)
        window: Averaging window
        start: Start date
        end: End date
        location: Location identifier

    Returns:
        DataFrame with exceedances
    """
    sql = f"""
        SELECT
            DATE_TRUNC('{window}', ts) as period,
            AVG(pm25_corr) as avg_pm25,
            MAX(pm25_corr) as max_pm25,
            COUNT(*) as n_readings,
            BIT_OR(qa_flags) as combined_qa_flags
        FROM observations_aq
        WHERE ts BETWEEN ? AND ?
        GROUP BY period
        HAVING avg_pm25 > ?
        ORDER BY period
    """

    df = db.query(sql, {"start": start, "end": end, "threshold": threshold})

    if not df.empty:
        df["duration_hours"] = len(df) * (24 if window == "24h" else 1)

    return df


def spike_detect(
    db,
    metric: str = "pm25_corr",
    z_threshold: float = 4.0,
    rolling_window: str = "1h",
    start: datetime = None,
    end: datetime = None,
    location: str = "bakersfield"
) -> pd.DataFrame:
    """
    Detect spikes using robust outlier detection (MAD).

    Args:
        db: Database instance
        metric: Metric to analyze
        z_threshold: Z-score threshold
        rolling_window: Window for rolling statistics
        start: Start date
        end: End date
        location: Location identifier

    Returns:
        DataFrame with detected spikes
    """
    # Get time series
    sql = f"""
        SELECT ts, {metric}, sensor_id, qa_flags
        FROM observations_aq
        WHERE ts BETWEEN ? AND ?
        ORDER BY ts
    """

    df = db.query(sql, {"start": start, "end": end})

    if df.empty:
        return df

    # Calculate rolling median and MAD
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.set_index("ts")

    rolling = df[metric].rolling(window=rolling_window, min_periods=3)
    rolling_median = rolling.median()
    rolling_mad = rolling.apply(lambda x: np.median(np.abs(x - np.median(x))))

    # Modified z-score
    df["z_score"] = 0.6745 * (df[metric] - rolling_median) / rolling_mad
    df["is_spike"] = np.abs(df["z_score"]) > z_threshold

    # Return only spikes
    spikes = df[df["is_spike"]].reset_index()

    return spikes


def correlate(
    db,
    x_metric: str,
    y_metric: str,
    method: Literal["spearman", "pearson"] = "spearman",
    controls: List[str] = None,
    start: datetime = None,
    end: datetime = None,
    location: str = "bakersfield"
) -> Dict[str, Any]:
    """
    Calculate correlation with controls for confounders.

    Args:
        db: Database instance
        x_metric: First variable
        y_metric: Second variable
        method: Correlation method
        controls: Control variables (hour, month, day_of_week)
        start: Start date
        end: End date
        location: Location identifier

    Returns:
        Dictionary with correlation results
    """
    if controls is None:
        controls = ["hour", "month"]

    # Determine tables based on metrics
    aq_metrics = ["pm25_corr", "pm25_raw", "pm10"]
    met_metrics = ["temp_c", "rh", "wind_speed_ms", "stability_idx"]

    # Build query to join AQ and weather data
    sql = """
        SELECT
            aq.ts,
            aq.pm25_corr,
            aq.pm25_raw,
            aq.pm10_raw as pm10,
            met.temp_c,
            met.rh,
            met.wind_speed_ms,
            met.stability_idx
        FROM observations_aq aq
        LEFT JOIN observations_met met
            ON DATE_TRUNC('hour', aq.ts) = DATE_TRUNC('hour', met.ts)
        WHERE aq.ts BETWEEN ? AND ?
    """

    df = db.query(sql, {"start": start, "end": end})

    if df.empty or len(df) < 10:
        return {
            "correlation": None,
            "p_value": None,
            "n_samples": len(df),
            "error": "Insufficient data"
        }

    # Add time features for controls
    df["ts"] = pd.to_datetime(df["ts"])
    df["hour"] = df["ts"].dt.hour
    df["month"] = df["ts"].dt.month
    df["day_of_week"] = df["ts"].dt.dayofweek

    # Drop NaN values
    df = df.dropna(subset=[x_metric, y_metric])

    if len(df) < 10:
        return {
            "correlation": None,
            "p_value": None,
            "n_samples": len(df),
            "error": "Insufficient valid data"
        }

    # Simple correlation if no controls
    if not controls:
        if method == "spearman":
            rho, p_value = spearmanr(df[x_metric], df[y_metric])
        else:
            rho, p_value = pearsonr(df[x_metric], df[y_metric])

        return {
            "correlation": float(rho),
            "p_value": float(p_value),
            "n_samples": len(df),
            "method": method,
            "controlled_for": []
        }

    # Partial correlation with controls
    try:
        # Create formula for OLS
        control_terms = " + ".join([f"C({c})" for c in controls])
        formula_x = f"{x_metric} ~ {control_terms}"
        formula_y = f"{y_metric} ~ {control_terms}"

        # Fit models
        model_x = ols(formula_x, data=df).fit()
        model_y = ols(formula_y, data=df).fit()

        # Get residuals
        resid_x = model_x.resid
        resid_y = model_y.resid

        # Correlate residuals
        if method == "spearman":
            rho, p_value = spearmanr(resid_x, resid_y)
        else:
            rho, p_value = pearsonr(resid_x, resid_y)

        return {
            "correlation": float(rho),
            "p_value": float(p_value),
            "n_samples": len(df),
            "method": method,
            "controlled_for": controls,
            "partial_correlation": True
        }

    except Exception as e:
        return {
            "correlation": None,
            "p_value": None,
            "n_samples": len(df),
            "error": str(e)
        }


def compare_periods(
    db,
    period_a: tuple[datetime, datetime],
    period_b: tuple[datetime, datetime],
    metric: str = "pm25_corr",
    test: str = "mann-whitney",
    location: str = "bakersfield"
) -> Dict[str, Any]:
    """
    Statistical comparison of two time periods.

    Args:
        db: Database instance
        period_a: (start, end) tuple for first period
        period_b: (start, end) tuple for second period
        metric: Metric to compare
        test: Statistical test
        location: Location identifier

    Returns:
        Dictionary with comparison results
    """
    sql = f"""
        SELECT {metric}
        FROM observations_aq
        WHERE ts BETWEEN ? AND ?
    """

    # Get data for both periods
    df_a = db.query(sql, {"start": period_a[0], "end": period_a[1]})
    df_b = db.query(sql, {"start": period_b[0], "end": period_b[1]})

    if df_a.empty or df_b.empty:
        return {"error": "Insufficient data for one or both periods"}

    values_a = df_a[metric].dropna().values
    values_b = df_b[metric].dropna().values

    if len(values_a) < 3 or len(values_b) < 3:
        return {"error": "Insufficient valid data"}

    # Mann-Whitney U test (non-parametric)
    if test == "mann-whitney":
        statistic, p_value = mannwhitneyu(values_a, values_b, alternative="two-sided")

        # Effect size (rank-biserial correlation)
        n_a, n_b = len(values_a), len(values_b)
        r = 1 - (2 * statistic) / (n_a * n_b)

        return {
            "test": "mann-whitney",
            "statistic": float(statistic),
            "p_value": float(p_value),
            "effect_size": float(r),
            "period_a_median": float(np.median(values_a)),
            "period_b_median": float(np.median(values_b)),
            "period_a_mean": float(np.mean(values_a)),
            "period_b_mean": float(np.mean(values_b)),
            "n_a": n_a,
            "n_b": n_b
        }

    return {"error": f"Unknown test: {test}"}


def infer_inversion(
    db,
    min_confidence: float = 0.7,
    start: datetime = None,
    end: datetime = None,
    location: str = "bakersfield"
) -> List[Dict[str, Any]]:
    """
    Infer surface inversions from weather indicators.

    Args:
        db: Database instance
        min_confidence: Minimum confidence threshold
        start: Start date
        end: End date
        location: Location identifier

    Returns:
        List of detected inversion periods
    """
    # Get combined AQ and weather data
    sql = """
        SELECT
            aq.ts,
            aq.pm25_corr,
            met.temp_c,
            met.wind_speed_ms,
            met.stability_idx
        FROM observations_aq aq
        LEFT JOIN observations_met met
            ON DATE_TRUNC('hour', aq.ts) = DATE_TRUNC('hour', met.ts)
        WHERE aq.ts BETWEEN ? AND ?
        ORDER BY aq.ts
    """

    df = db.query(sql, {"start": start, "end": end})

    if df.empty:
        return []

    df["ts"] = pd.to_datetime(df["ts"])

    # Calculate indicators
    df["low_wind"] = df["wind_speed_ms"] < 2.0
    df["high_stability"] = df["stability_idx"] > 0.3

    # Calculate evening cooling (temperature drop)
    df["hour"] = df["ts"].dt.hour
    df["date"] = df["ts"].dt.date

    evening_cooling = []
    for date, group in df.groupby("date"):
        afternoon_temp = group[group["hour"] == 15]["temp_c"].mean()
        evening_temp = group[group["hour"] == 20]["temp_c"].mean()

        if not np.isnan(afternoon_temp) and not np.isnan(evening_temp):
            cooling = afternoon_temp - evening_temp
            evening_cooling.append((date, cooling))

    # Detect PM2.5 buildup at night
    df["night_pm"] = df[df["hour"].isin([20, 21, 22, 23])]["pm25_corr"]
    df["day_pm"] = df[df["hour"].isin([12, 13, 14, 15])]["pm25_corr"]

    # Find inversion periods
    inversions = []
    for date, group in df.groupby("date"):
        indicators = {
            "low_wind": group["low_wind"].mean() > 0.6,
            "high_stability": group["high_stability"].mean() > 0.5,
            "pm_buildup": group["night_pm"].mean() > group["day_pm"].mean() * 1.3
        }

        # Add cooling indicator
        cooling_value = next((c[1] for c in evening_cooling if c[0] == date), 0)
        indicators["evening_cooling"] = cooling_value > 5.0

        # Calculate confidence
        confidence = sum(indicators.values()) / len(indicators)

        if confidence >= min_confidence:
            inversions.append({
                "date": str(date),
                "confidence": float(confidence),
                "indicators": indicators,
                "type": "surface_inferred",
                "caveat": "No vertical profile available"
            })

    return inversions
