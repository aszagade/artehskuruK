from __future__ import annotations

from kurukshetra.embeddings import BGEEmbedding
from kurukshetra.registry.chunks import ChunkRepository
from kurukshetra.registry.vectors import VectorRepository


class VectorIndexer:
    def __init__(self):
        self.embedder = BGEEmbedding()
        self.chunk_repo = ChunkRepository()
        self.vector_repo = VectorRepository()

    def build(self):
        chunks = self.chunk_repo.load()

        for chunk in chunks:
            vector = self.embedder.embed(chunk.text)
            self.vector_repo.insert(chunk.chunk_id, vector)

        return len(chunks)