from __future__ import annotations

import json
from kurukshetra.registry.database import get_connection


class VectorRepository:
    def __init__(self):
        conn = get_connection()
        conn.execute("""
        CREATE TABLE IF NOT EXISTS vectors(
            chunk_id TEXT PRIMARY KEY,
            embedding TEXT
        )
        """)
        conn.close()

    def insert(self, chunk_id: str, vector: list[float]):
        conn = get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO vectors VALUES (?, ?)",
            (chunk_id, json.dumps(vector)),
        )
        conn.close()

    def load(self):
        conn = get_connection()
        rows = conn.execute(
            "SELECT chunk_id, embedding FROM vectors"
        ).fetchall()
        conn.close()

        return [
            (r[0], json.loads(r[1]))
            for r in rows
        ]