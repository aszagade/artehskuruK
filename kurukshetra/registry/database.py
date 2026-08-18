from pathlib import Path
import duckdb

DATABASE_PATH = Path("kurukshetra_registry.duckdb")


def get_connection() -> duckdb.DuckDBPyConnection:
    """
    Return a reusable connection to the local KURUKSHETRA registry.
    """
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DATABASE_PATH))