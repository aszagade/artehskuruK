from __future__ import annotations

from typing import List

from .models import Chunk


class DeterministicSplitter:
    """
    Character-based deterministic chunking.

    Produces identical chunks for identical input.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        overlap: int = 150,
    ) -> None:
        if overlap >= chunk_size:
            raise ValueError("Overlap must be smaller than chunk size.")

        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, document_id: str, text: str) -> List[Chunk]:
        chunks: List[Chunk] = []

        start = 0
        sequence = 1

        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunk_text = text[start:end]

            chunks.append(
                Chunk(
                    chunk_id=f"{document_id}-CH-{sequence:06d}",
                    document_id=document_id,
                    sequence=sequence,
                    text=chunk_text,
                    char_start=start,
                    char_end=end,
                )
            )

            if end == len(text):
                break

            start = end - self.overlap
            sequence += 1

        return chunks