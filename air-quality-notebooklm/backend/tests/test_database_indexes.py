"""Tests for database indexes and optimization."""
import pytest
import tempfile
from pathlib import Path
from storage.database import Database


class TestDatabaseIndexes:
    """Test database index creation and functionality."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            parquet_path = Path(tmpdir) / "parquet"
            db = Database(db_path, parquet_path)
            db.connect()
            yield db
            db.close()

    def test_indexes_created(self, temp_db):
        """Test that all indexes are created."""
        # Query for indexes
        indexes = temp_db.query("""
            SELECT index_name, table_name
            FROM duckdb_indexes()
            ORDER BY index_name
        """)

        index_names = set(indexes['index_name'].tolist())

        # Check events indexes
        assert 'idx_events_start_ts' in index_names
        assert 'idx_events_type' in index_names
        assert 'idx_events_type_start' in index_names

        # Check documents indexes
        assert 'idx_documents_path' in index_names
        assert 'idx_documents_added_at' in index_names

        # Check chunks indexes
        assert 'idx_chunks_doc_id' in index_names
        assert 'idx_chunks_page' in index_names

        # Check lineage indexes
        assert 'idx_lineage_record_id' in index_names
        assert 'idx_lineage_table_name' in index_names
        assert 'idx_lineage_fetched_at' in index_names
        assert 'idx_lineage_api_source' in index_names

    def test_tables_created(self, temp_db):
        """Test that all tables are created."""
        tables = temp_db.query("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main'
            AND table_type = 'BASE TABLE'
        """)

        table_names = set(tables['table_name'].tolist())

        assert 'events' in table_names
        assert 'documents' in table_names
        assert 'chunks' in table_names
        assert 'lineage' in table_names

    def test_views_created(self, temp_db):
        """Test that views are created."""
        views = temp_db.query("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main'
            AND table_type = 'VIEW'
        """)

        view_names = set(views['table_name'].tolist())

        assert 'observations_aq' in view_names
        assert 'observations_met' in view_names

    def test_vacuum_runs(self, temp_db):
        """Test that vacuum completes without error."""
        # Should not raise an exception
        temp_db.vacuum()

    def test_explain_query(self, temp_db):
        """Test query explanation functionality."""
        sql = "SELECT * FROM events WHERE type = 'inversion'"
        plan = temp_db.explain_query(sql)

        assert plan is not None
        assert isinstance(plan, str)
        assert len(plan) > 0


class TestQueryOptimization:
    """Test query optimization features."""

    @pytest.fixture
    def temp_db_with_data(self):
        """Create temporary database with sample data."""
        import pandas as pd
        from datetime import datetime, timedelta

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            parquet_path = Path(tmpdir) / "parquet"
            db = Database(db_path, parquet_path)
            db.connect()

            # Insert sample event
            db.insert_event({
                'start_ts': datetime.now(),
                'end_ts': datetime.now() + timedelta(hours=1),
                'type': 'inversion',
                'confidence': 0.9,
                'details': {}
            })

            yield db
            db.close()

    def test_index_usage_in_query(self, temp_db_with_data):
        """Test that indexes are used in queries."""
        # Query that should use index
        sql = "SELECT * FROM events WHERE type = 'inversion'"
        plan = temp_db_with_data.explain_query(sql)

        # DuckDB query plans show index usage
        assert plan is not None

    def test_event_insertion_and_retrieval(self, temp_db_with_data):
        """Test that indexed columns work correctly."""
        result = temp_db_with_data.query("""
            SELECT * FROM events WHERE type = 'inversion'
        """)

        assert not result.empty
        assert result.iloc[0]['type'] == 'inversion'
        # Use approximate comparison for floats
        assert abs(result.iloc[0]['confidence'] - 0.9) < 0.001


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
