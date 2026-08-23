"""
Semantic Chunking Engine
========================

Document-aware chunking that respects structural boundaries:
- Section headings and subheadings
- Numbered steps and procedures
- Paragraph boundaries
- Table structures
- Preserves metadata about chunk context
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .models import Chunk


class ChunkGranularity(Enum):
    """Level of chunking granularity."""
    SECTION = "section"       # Split by major sections
    PARAGRAPH = "paragraph"   # Split by paragraphs
    SENTENCE = "sentence"     # Split by sentences
    HYBRID = "hybrid"         # Adaptive based on content


@dataclass(slots=True)
class SemanticChunk(Chunk):
    """Enhanced chunk with structural metadata."""
    section_heading: str = ""
    parent_heading: str = ""
    chunk_type: str = "text"  # text, heading, list, table, step
    has_code: bool = False
    has_numbers: bool = False
    confidence: float = 1.0


# ---------------------------------------------------------------------------
# Patterns for document structure detection
# ---------------------------------------------------------------------------

HEADING_PATTERNS = [
    # Markdown headings
    re.compile(r"^#{1,6}\s+.+", re.MULTILINE),
    # ALL CAPS lines (likely headings)
    re.compile(r"^[A-Z][A-Z\s\-:]{5,}$", re.MULTILINE),
    # Numbered headings like "1. Title" or "1.1 Title"
    re.compile(r"^\d+(?:\.\d+)*\s+[A-Z].*", re.MULTILINE),
    # Lines ending with colon that are short (likely subheadings)
    re.compile(r"^[A-Z][^.!?]{3,50}:\s*$", re.MULTILINE),
]

STEP_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:Step\s+\d+|"
    r"\d+\)\s+|"
    r"-\s+|"
    r"•\s+|"
    r"►\s+|"
    r"→\s+)",
    re.MULTILINE,
)

CODE_PATTERN = re.compile(
    r"(?:```|`[^`]+`|SELECT\s|CREATE\s|INSERT\s|UPDATE\s|DELETE\s|"
    r"import\s|def\s|class\s|function\s|if\s*\(|for\s*\()",
    re.IGNORECASE,
)

NUMBER_PATTERN = re.compile(r"\b\d{2,}\b")

TABLE_PATTERN = re.compile(r"\|.*\|.*\|")

LIST_ITEM_PATTERN = re.compile(
    r"^\s*(?:[-•►→*]\s+|\d+[.)]\s+)",
    re.MULTILINE,
)


def _is_heading(line: str) -> bool:
    """Check if a line is a section heading."""
    stripped = line.strip()
    if not stripped:
        return False

    for pattern in HEADING_PATTERNS:
        if pattern.match(stripped):
            return True

    return False


def _classify_line(line: str) -> str:
    """Classify a line's structural type."""
    stripped = line.strip()
    if not stripped:
        return "blank"
    if _is_heading(stripped):
        return "heading"
    if TABLE_PATTERN.search(stripped):
        return "table"
    if STEP_PATTERN.match(stripped):
        return "step"
    if LIST_ITEM_PATTERN.match(stripped):
        return "list"
    return "text"


def _split_into_sections(text: str) -> list[dict]:
    """
    Split document text into sections based on heading detection.

    Returns list of dicts with 'heading', 'level', and 'content' keys.
    """
    lines = text.split("\n")
    sections: list[dict] = []
    current_heading = ""
    current_level = 0
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        if _is_heading(stripped):
            # Save previous section
            if current_lines or current_heading:
                sections.append({
                    "heading": current_heading,
                    "level": current_level,
                    "content": "\n".join(current_lines).strip(),
                })

            # Determine heading level
            if stripped.startswith("#"):
                level = len(stripped) - len(stripped.lstrip("#"))
            elif re.match(r"^\d+(?:\.\d+)*\s", stripped):
                dots = stripped.split()[0].count(".")
                level = dots + 1
            else:
                level = 1

            current_heading = stripped
            current_level = level
            current_lines = []
        else:
            current_lines.append(line)

    # Don't forget the last section
    if current_lines or current_heading:
        sections.append({
            "heading": current_heading,
            "level": current_level,
            "content": "\n".join(current_lines).strip(),
        })

    return sections


def _split_section_into_chunks(
    section_content: str,
    section_heading: str,
    parent_heading: str,
    max_chunk_size: int = 1000,
    min_chunk_size: int = 200,
    overlap: int = 150,
) -> list[dict]:
    """
    Split a section's content into appropriately sized chunks.
    Respects paragraph and sentence boundaries.
    """
    if not section_content.strip():
        return []

    chunks = []

    # Split by double newline (paragraphs)
    paragraphs = re.split(r"\n\s*\n", section_content)
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # If single paragraph exceeds max, split by sentences
        if len(para) > max_chunk_size:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""

            # Split by sentence boundaries
            sentences = re.split(r"(?<=[.!?])\s+", para)
            for sentence in sentences:
                if len(current_chunk) + len(sentence) > max_chunk_size:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = sentence
                else:
                    current_chunk = (
                        f"{current_chunk} {sentence}" if current_chunk else sentence
                    )
        elif len(current_chunk) + len(para) + 2 > max_chunk_size:
            # Would exceed max with this paragraph
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = para
        else:
            current_chunk = (
                f"{current_chunk}\n\n{para}" if current_chunk else para
            )

    if current_chunk:
        chunks.append(current_chunk)

    # Apply overlap between chunks
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_text = chunks[i - 1]
            overlap_text = prev_text[-overlap:] if len(prev_text) > overlap else prev_text
            # Find a clean break point in the overlap text
            break_idx = overlap_text.rfind(". ")
            if break_idx > 0:
                overlap_text = overlap_text[break_idx + 2 :]
            overlapped.append(f"{overlap_text} {chunks[i]}")
        chunks = overlapped

    return chunks


class SemanticSplitter:
    """
    Document-aware chunking that respects structural boundaries.

    Produces chunks that:
    - Never split mid-sentence
    - Respect section headings and hierarchy
    - Preserve step-by-step procedures as complete units
    - Include structural metadata for each chunk
    """

    def __init__(
        self,
        max_chunk_size: int = 1000,
        min_chunk_size: int = 200,
        overlap: int = 150,
        granularity: ChunkGranularity = ChunkGranularity.HYBRID,
    ) -> None:
        if overlap >= max_chunk_size:
            raise ValueError("Overlap must be smaller than chunk size.")
        if min_chunk_size > max_chunk_size:
            raise ValueError("Min chunk size cannot exceed max chunk size.")

        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.overlap = overlap
        self.granularity = granularity

    def split(self, document_id: str, text: str) -> list[SemanticChunk]:
        """
        Split document text into semantically meaningful chunks.

        Args:
            document_id: Unique document identifier
            text: Full document text

        Returns:
            List of SemanticChunk with structural metadata
        """
        if not text.strip():
            return []

        sections = _split_into_sections(text)
        all_chunks: list[SemanticChunk] = []
        sequence = 1

        parent_heading = ""

        for section in sections:
            heading = section["heading"]
            content = section["content"]

            # Track parent heading based on level
            if section["level"] <= 1:
                parent_heading = heading

            # Split section into sized chunks
            raw_chunks = _split_section_into_chunks(
                content,
                heading,
                parent_heading,
                self.max_chunk_size,
                self.min_chunk_size,
                self.overlap,
            )

            for chunk_text in raw_chunks:
                if not chunk_text.strip():
                    continue

                chunk_type = "text"
                has_code = bool(CODE_PATTERN.search(chunk_text))
                has_numbers = bool(NUMBER_PATTERN.search(chunk_text))

                if STEP_PATTERN.search(chunk_text):
                    chunk_type = "step"
                elif TABLE_PATTERN.search(chunk_text):
                    chunk_type = "table"
                elif LIST_ITEM_PATTERN.search(chunk_text):
                    chunk_type = "list"

                # Calculate confidence based on chunk quality
                confidence = self._calculate_chunk_confidence(
                    chunk_text, heading, chunk_type
                )

                char_start = text.find(chunk_text[:50])
                if char_start == -1:
                    char_start = 0
                char_end = char_start + len(chunk_text)

                all_chunks.append(
                    SemanticChunk(
                        chunk_id=f"{document_id}-SC-{sequence:06d}",
                        document_id=document_id,
                        sequence=sequence,
                        text=chunk_text,
                        char_start=char_start,
                        char_end=char_end,
                        section_heading=heading,
                        parent_heading=parent_heading,
                        chunk_type=chunk_type,
                        has_code=has_code,
                        has_numbers=has_numbers,
                        confidence=confidence,
                    )
                )
                sequence += 1

        return all_chunks

    def _calculate_chunk_confidence(
        self, chunk_text: str, heading: str, chunk_type: str
    ) -> float:
        """
        Calculate confidence score for chunk quality.

        Higher confidence = more self-contained, more useful for retrieval.
        """
        confidence = 1.0

        # Penalize very short chunks
        if len(chunk_text) < self.min_chunk_size:
            confidence *= 0.7

        # Boost chunks with headings (more context)
        if heading:
            confidence *= 1.1

        # Boost procedural steps (high-value for SOP queries)
        if chunk_type == "step":
            confidence *= 1.15

        # Boost chunks with both text and numbers (likely procedures)
        has_alpha = any(c.isalpha() for c in chunk_text)
        has_nums = bool(NUMBER_PATTERN.search(chunk_text))
        if has_alpha and has_nums:
            confidence *= 1.05

        # Penalize chunks that are mostly whitespace or punctuation
        alpha_ratio = sum(c.isalpha() for c in chunk_text) / max(len(chunk_text), 1)
        if alpha_ratio < 0.3:
            confidence *= 0.5

        return min(confidence, 1.0)
