from __future__ import annotations

from datetime import datetime
from pathlib import Path

from kurukshetra.identity import (
    DocumentIdentity,
    create_document_id,
    generate_sha256,
)
from kurukshetra.registry import get_connection


class DocumentRegistrar:
    """Registers knowledge assets into the KURUKSHETRA Registry."""

    def register(self, file_path: Path) -> DocumentIdentity:
        if not file_path.exists():
            raise FileNotFoundError(file_path)

        conn = get_connection()
        sha = generate_sha256(file_path)

        # Return existing document if already registered
        existing = conn.execute(
            "SELECT document_id FROM documents WHERE sha256 = ?",
            (sha,),
        ).fetchone()

        if existing:
            conn.close()
            return DocumentIdentity(
                document_id=existing[0],
                file_name=file_path.name,
                sha256=sha,
                file_size=file_path.stat().st_size,
                created_at=datetime.utcnow(),
            )

        sequence = (
            conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] + 1
        )

        identity = DocumentIdentity(
            document_id=create_document_id(sequence),
            file_name=file_path.name,
            sha256=sha,
            file_size=file_path.stat().st_size,
            created_at=datetime.utcnow(),
        )

        conn.execute(
            """
            INSERT INTO documents (
                document_id,
                title,
                team_owner,
                document_type,
                visibility,
                version,
                sha256,
                source_path,
                last_updated
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity.document_id,
                identity.file_name,
                "UNKNOWN",
                "UNKNOWN",
                "Internal",
                "1.0.0",
                identity.sha256,
                str(file_path),
                identity.created_at,
            ),
        )

        conn.close()
        return identity