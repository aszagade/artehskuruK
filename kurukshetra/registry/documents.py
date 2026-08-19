from __future__ import annotations

from kurukshetra.registry.database import get_connection


class DocumentRepository:
    def get(self, document_id: str):
        conn = get_connection()
        row = conn.execute(
            """
            SELECT document_id, title, source_path
            FROM documents
            WHERE document_id=?
            """,
            (document_id,),
        ).fetchone()
        conn.close()
        return row