from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import mimetypes


@dataclass(slots=True)
class FileMetadata:
    extension: str
    mime_type: str
    file_size: int
    created_at: datetime
    modified_at: datetime


class MetadataEnricher:
    """
    Extract deterministic metadata from a file.
    """

    def extract(self, file_path: Path) -> FileMetadata:
        if not file_path.exists():
            raise FileNotFoundError(file_path)

        stat = file_path.stat()
        mime, _ = mimetypes.guess_type(file_path)

        return FileMetadata(
            extension=file_path.suffix.lower(),
            mime_type=mime or "application/octet-stream",
            file_size=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_ctime),
            modified_at=datetime.fromtimestamp(stat.st_mtime),
        )