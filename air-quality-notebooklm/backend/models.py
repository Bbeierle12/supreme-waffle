"""Data models for air quality observations and events."""
from datetime import datetime
from typing import Optional, Dict, Any, Literal, List
from enum import IntFlag
from pydantic import BaseModel, Field


class QAFlags(IntFlag):
    """QA/QC flags as bit mask."""
    NONE = 0x00
    AB_MISMATCH = 0x01      # A/B channel disagreement
    HIGH_HUMIDITY = 0x02    # RH>85% uncorrected
    OUTLIER = 0x04          # Statistical outlier (MAD z-score>4)
    STALE_DATA = 0x08       # >2 hours old
    SENSOR_OFFLINE = 0x10   # Offline periods
    MAINTENANCE = 0x20      # Maintenance/calibration flag


class AirQualityObservation(BaseModel):
    """Air quality observation with QA/QC."""
    ts: datetime
    source: Literal["purpleair", "airnow"]
    sensor_id: str
    pm25_raw: float
    pm25_corr: float
    pm10_raw: Optional[float] = None
    qa_flags: int = 0
    window: Literal["1m", "10m", "1h", "24h"]
    lat: float
    lon: float
    metadata: Optional[Dict[str, Any]] = None


class WeatherObservation(BaseModel):
    """Weather observation."""
    ts: datetime
    station_id: str
    temp_c: float
    rh: float
    wind_speed_ms: float
    wind_dir_deg: float
    pressure_mb: Optional[float] = None
    stability_idx: Optional[float] = None
    mixing_height_m: Optional[float] = None
    window: Literal["1m", "10m", "1h", "24h"]
    lat: float
    lon: float


class Event(BaseModel):
    """Detected event (spike, exceedance, inversion)."""
    start_ts: datetime
    end_ts: datetime
    type: Literal["spike", "exceedance", "inversion_inferred"]
    confidence: float = Field(ge=0.0, le=1.0)
    details: Dict[str, Any]


class Document(BaseModel):
    """Research document for RAG."""
    doc_id: str
    title: str
    path: str
    checksum: str
    added_at: datetime


class Chunk(BaseModel):
    """Document chunk with embedding."""
    chunk_id: str
    doc_id: str
    page: int
    text: str
    embedding: Optional[List[float]] = None
    span: str  # Page location reference


class DataLineage(BaseModel):
    """Data lineage tracking."""
    record_id: str
    table_name: str
    raw_payload: Dict[str, Any]
    fetched_at: datetime
    api_source: str
    api_version: str


# Tool schemas for LLM
class GetMetricSummary(BaseModel):
    """Get summary statistics for a metric."""
    metric: Literal["pm25_corr", "pm25_raw", "pm10"]
    window: Literal["1h", "24h"]
    start: datetime
    end: datetime
    location: str = "bakersfield"
    aggregate: Literal["max", "mean", "p95", "median"]


class DetectExceedances(BaseModel):
    """Detect EPA standard exceedances."""
    threshold: float = Field(default=35.0, description="EPA 24-hour standard µg/m³")
    window: Literal["24h"]
    start: datetime
    end: datetime
    location: str = "bakersfield"


class DetectSpikes(BaseModel):
    """Detect PM2.5 spikes using statistical methods."""
    metric: Literal["pm25_corr", "pm25_raw"]
    z_threshold: float = Field(default=4.0, description="MAD z-score threshold")
    rolling_window: Literal["1h", "3h", "6h"] = "1h"
    start: datetime
    end: datetime
    location: str = "bakersfield"


class FindCorrelations(BaseModel):
    """Find correlations with controls for confounders."""
    x_metric: str
    y_metric: str
    method: Literal["spearman", "pearson"] = "spearman"
    controls: List[Literal["hour", "month", "day_of_week"]] = ["hour", "month"]
    start: datetime
    end: datetime
    location: str = "bakersfield"


class InferInversion(BaseModel):
    """Infer surface inversion from weather indicators."""
    min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    start: datetime
    end: datetime
    location: str = "bakersfield"


class AnalysisFact(BaseModel):
    """A measured fact with metadata."""
    value: float
    unit: str
    metric: str
    timestamp: Optional[datetime] = None
    sensor_id: Optional[str] = None
    qa_flags: int = 0


class AnalysisFinding(BaseModel):
    """A statistical finding."""
    description: str
    statistic: float
    p_value: Optional[float] = None
    confidence_interval: Optional[tuple[float, float]] = None
    n_samples: int
    controlled_for: List[str] = []


class Citation(BaseModel):
    """Citation for data or literature."""
    type: Literal["data", "literature"]
    source: str
    timestamp: Optional[datetime] = None
    page: Optional[int] = None
    text: Optional[str] = None


class AnalysisAnswer(BaseModel):
    """Structured answer from the system."""
    measurements: List[AnalysisFact]
    statistics: List[AnalysisFinding]
    confidence: Literal["high", "medium", "low"]
    caveats: List[str]
    sources: List[Citation]
    raw_query_params: Optional[Dict[str, Any]] = None
