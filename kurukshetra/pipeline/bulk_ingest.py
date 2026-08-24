from __future__ import annotations

from pathlib import Path

from kurukshetra.extractors.text_extractor import TextExtractor
from kurukshetra.pipeline.ingest import IngestionPipeline, IngestionResult


class BulkIngestionPipeline:
    """
    Bulk ingestion for folders of documents.

    Supports all file types the TextExtractor handles.
    """

    def __init__(self, build_embeddings: bool = False):
        self.pipeline = IngestionPipeline(build_embeddings=build_embeddings)
        self.supported = TextExtractor.supported_extensions()

    def ingest_folder(
        self, folder: Path, limit: int | None = None
    ) -> list[IngestionResult]:
        """Ingest all supported files from a folder."""
        files = sorted(
            f for f in folder.iterdir()
            if f.is_file() and f.suffix.lower() in self.supported
        )

        if limit:
            files = files[:limit]

        results: list[IngestionResult] = []

        for i, file_path in enumerate(files, start=1):
            print(f"[{i}/{len(files)}] {file_path.name}")
            result = self.pipeline.ingest(file_path)
            results.append(result)

            if result.error:
                print(f"  ERROR: {result.error}")
            else:
                print(f"  OK: {result.chunks_stored} chunks, "
                      f"{result.entities_extracted} entities")

        return results
