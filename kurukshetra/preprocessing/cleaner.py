from __future__ import annotations

import re


class KnowledgeCleaner:
    """Normalize extracted CARE knowledge PDFs."""

    REMOVE_PATTERNS = [
        r"CARE Knowledge\s*Base",
        r"Knowledge Engine for CARE, by CARE!",
        r"Search by Category",
        r"All categories Search",
        r"Enter a search term.*",
        r"Recent Posts",
        r"All Articles.*",
        r"Select Category",
        r"Categories",
        r"📝",
    ]

    def clean(self, text: str) -> str:
        cleaned = text

        for pattern in self.REMOVE_PATTERNS:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        # Remove repeated blank lines and normalize spaces
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{2,}", "\n", cleaned)

        return cleaned.strip()