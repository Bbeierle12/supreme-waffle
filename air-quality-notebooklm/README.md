# Air Quality NotebookLM

A personal research assistant for air quality data analysis. Transform fragmented air quality data into a trustworthy conversational research partner that understands atmospheric science and maintains scientific integrity.

![Version](https://img.shields.io/badge/version-0.1.0-blue)
![Python](https://img.shields.io/badge/python-3.11-blue)
![Next.js](https://img.shields.io/badge/next.js-14.0-black)

## Features

- **QA/QC with EPA Standards**: Automatic PurpleAir correction, sensor validation, and data quality flagging
- **Statistical Rigor**: Proper correlations with controls, confidence intervals, and significance tests
- **Inversion Detection**: Surface-based atmospheric inversion inference from weather indicators
- **Safe LLM Tools**: Structured query interface with no raw SQL generation
- **Reproducible Analysis**: Every answer traceable to data and methods with full lineage tracking
- **Real-time Data**: Automatic ingestion from PurpleAir and weather APIs

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (optional)
- API Keys:
  - Anthropic API key
  - PurpleAir API key
  - OpenWeather API key (optional)

### Docker Setup (Recommended)

1. Clone the repository:
```bash
git clone https://github.com/yourusername/air-quality-notebooklm.git
cd air-quality-notebooklm
```

2. Create `.env` file:
```bash
cp backend/.env.example .env
# Edit .env with your API keys
```

3. Start the services:
```bash
docker-compose up -d
```

4. Open http://localhost:3000 in your browser

### Manual Setup

#### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
python main.py
```

Backend will run on http://localhost:8000

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend will run on http://localhost:3000

## Architecture

```
air-quality-notebooklm/
├── backend/               # FastAPI server
│   ├── analytics/        # QA/QC and analysis primitives
│   ├── ingestion/        # PurpleAir & weather data ingestion
│   ├── llm/              # Claude orchestration & safe tools
│   ├── storage/          # DuckDB database interface
│   └── main.py           # FastAPI application
├── frontend/             # Next.js UI
│   ├── app/              # Next.js App Router pages
│   └── components/       # React components
├── data/                 # Data storage
│   ├── parquet/          # Partitioned Parquet files
│   └── papers/           # Research PDFs for RAG
└── config/               # Location configurations
```

## Data Model

### Air Quality Observations

- **Source**: PurpleAir, AirNow
- **QA/QC**: Barkjohn humidity correction, A/B channel validation, outlier detection
- **Storage**: Partitioned Parquet with DuckDB views

### Weather Observations

- **Source**: OpenWeather API
- **Features**: Temperature, humidity, wind, stability index
- **Inversion Detection**: Surface-based inference (no vertical profiles)

### QA Flags

- `0x01`: A/B channel disagreement (>5 µg/m³ or >20%)
- `0x02`: High humidity (RH>85%) uncorrected
- `0x04`: Statistical outlier (MAD z-score>4)
- `0x08`: Stale data (>2 hours old)
- `0x10`: Sensor offline periods
- `0x20`: Maintenance/calibration flag

## Analytics Tools

All analysis functions are exposed as safe LLM tools:

1. **get_metric_summary**: Get summary statistics (max, mean, p95, median)
2. **detect_exceedances**: Detect EPA standard exceedances (35 µg/m³)
3. **detect_spikes**: Statistical outlier detection using MAD
4. **find_correlations**: Correlations with controls for confounders
5. **infer_inversion**: Surface inversion detection from weather indicators

## API Endpoints

- `GET /`: System info
- `GET /status`: System status and data availability
- `POST /query`: Ask a question (synchronous)
- `POST /query/stream`: Ask a question (streaming)
- `POST /ingest/trigger`: Manually trigger data ingestion
- `GET /locations`: List available locations

## Configuration

### Adding Locations

Edit `config/locations.yaml`:

```yaml
my_location:
  name: "My City, State"
  timezone: "America/Los_Angeles"
  bounds:
    lat: [min_lat, max_lat]
    lon: [min_lon, max_lon]
  sensors:
    purpleair: [sensor_id_1, sensor_id_2]
    epa: ["epa_site_id"]
  qa_rules:
    spike_threshold: 4.0
    humidity_correction: "barkjohn"
```

## Testing

Run the test suite:

```bash
cd backend
pytest tests/ -v
```

Tests include:
- QA/QC validation tests
- Gold standard query tests
- Integration tests

## Development

### Backend Development

```bash
cd backend
python main.py --reload
```

### Frontend Development

```bash
cd frontend
npm run dev
```

### Running Tests

```bash
# Backend tests
cd backend
pytest

# Frontend tests (if added)
cd frontend
npm test
```

## Data Ingestion

Data is automatically fetched every 10-15 minutes when the backend is running.

### Manual Trigger

```bash
curl -X POST http://localhost:8000/ingest/trigger
```

### Backfill Historical Data

```python
from ingestion.purpleair import backfill_historical
from datetime import datetime

await backfill_historical(
    api_key=settings.purpleair_api_key,
    sensor_ids=[122842, 122848],
    start_date=datetime(2024, 11, 1),
    end_date=datetime(2024, 11, 10),
    location_config=location_config.get_location("bakersfield"),
    db=get_db()
)
```

## Scientific Rigor

### QA/QC Process

1. **A/B Channel Validation**: Ensure PurpleAir sensor agreement
2. **Humidity Correction**: EPA-recommended Barkjohn formula
3. **Outlier Detection**: MAD-based z-scores (robust to non-normality)
4. **Staleness Checks**: Flag data >2 hours old

### Statistical Methods

- **Correlations**: Spearman (robust) with partial correlation for controls
- **Comparisons**: Mann-Whitney U (non-parametric)
- **Effect Sizes**: Cohen's d or rank-biserial correlation
- **Time Series**: Rolling statistics with proper windowing

### Limitations

- **No Vertical Profiles**: Inversion detection is surface-based only
- **Single Location Focus**: Optimized for Bakersfield initially
- **Research Tool**: Not for regulatory compliance or public health alerts

## Performance

- **Query Response**: <2 seconds for common queries
- **Data Storage**: ~50MB/month per location
- **Concurrent Users**: Single-user optimized

## Troubleshooting

### Database Issues

```bash
# Reset database
rm data/airquality.db
# Restart backend to recreate schema
```

### API Rate Limits

- PurpleAir: ~1 request per second
- OpenWeather: Adjust update frequency in scheduler

### No Data Available

Check that:
1. API keys are valid
2. Sensor IDs are correct
3. Ingestion scheduler is running
4. Check logs for errors

## Contributing

This is a personal research tool. If you'd like to adapt it:

1. Fork the repository
2. Modify `config/locations.yaml` for your location
3. Adjust QA rules as needed
4. Submit issues for bugs

## License

MIT License - see LICENSE file

## Citation

If you use this tool in research:

```
Air Quality NotebookLM (2024)
Personal research assistant for air quality data analysis
https://github.com/yourusername/air-quality-notebooklm
```

## Acknowledgments

- EPA for Barkjohn PurpleAir correction formula
- PurpleAir for sensor data API
- Anthropic for Claude AI

## References

1. Barkjohn et al. (2021). "Development and Application of a United States-wide correction for PM2.5 data collected with the PurpleAir sensor"
2. EPA Air Quality Standards: https://www.epa.gov/criteria-air-pollutants/naaqs-table

---

**Version**: 0.1.0
**Created**: November 2024
**Purpose**: Scientifically rigorous personal research tool for air quality analysis
