from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class DocumentIdentity:
    """
    Immutable identity assigned to every knowledge asset.
    """

    document_id: str
    file_name: str
    sha256: str
    file_size: int
    created_at: datetime