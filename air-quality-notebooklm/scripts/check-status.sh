#!/bin/bash
# Check system status

echo "==================================="
echo "Air Quality NotebookLM Status"
echo "==================================="
echo ""

# Check if backend is running
echo "Checking backend..."
if curl -s http://localhost:8000/ > /dev/null; then
    echo "✓ Backend is running"

    # Get detailed status
    STATUS=$(curl -s http://localhost:8000/status)
    echo ""
    echo "Backend Status:"
    echo "$STATUS" | python3 -m json.tool 2>/dev/null || echo "$STATUS"
else
    echo "✗ Backend is not running"
    echo "  Start it with: cd backend && python main.py"
fi

echo ""

# Check if frontend is running
echo "Checking frontend..."
if curl -s http://localhost:3000/ > /dev/null; then
    echo "✓ Frontend is running"
    echo "  Access at: http://localhost:3000"
else
    echo "✗ Frontend is not running"
    echo "  Start it with: cd frontend && npm run dev"
fi

echo ""

# Check data directory
echo "Checking data..."
if [ -d "data/parquet" ]; then
    PARQUET_COUNT=$(find data/parquet -name "*.parquet" 2>/dev/null | wc -l)
    echo "✓ Data directory exists"
    echo "  Parquet files: $PARQUET_COUNT"
else
    echo "⚠ Data directory not found"
fi

if [ -f "data/airquality.db" ]; then
    DB_SIZE=$(du -h data/airquality.db | cut -f1)
    echo "✓ Database exists ($DB_SIZE)"
else
    echo "⚠ Database not found (will be created on first run)"
fi

echo ""
echo "==================================="
