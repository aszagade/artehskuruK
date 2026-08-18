from __future__ import annotations

from pathlib import Path
import pdfplumber


class PDFExtractor:
    """Extract text from PDF files."""

    def extract(self, file_path: Path) -> str:
        if not file_path.exists():
            raise FileNotFoundError(file_path)

        pages: list[str] = []

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(text)

        return "\n".join(pages)