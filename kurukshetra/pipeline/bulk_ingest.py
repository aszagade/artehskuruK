from __future__ import annotations

from pathlib import Path

from .ingest import IngestionPipeline


class BulkIngestionPipeline:
    def __init__(self) -> None:
        self.pipeline = IngestionPipeline()

    def ingest_folder(self, folder: Path, limit: int | None = None):
        results = []
    
        for i, pdf in enumerate(sorted(folder.rglob("*.pdf")), start=1):
            if limit and i > limit:
                break
            
            print(f"[{i}] {pdf.name}")
    
            try:
                results.append(self.pipeline.ingest(pdf))
            except Exception as e:
                print(f"Skipped: {e}")
    
        return results