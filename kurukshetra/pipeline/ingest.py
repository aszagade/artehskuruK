from __future__ import annotations

from pathlib import Path

from kurukshetra.chunking.splitter import DeterministicSplitter
from kurukshetra.services import DocumentRegistrar
from kurukshetra.services.metadata import MetadataEnricher


class IngestionPipeline:
    def __init__(self) -> None:
        self.registrar = DocumentRegistrar()
        self.metadata = MetadataEnricher()
        self.splitter = DeterministicSplitter()

    def ingest(self, file_path: Path, text: str):
        doc = self.registrar.register(file_path)
        meta = self.metadata.extract(file_path)
        chunks = self.splitter.split(doc.document_id, text)

        return {
            "document": doc,
            "metadata": meta,
            "chunks": chunks,
        }