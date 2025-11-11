"""DuckDB database management and query interface."""
import duckdb
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import pandas as pd


class Database:
    """DuckDB database interface with Parquet backing."""

    def __init__(self, db_path: Path, parquet_path: Path):
        """
        Initialize database connection.

        Args:
            db_path: Path to DuckDB database file
            parquet_path: Path to Parquet data directory
        """
        self.db_path = db_path
        self.parquet_path = parquet_path
        self.conn: Optional[duckdb.DuckDBPyConnection] = None

        # Ensure paths exist
        db_path.parent.mkdir(parents=True, exist_ok=True)
        parquet_path.mkdir(parents=True, exist_ok=True)

    def connect(self):
        """Open database connection."""
        if self.conn is None:
            self.conn = duckdb.connect(str(self.db_path))
            self._setup_schema()

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def _setup_schema(self):
        """Create database schema and views over Parquet files."""
        # Create views for each data type, handling case where no files exist yet
        try:
            self.conn.execute(f"""
                CREATE VIEW IF NOT EXISTS observations_aq AS
                SELECT * FROM read_parquet('{self.parquet_path}/aq/*.parquet',
                                           hive_partitioning=true,
                                           union_by_name=true)
            """)
        except Exception as e:
            # No parquet files yet, create empty view
            print(f"Warning: No AQ parquet files found, creating empty view: {e}")
            self.conn.execute("""
                CREATE VIEW IF NOT EXISTS observations_aq AS
                SELECT * FROM (VALUES
                    (NULL::TIMESTAMP, NULL::VARCHAR, NULL::VARCHAR, NULL::DOUBLE, NULL::DOUBLE,
                     NULL::DOUBLE, NULL::INTEGER, NULL::VARCHAR, NULL::DOUBLE, NULL::DOUBLE, NULL::JSON)
                ) t(ts, source, sensor_id, pm25_raw, pm25_corr, pm10_raw, qa_flags, "window", lat, lon, metadata)
                WHERE FALSE
            """)

        try:
            self.conn.execute(f"""
                CREATE VIEW IF NOT EXISTS observations_met AS
                SELECT * FROM read_parquet('{self.parquet_path}/met/*.parquet',
                                           hive_partitioning=true,
                                           union_by_name=true)
            """)
        except Exception as e:
            # No parquet files yet, create empty view
            print(f"Warning: No weather parquet files found, creating empty view: {e}")
            self.conn.execute("""
                CREATE VIEW IF NOT EXISTS observations_met AS
                SELECT * FROM (VALUES
                    (NULL::TIMESTAMP, NULL::VARCHAR, NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE,
                     NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE, NULL::VARCHAR,
                     NULL::DOUBLE, NULL::DOUBLE)
                ) t(ts, station_id, temp_c, rh, wind_speed_ms, wind_dir_deg, pressure_mb,
                    stability_idx, mixing_height_m, "window", lat, lon)
                WHERE FALSE
            """)

        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS events (
                start_ts TIMESTAMPTZ,
                end_ts TIMESTAMPTZ,
                type VARCHAR,
                confidence REAL,
                details JSON
            )
        """)

        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id VARCHAR PRIMARY KEY,
                title VARCHAR,
                path VARCHAR,
                checksum VARCHAR,
                added_at TIMESTAMPTZ
            )
        """)

        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id VARCHAR PRIMARY KEY,
                doc_id VARCHAR,
                page INTEGER,
                text VARCHAR,
                span VARCHAR,
                FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
            )
        """)

        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS lineage (
                record_id VARCHAR,
                table_name VARCHAR,
                raw_payload JSON,
                fetched_at TIMESTAMPTZ,
                api_source VARCHAR,
                api_version VARCHAR
            )
        """)

    def write_parquet(
        self,
        data: pd.DataFrame,
        data_type: str,
        partition_by: str = "date"
    ):
        """
        Write data to Parquet with partitioning.

        Args:
            data: DataFrame to write
            data_type: 'aq' or 'met'
            partition_by: Column to partition by (default 'date')
        """
        if data.empty:
            return

        # Ensure timestamp column exists
        if 'ts' not in data.columns:
            raise ValueError("DataFrame must have 'ts' column")

        # Add date partition column
        data['date'] = pd.to_datetime(data['ts']).dt.date

        # Write to partitioned Parquet
        output_dir = self.parquet_path / data_type
        output_dir.mkdir(parents=True, exist_ok=True)

        # Group by date and write separate files
        for date, group in data.groupby('date'):
            partition_dir = output_dir / f"date={date}"
            partition_dir.mkdir(parents=True, exist_ok=True)

            output_file = partition_dir / f"{datetime.now().timestamp()}.parquet"
            group.drop('date', axis=1).to_parquet(
                output_file,
                engine='pyarrow',
                compression='snappy',
                index=False
            )

    def query(self, sql: str, params: Optional[Dict] = None) -> pd.DataFrame:
        """
        Execute SQL query and return results as DataFrame.

        Args:
            sql: SQL query string
            params: Optional parameters for prepared statement

        Returns:
            Query results as DataFrame
        """
        if not self.conn:
            self.connect()

        if params:
            return self.conn.execute(sql, params).df()
        return self.conn.execute(sql).df()

    def insert_event(self, event: Dict[str, Any]):
        """Insert event into database."""
        if not self.conn:
            self.connect()

        self.conn.execute("""
            INSERT INTO events (start_ts, end_ts, type, confidence, details)
            VALUES (?, ?, ?, ?, ?)
        """, [
            event['start_ts'],
            event['end_ts'],
            event['type'],
            event['confidence'],
            event['details']
        ])

    def get_time_range(self, data_type: str = 'aq') -> tuple:
        """
        Get earliest and latest timestamps in database.

        Args:
            data_type: 'aq' or 'met'

        Returns:
            (min_ts, max_ts) tuple
        """
        table = f"observations_{data_type}"
        result = self.query(f"SELECT MIN(ts) as min_ts, MAX(ts) as max_ts FROM {table}")

        if result.empty:
            return None, None

        return result.iloc[0]['min_ts'], result.iloc[0]['max_ts']

    def get_sensors(self, location: str = None) -> List[str]:
        """Get list of unique sensor IDs."""
        sql = "SELECT DISTINCT sensor_id FROM observations_aq"
        if location:
            sql += f" WHERE location = '{location}'"

        result = self.query(sql)
        return result['sensor_id'].tolist()

    def vacuum(self):
        """Optimize database and reclaim space."""
        if not self.conn:
            self.connect()
        self.conn.execute("VACUUM")
        self.conn.execute("ANALYZE")


# Global database instance
_db: Optional[Database] = None


def get_db(db_path: Path = None, parquet_path: Path = None) -> Database:
    """Get global database instance (singleton pattern)."""
    global _db

    if _db is None:
        if db_path is None or parquet_path is None:
            from config import settings
            db_path = settings.database_path
            parquet_path = settings.parquet_path

        _db = Database(db_path, parquet_path)
        _db.connect()

    return _db
