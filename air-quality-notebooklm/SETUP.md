# Setup Guide

## Initial Setup

### 1. API Keys

You'll need the following API keys:

#### Anthropic API Key
- Sign up at https://console.anthropic.com/
- Create a new API key
- Costs: ~$3 per 1M input tokens, ~$15 per 1M output tokens (Claude Sonnet)

#### PurpleAir API Key
- Request from https://api.purpleair.com/
- Free tier includes 1 request per second
- Required for sensor data

#### OpenWeather API Key (Optional)
- Sign up at https://openweathermap.org/api
- Free tier: 1000 calls/day
- Used for weather data and inversion detection

### 2. Configuration

Create `.env` file in the backend directory:

```bash
cd backend
cp .env.example .env
```

Edit `.env` with your keys:

```
ANTHROPIC_API_KEY=sk-ant-...
PURPLEAIR_API_KEY=...
OPENWEATHER_API_KEY=...
```

### 3. Location Configuration

Edit `config/locations.yaml` to set up your location:

```yaml
bakersfield:
  name: "Bakersfield, CA"
  timezone: "America/Los_Angeles"
  bounds:
    lat: [35.25, 35.45]
    lon: [-119.15, -118.85]
  sensors:
    purpleair: [122842, 122848, 14633]  # Your sensor IDs
    epa: ["06-029-0014"]
  qa_rules:
    spike_threshold: 4.0
    humidity_correction: "barkjohn"
```

#### Finding PurpleAir Sensor IDs

1. Go to https://map.purpleair.com/
2. Click on sensors in your area
3. The sensor ID is in the URL: `...?select=SENSOR_ID`

### 4. Installation

#### Option A: Docker (Recommended)

```bash
docker-compose up -d
```

This will:
- Build backend and frontend containers
- Start data ingestion scheduler
- Expose services on ports 8000 (backend) and 3000 (frontend)

#### Option B: Manual Installation

**Backend:**
```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

### 5. Initial Data Load

The system will automatically start fetching data when the backend starts. To manually trigger:

```bash
curl -X POST http://localhost:8000/ingest/trigger
```

For historical backfill, use the Python API:

```python
from ingestion.purpleair import backfill_historical
from datetime import datetime
from config import settings, location_config
from storage.database import get_db

location = location_config.get_location("bakersfield")
db = get_db()

await backfill_historical(
    api_key=settings.purpleair_api_key,
    sensor_ids=location["sensors"]["purpleair"],
    start_date=datetime(2024, 11, 1),
    end_date=datetime(2024, 11, 10),
    location_config=location,
    db=db
)
```

## Verification

### 1. Check Backend Status

```bash
curl http://localhost:8000/status
```

Expected response:
```json
{
  "status": "healthy",
  "database": "/data/airquality.db",
  "data_range": {
    "start": "2024-11-08T00:00:00",
    "end": "2024-11-10T12:00:00"
  },
  "sensors": ["122842", "122848", "14633"]
}
```

### 2. Check Frontend

Open http://localhost:3000 in your browser. You should see the chat interface.

### 3. Test Query

Try asking: "What was the max PM2.5 yesterday?"

If you get a response with actual data, everything is working!

## Troubleshooting

### No Data Showing Up

**Symptoms:**
- Empty data_range in /status
- "No data found" errors in queries

**Solutions:**
1. Check API keys are valid
2. Verify sensor IDs exist: https://map.purpleair.com/
3. Check backend logs for API errors
4. Manually trigger ingestion: `curl -X POST http://localhost:8000/ingest/trigger`

### Database Errors

**Symptoms:**
- "Database locked" errors
- "Table does not exist" errors

**Solutions:**
1. Stop the backend
2. Delete `data/airquality.db`
3. Restart backend (will recreate schema)

### Rate Limiting

**Symptoms:**
- 429 errors in logs
- Intermittent data gaps

**Solutions:**
1. PurpleAir: Reduce update frequency in scheduler (currently 10 minutes)
2. OpenWeather: Use free tier wisely (1000 calls/day)

### Frontend Not Connecting to Backend

**Symptoms:**
- Network errors in browser console
- "Failed to get response" errors

**Solutions:**
1. Check backend is running: `curl http://localhost:8000/`
2. Verify CORS settings in backend/main.py
3. Check NEXT_PUBLIC_API_URL in frontend .env.local

## Optimization

### Database Performance

For large datasets (>1M rows):

```python
# Run periodically
from storage.database import get_db

db = get_db()
db.vacuum()  # Reclaim space and optimize
```

### Storage Management

Parquet files are partitioned by date. To clean old data:

```bash
# Remove data older than 90 days
find data/parquet -name "date=2024-08-*" -type d -exec rm -rf {} +
```

### Memory Usage

- Backend: ~200-500MB with DuckDB
- Frontend: ~100-200MB
- Total: ~500MB typical usage

## Production Considerations

### Security

1. **API Keys**: Use environment variables, never commit to git
2. **CORS**: Restrict origins in production
3. **Authentication**: Add if exposing publicly

### Monitoring

1. Check logs: `docker-compose logs -f backend`
2. Monitor disk space: Parquet files grow ~50MB/month per location
3. Set up alerts for API failures

### Backups

Important files to backup:
- `data/airquality.db` - Database
- `data/parquet/` - Raw data files
- `config/locations.yaml` - Configuration
- `.env` - API keys (store securely!)

Backup script:
```bash
#!/bin/bash
DATE=$(date +%Y%m%d)
tar -czf backup-$DATE.tar.gz data/ config/ .env
```

## Next Steps

1. **Customize Queries**: Modify analytics primitives for your research questions
2. **Add Locations**: Expand to multiple monitoring locations
3. **Add Papers**: Place PDFs in `data/papers/` for RAG-based literature search
4. **Tune QA/QC**: Adjust thresholds in location config for your sensors

## Getting Help

- Check logs: `docker-compose logs -f`
- Run tests: `cd backend && pytest tests/ -v`
- Review documentation: See README.md
- File issues: [GitHub Issues](https://github.com/yourusername/air-quality-notebooklm/issues)
