from __future__ import annotations

from kurukshetra.chunking.models import Chunk
from .database import get_connection


class ChunkRepository:
    def __init__(self) -> None:
        self._ensure_table()

    def _ensure_table(self) -> None:
        conn = get_connection()
        conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            document_id TEXT,
            chunk_index INTEGER,
            text TEXT,
            start_offset INTEGER,
            end_offset INTEGER
        )
        """)
        conn.close()

    def insert(self, chunks: list[Chunk]) -> None:
        conn = get_connection()
        for c in chunks:
            conn.execute(
                """
                INSERT OR REPLACE INTO chunks (
                    chunk_id,
                    document_id,
                    chunk_index,
                    text,
                    start_offset,
                    end_offset
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    c.chunk_id,
                    c.document_id,
                    c.sequence,
                    c.text,
                    c.char_start,
                    c.char_end,
                ),
            )
        conn.close()

    def load(self) -> list[Chunk]:
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT chunk_id, document_id, chunk_index,
                   text, start_offset, end_offset
            FROM chunks
            ORDER BY document_id, chunk_index
            """
        ).fetchall()
        conn.close()

        return [
            Chunk(
                chunk_id=r[0],
                document_id=r[1],
                sequence=r[2],
                text=r[3],
                char_start=r[4],
                char_end=r[5],
            )
            for r in rows
        ]