from dataclasses import dataclass


@dataclass(slots=True)
class Chunk:
    """
    Atomic unit of knowledge used by retrieval engines.
    """

    chunk_id: str
    document_id: str
    sequence: int
    text: str
    char_start: int
    char_end: int