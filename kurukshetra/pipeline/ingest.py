from __future__ import annotations

from pathlib import Path

from kurukshetra.chunking.splitter import DeterministicSplitter
from kurukshetra.extractors import PDFExtractor
from kurukshetra.services import DocumentRegistrar
from kurukshetra.services.metadata import MetadataEnricher


class IngestionPipeline:
    def __init__(self) -> None:
        self.registrar = DocumentRegistrar()
        self.metadata = MetadataEnricher()
        self.extractor = PDFExtractor()
        self.splitter = DeterministicSplitter()

    def ingest(self, file_path: Path):
        text = self.extractor.extract(file_path)

        document = self.registrar.register(file_path)
        metadata = self.metadata.extract(file_path)
        chunks = self.splitter.split(document.document_id, text)

        return {
            "document": document,
            "metadata": metadata,
            "chunks": chunks,
        }