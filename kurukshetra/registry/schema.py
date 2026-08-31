from .database import get_connection


def initialize_schema() -> None:
    """
    Create the core Knowledge Registry schema.
    """
    conn = get_connection()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        document_id TEXT PRIMARY KEY,
        title TEXT,
        team_owner TEXT,
        document_type TEXT,
        visibility TEXT,
        version TEXT,
        sha256 TEXT UNIQUE,
        source_path TEXT,
        last_updated TIMESTAMP
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS agents (
        agent_id TEXT PRIMARY KEY,
        name TEXT,
        parent_agent TEXT,
        role TEXT,
        version TEXT,
        status TEXT
    );
    """)

    # Ensure quality columns exist on graph_entities (migration)
    for col_def in [
        "ALTER TABLE graph_entities ADD COLUMN quality_score DOUBLE DEFAULT 0.5",
        "ALTER TABLE graph_entities ADD COLUMN quality_label VARCHAR DEFAULT 'MEDIUM'",
    ]:
        try:
            conn.execute(col_def)
        except Exception:
            pass  # column already exists

    conn.close()