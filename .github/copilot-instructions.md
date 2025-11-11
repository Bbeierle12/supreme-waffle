# Copilot Instructions — Air Quality NotebookLM

Short, actionable guidance for AI coding agents working on this repository.

## 1. Big Picture Architecture

This project is a **FastAPI backend + Next.js frontend** for scientific air quality analysis with LLM-driven research assistance.

**Key Components:**
- **Backend** (`air-quality-notebooklm/backend/`): FastAPI server with DuckDB + Parquet storage
  - Entry point: `backend/main.py` — FastAPI app, APScheduler for ingestion, exception handlers
  - Data models: `backend/models.py` — ALL Pydantic schemas (Observation, QAFlags, Tool inputs/outputs)
  - LLM orchestration: `backend/llm/orchestrator.py` — Claude agentic loop with tool calling
  - Safe tools: `backend/llm/tools.py` — 5 structured analysis tools (NO raw SQL from LLM)
  - Storage: `backend/storage/database.py` — DuckDB with Parquet-backed views
  - QA/QC: `backend/analytics/qa_qc.py` — EPA Barkjohn correction, A/B validation, MAD outlier detection
  - Analytics: `backend/analytics/primitives.py` — Statistical functions (correlations, exceedances, inversions)
  
- **Frontend** (`air-quality-notebooklm/frontend/`): Next.js 14 + React + Tailwind
  - Entry: `app/page.tsx` — main page
  - Chat UI: `components/ChatInterface.tsx` — conversational interface
  - Data inspector: `components/DataInspector.tsx` — tool call visualization

- **Data Flow:**
  1. Scheduler (APScheduler) → `ingestion/purpleair.py` + `ingestion/weather.py` fetch data every 10-15 min
  2. Data → QA/QC validation → Parquet files (hive-partitioned by `date=YYYY-MM-DD`)
  3. DuckDB views (`observations_aq`, `observations_met`) → analytics primitives
  4. User query → Claude → structured tool calls → analytics → structured response

## 2. Critical Constraints (DO NOT VIOLATE)

1. **NO raw SQL from LLM**: All data access MUST use structured tools defined in `backend/models.py` (GetMetricSummary, DetectExceedances, etc.). This prevents SQL injection.
2. **Location IDs**: Lowercase alphanumeric with hyphens/underscores only (validated in `QueryRequest.validate_location`)
3. **QA Flags are bitmask**: `QAFlags` in `models.py` uses bitwise operations (0x01, 0x02, etc.). Preserve semantics when modifying.
4. **Parquet partitioning**: Data stored as `data/parquet/{aq,met}/date=YYYY-MM-DD/*.parquet`. DuckDB reads via views with `hive_partitioning=true`.
5. **Tool schemas**: Changing tool input/output shapes in `models.py` requires updating `llm/tools.py`, `llm/orchestrator.py`, and tests.

## 3. Key File Reference

| File | Purpose |
|------|---------|
| `backend/models.py` | **START HERE** — All Pydantic models, tool schemas, QA flags |
| `backend/main.py` | FastAPI app, endpoints, scheduler setup, lifespan context |
| `backend/llm/orchestrator.py` | Claude integration, agentic loop (max 5 rounds) |
| `backend/llm/tools.py` | `TOOLS` list & `execute_tool()` — only way LLM accesses data |
| `backend/storage/database.py` | DuckDB interface, `write_parquet()`, `query()`, index creation |
| `backend/analytics/qa_qc.py` | `correct_pm25_barkjohn()`, `validate_ab_channels()`, `detect_outliers_mad()` |
| `backend/analytics/primitives.py` | `correlate()`, `detect_exceedances()`, `spike_detect()`, `infer_inversion()` |
| `config/locations.yaml` | Location config (sensors, bounds, QA thresholds) |
| `backend/tests/test_gold_queries.py` | Gold standard tests — expected outputs for queries |
| `backend/tests/test_qa_qc.py` | QA/QC validation tests (Barkjohn formula, MAD outliers) |

## 4. Common Developer Workflows

### Start Services (Docker)
```bash
cd air-quality-notebooklm
docker-compose up -d
```

### Start Backend (Dev)
```bash
cd air-quality-notebooklm/backend
python main.py --reload
# Or with uvicorn directly:
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Start Frontend (Dev)
```bash
cd air-quality-notebooklm/frontend
npm install
npm run dev
```

### Run Tests
```bash
cd air-quality-notebooklm/backend
pytest tests/ -v
# Specific test file:
pytest tests/test_gold_queries.py -v
```

### Trigger Manual Ingestion
```bash
curl -X POST http://localhost:8000/ingest/trigger
```

### Check Status
```bash
curl http://localhost:8000/status
```

## 5. Adding a New LLM Analysis Tool

**Example:** Add a tool to detect diurnal patterns

1. **Define input schema** in `backend/models.py`:
   ```python
   class DetectDiurnalPattern(BaseModel):
       metric: Literal["pm25_corr", "temp_c"]
       start: datetime
       end: datetime
       location: str = "bakersfield"
   ```

2. **Implement logic** in `backend/analytics/primitives.py`:
   ```python
   def detect_diurnal_pattern(db, metric, start, end, location):
       # Query hourly averages, detect patterns
       # Return structured result
       pass
   ```

3. **Wrap in tool** in `backend/llm/tools.py`:
   - Add to `TOOLS` list with name, description, schema
   - Add `execute_tool()` case: validate params → call primitive → return result

4. **Test** in `backend/tests/test_gold_queries.py`:
   - Add test case with expected output
   - Verify tool can be called by orchestrator

## 6. QA/QC and Scientific Rigor

- **Barkjohn correction**: EPA-recommended formula for PurpleAir PM2.5 (see `qa_qc.correct_pm25_barkjohn()`)
- **A/B validation**: PurpleAir dual-channel agreement (abs diff <5 µg/m³ OR rel diff <20%)
- **Outlier detection**: MAD-based z-scores (robust to non-normality, threshold=4.0)
- **QA flags** (bitmask in `QAFlags`):
  - 0x01: A/B mismatch
  - 0x02: High humidity (RH>85%)
  - 0x04: Statistical outlier
  - 0x08: Stale data (>2 hours)
  - 0x10: Sensor offline
  - 0x20: Maintenance flag

## 7. Integration Points

- **Scheduler**: Jobs registered in `main.py:lifespan()`. Uses APScheduler with `AsyncIOScheduler`.
- **LLM**: Anthropic Claude via `anthropic` SDK. Model: `claude-3-5-sonnet-20241022`. See `orchestrator.py:AnalysisOrchestrator`.
- **Database**: Singleton `get_db()` in `storage/database.py`. Returns `Database` instance. Use `.query(sql, params)` and `.write_parquet(df, data_type)`.
- **API Keys**: Set via `.env` file in backend directory (see `backend/config.py`):
  - `ANTHROPIC_API_KEY`
  - `PURPLEAIR_API_KEY`
  - `OPENWEATHER_API_KEY`

## 8. Testing

- **Focus**: `backend/tests/` — gold queries, QA/QC validation, database indexes
- **Gold queries**: `test_gold_queries.py` — ensure LLM tools return expected outputs
- **QA/QC tests**: `test_qa_qc.py` — validate Barkjohn formula, MAD outliers, A/B validation
- **When changing models**: Update tests to assert new Pydantic shapes

## 9. Data Storage

- **Format**: Parquet files, partitioned by date
- **Paths**: 
  - Air quality: `data/parquet/aq/date=YYYY-MM-DD/*.parquet`
  - Weather: `data/parquet/weather/date=YYYY-MM-DD/*.parquet`
- **DuckDB views**: `observations_aq`, `observations_met` (created in `Database._setup_schema()`)
- **Indexes**: Created on `events`, `documents`, `chunks`, `lineage` tables for performance

## 10. Quick Examples

### Add a new location
Edit `config/locations.yaml`:
```yaml
new_city:
  name: "New City, State"
  timezone: "America/Los_Angeles"
  bounds:
    lat: [lat_min, lat_max]
    lon: [lon_min, lon_max]
  sensors:
    purpleair: [sensor_id_1, sensor_id_2]
  qa_rules:
    spike_threshold: 4.0
    humidity_correction: "barkjohn"
```

### Query data directly (from backend)
```python
from storage.database import get_db
db = get_db()
df = db.query("SELECT * FROM observations_aq WHERE date = '2024-11-10' LIMIT 10")
```

### Test a tool manually
```python
from llm.tools import execute_tool
from datetime import datetime
result = execute_tool("get_metric_summary", {
    "metric": "pm25_corr",
    "window": "24h",
    "aggregate": "max",
    "start": datetime(2024, 11, 9),
    "end": datetime(2024, 11, 10),
    "location": "bakersfield"
})
```

## 11. Debugging Tips

- **Check logs**: `data/logs/app.log` (or `docker-compose logs -f backend`)
- **No data**: Verify API keys, sensor IDs, trigger ingestion manually
- **Tool failures**: Check `execute_tool()` catch block in `tools.py`, validate input schema
- **LLM not using tools**: Review `TOOLS` list registration, check Claude response `stop_reason`
- **Database errors**: Check Parquet partitions exist, verify DuckDB views in `_setup_schema()`

## 12. Frontend-Backend Contract

- **Endpoint**: `POST /query` (sync) or `POST /query/stream` (SSE)
- **Request**: `{"question": "...", "location": "bakersfield"}`
- **Response**: `QueryResponse` model (see `models.py`):
  - `answer`: `{text, confidence, sources}`
  - `tool_calls`: `[{tool_name, tool_input, result}, ...]`
  - `rounds`: Number of agentic rounds
  - `model`: LLM model used

## 13. Scientific Limitations (Document in Responses)

- **No vertical profiles**: Inversion detection is surface-based only (temp, wind, PM buildup)
- **Single-location focus**: Optimized for Bakersfield initially (multi-location support in config)
- **Not for regulatory use**: Research tool, not certified for EPA compliance

---

**If unclear**: Ask which section needs expansion (LLM prompts, tool schemas, storage layout, etc.) and I'll iterate.
