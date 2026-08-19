from __future__ import annotations

from pathlib import Path

from kurukshetra.pipeline.ingest import IngestionPipeline
from kurukshetra.registry.chunks import ChunkRepository


class BulkIngestionPipeline:
    def __init__(self):
        self.pipeline = IngestionPipeline()
        self.chunk_repo = ChunkRepository()

    def ingest_folder(self, folder: Path, limit: int | None = None):
        results = []

        pdfs = sorted(folder.glob("*.pdf"))

        if limit:
            pdfs = pdfs[:limit]

        for i, pdf in enumerate(pdfs, start=1):
            print(f"[{i}] {pdf.name}")

            result = self.pipeline.ingest(pdf)

            # SAVE CHUNKS TO DUCKDB
            self.chunk_repo.insert(result["chunks"])

            results.append(result)

        return results