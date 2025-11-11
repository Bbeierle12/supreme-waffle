# Database Performance Optimization Guide

## Overview

This document explains the database optimization strategy for the Air Quality NotebookLM system.

## Architecture

### DuckDB with Parquet Storage

- **DuckDB**: OLAP-oriented database optimized for analytical queries
- **Parquet**: Columnar storage format with efficient compression
- **Date Partitioning**: Data partitioned by date for time-range query optimization

### Trade-offs

**Advantages:**
- Excellent query performance for analytical workloads
- Columnar storage reduces I/O for selective column reads
- Built-in Parquet support
- Low operational overhead (embedded database)

**Limitations:**
- Not optimized for concurrent writes (single writer)
- Indexes only work on tables, not on Parquet views
- Better suited for read-heavy workloads

## Indexes

### Table Indexes

Indexes have been created on the following tables:

#### Events Table
```sql
idx_events_start_ts      -- Time-based event queries
idx_events_type          -- Event type filtering
idx_events_type_start    -- Composite index for filtered time queries
```

#### Documents Table
```sql
idx_documents_path       -- Document path lookups
idx_documents_added_at   -- Recent documents queries
```

#### Chunks Table (RAG)
```sql
idx_chunks_doc_id        -- Document chunk retrieval
idx_chunks_page          -- Page-based queries
```

#### Lineage Table
```sql
idx_lineage_record_id    -- Record provenance
idx_lineage_table_name   -- Table-specific lineage
idx_lineage_fetched_at   -- Temporal lineage queries
idx_lineage_api_source   -- Source-based filtering
```

### Parquet Optimization

Since `observations_aq` and `observations_met` are **views** over Parquet files, traditional indexes don't apply. Instead, optimization relies on:

1. **Date Partitioning**: Files organized by date (`date=YYYY-MM-DD/`)
2. **Column Pruning**: DuckDB only reads requested columns
3. **Predicate Pushdown**: Filters applied at file scan level
4. **File Consolidation**: Periodic merging of small files

## Query Optimization Best Practices

### 1. Use Date Filters

**Good:**
```sql
SELECT * FROM observations_aq
WHERE ts BETWEEN '2024-01-01' AND '2024-01-07'
```

This leverages date partitioning and only reads relevant files.

**Bad:**
```sql
SELECT * FROM observations_aq
WHERE sensor_id = 'sensor_123'
```

This requires scanning all Parquet files.

### 2. Select Only Needed Columns

**Good:**
```sql
SELECT ts, pm25_corr FROM observations_aq WHERE ...
```

**Bad:**
```sql
SELECT * FROM observations_aq WHERE ...
```

### 3. Use Appropriate Aggregations

DuckDB excels at aggregations:

```sql
SELECT
    DATE_TRUNC('hour', ts) as hour,
    AVG(pm25_corr) as avg_pm25
FROM observations_aq
WHERE ts BETWEEN ? AND ?
GROUP BY hour
```

### 4. Leverage Partitioning in Application Code

When possible, construct queries that align with date partitions:

```python
# Good: Query within date boundaries
start = datetime(2024, 1, 1)
end = datetime(2024, 1, 7)
df = db.query("SELECT * FROM observations_aq WHERE ts BETWEEN ? AND ?",
              {"start": start, "end": end})

# Less efficient: Open-ended queries
df = db.query("SELECT * FROM observations_aq WHERE sensor_id = ?",
              {"sensor_id": "123"})
```

## Maintenance Tasks

### Periodic Optimization

Run these tasks periodically (e.g., daily via cron):

```python
from storage.database import get_db

db = get_db()

# 1. Consolidate small Parquet files
db.optimize_parquet_files()

# 2. Vacuum and analyze
db.vacuum()
```

### File Consolidation

The `optimize_parquet_files()` method:
- Identifies partitions with >10 files
- Consolidates them into a single file
- Sorts by timestamp for better compression
- Removes old files

**Benefits:**
- Fewer file opens during queries
- Better compression ratios
- Improved query latency

### Query Analysis

Use `explain_query()` to understand query plans:

```python
sql = """
    SELECT AVG(pm25_corr)
    FROM observations_aq
    WHERE ts > '2024-01-01'
"""

print(db.explain_query(sql))
```

## Performance Monitoring

### Key Metrics to Track

1. **Query Latency**
   - p50, p95, p99 response times
   - Track by query type

2. **Parquet File Stats**
   - Number of files per partition
   - Average file size
   - Total storage used

3. **Index Usage**
   - DuckDB provides query plans showing index usage

### Slow Query Detection

Log queries taking >1 second:

```python
import time
from logging_config import get_logger

logger = get_logger("db.performance")

start = time.time()
result = db.query(sql)
duration = time.time() - start

if duration > 1.0:
    logger.warning(f"Slow query ({duration:.2f}s): {sql[:100]}")
```

## Migration Considerations

### If Scaling Issues Arise

When DuckDB's single-writer limitation becomes a bottleneck, consider:

1. **PostgreSQL + TimescaleDB**
   - Better for concurrent writes
   - Automatic partitioning
   - Built-in time-series optimizations

2. **Hybrid Approach**
   - PostgreSQL for recent data (hot path)
   - Parquet for historical data (cold path)
   - Union queries across both

3. **ClickHouse**
   - Column-oriented OLAP database
   - Excellent for analytical queries
   - Better concurrency than DuckDB

## References

- [DuckDB Performance Guide](https://duckdb.org/docs/guides/performance/overview)
- [Parquet File Format](https://parquet.apache.org/docs/)
- [DuckDB Hive Partitioning](https://duckdb.org/docs/data/partitioning/hive_partitioning)
