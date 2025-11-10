"""Safe LLM tools - structured wrappers around analytics primitives."""
from typing import List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from models import (
    GetMetricSummary,
    DetectExceedances,
    DetectSpikes,
    FindCorrelations,
    InferInversion
)
from analytics import primitives
from storage.database import get_db


# Tool registry with schemas
TOOLS = [
    {
        "name": "get_metric_summary",
        "description": "Get summary statistics (max, mean, p95, median) for PM2.5 or PM10 over a time period",
        "input_schema": GetMetricSummary.model_json_schema()
    },
    {
        "name": "detect_exceedances",
        "description": "Detect periods when PM2.5 exceeded EPA standards (35 µg/m³ for 24-hour average)",
        "input_schema": DetectExceedances.model_json_schema()
    },
    {
        "name": "detect_spikes",
        "description": "Detect statistical outliers and spikes in PM2.5 data using robust MAD method",
        "input_schema": DetectSpikes.model_json_schema()
    },
    {
        "name": "find_correlations",
        "description": "Find correlations between PM2.5 and weather variables, controlling for time-of-day and seasonal effects",
        "input_schema": FindCorrelations.model_json_schema()
    },
    {
        "name": "infer_inversion",
        "description": "Infer surface-level atmospheric inversions from weather indicators (low wind, temperature drop, PM buildup)",
        "input_schema": InferInversion.model_json_schema()
    }
]


def execute_tool(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a tool with given parameters.

    Args:
        tool_name: Name of tool to execute
        params: Tool parameters

    Returns:
        Tool execution results
    """
    db = get_db()

    try:
        if tool_name == "get_metric_summary":
            validated_params = GetMetricSummary(**params)
            result = get_metric_summary(db, validated_params)

        elif tool_name == "detect_exceedances":
            validated_params = DetectExceedances(**params)
            result = detect_exceedances_tool(db, validated_params)

        elif tool_name == "detect_spikes":
            validated_params = DetectSpikes(**params)
            result = detect_spikes_tool(db, validated_params)

        elif tool_name == "find_correlations":
            validated_params = FindCorrelations(**params)
            result = find_correlations_tool(db, validated_params)

        elif tool_name == "infer_inversion":
            validated_params = InferInversion(**params)
            result = infer_inversion_tool(db, validated_params)

        else:
            return {"error": f"Unknown tool: {tool_name}"}

        return {
            "success": True,
            "result": result,
            "tool": tool_name,
            "params": params
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "tool": tool_name,
            "params": params
        }


def get_metric_summary(db, params: GetMetricSummary) -> Dict[str, Any]:
    """Get summary statistics for a metric."""
    # Query data
    sql = f"""
        SELECT
            {params.aggregate}({params.metric}) as value,
            COUNT(*) as n_samples,
            BIT_OR(qa_flags) as combined_qa_flags
        FROM observations_aq
        WHERE ts BETWEEN ? AND ?
          AND window = ?
    """

    result = db.query(sql, {
        "start": params.start,
        "end": params.end,
        "window": params.window
    })

    if result.empty:
        return {
            "value": None,
            "n_samples": 0,
            "error": "No data found"
        }

    row = result.iloc[0]

    return {
        "metric": params.metric,
        "aggregate": params.aggregate,
        "value": float(row["value"]) if row["value"] is not None else None,
        "unit": "µg/m³",
        "n_samples": int(row["n_samples"]),
        "window": params.window,
        "start": params.start.isoformat(),
        "end": params.end.isoformat(),
        "qa_flags": int(row["combined_qa_flags"]) if row["combined_qa_flags"] else 0
    }


def detect_exceedances_tool(db, params: DetectExceedances) -> Dict[str, Any]:
    """Detect EPA standard exceedances."""
    df = primitives.detect_exceedances(
        db,
        threshold=params.threshold,
        window=params.window,
        start=params.start,
        end=params.end,
        location=params.location
    )

    if df.empty:
        return {
            "exceedances": [],
            "total_count": 0,
            "threshold": params.threshold,
            "unit": "µg/m³"
        }

    exceedances = []
    for _, row in df.iterrows():
        exceedances.append({
            "period": str(row["period"]),
            "avg_pm25": float(row["avg_pm25"]),
            "max_pm25": float(row["max_pm25"]),
            "n_readings": int(row["n_readings"]),
            "qa_flags": int(row["combined_qa_flags"])
        })

    return {
        "exceedances": exceedances,
        "total_count": len(exceedances),
        "threshold": params.threshold,
        "unit": "µg/m³",
        "window": params.window
    }


def detect_spikes_tool(db, params: DetectSpikes) -> Dict[str, Any]:
    """Detect spikes in PM2.5 data."""
    df = primitives.spike_detect(
        db,
        metric=params.metric,
        z_threshold=params.z_threshold,
        rolling_window=params.rolling_window,
        start=params.start,
        end=params.end,
        location=params.location
    )

    if df.empty:
        return {
            "spikes": [],
            "total_count": 0,
            "method": "MAD z-score"
        }

    spikes = []
    for _, row in df.iterrows():
        spikes.append({
            "timestamp": str(row["ts"]),
            "value": float(row[params.metric]),
            "z_score": float(row["z_score"]),
            "sensor_id": str(row["sensor_id"])
        })

    return {
        "spikes": spikes,
        "total_count": len(spikes),
        "method": "MAD z-score",
        "threshold": params.z_threshold
    }


def find_correlations_tool(db, params: FindCorrelations) -> Dict[str, Any]:
    """Find correlations between variables."""
    result = primitives.correlate(
        db,
        x_metric=params.x_metric,
        y_metric=params.y_metric,
        method=params.method,
        controls=params.controls,
        start=params.start,
        end=params.end,
        location=params.location
    )

    return result


def infer_inversion_tool(db, params: InferInversion) -> Dict[str, Any]:
    """Infer surface inversions."""
    inversions = primitives.infer_inversion(
        db,
        min_confidence=params.min_confidence,
        start=params.start,
        end=params.end,
        location=params.location
    )

    return {
        "inversions": inversions,
        "total_count": len(inversions),
        "min_confidence": params.min_confidence,
        "caveat": "Surface-based inference without vertical profile data"
    }
