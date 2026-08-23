"""
Self-Verification Question Generation
=====================================

System tests itself by:
1. Generating verification questions from ingested documents
2. Storing as golden Q&A pairs
3. Periodically re-running retrieval against these questions
4. Measuring accuracy degradation over time (knowledge decay detection)
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from kurukshetra.registry.database import get_connection


@dataclass(slots=True)
class VerificationQuestion:
    """A generated verification question with expected answer source."""
    question_id: str
    question: str
    source_document_id: str
    source_chunk_id: str
    expected_keywords: list[str]
    category: str
    difficulty: str  # easy, medium, hard
    created_at: str
    last_tested_at: Optional[str] = None
    last_accuracy: Optional[float] = None
    test_count: int = 0


@dataclass(slots=True)
class VerificationResult:
    """Result of testing the system's knowledge with a verification question."""
    question_id: str
    retrieved_correctly: bool
    top_score: float
    expected_found_in_top_k: bool
    latency_ms: float
    tested_at: str


class SelfVerifier:
    """
    Generates and manages self-verification questions.

    Periodically tests the system's knowledge and detects
    accuracy degradation (knowledge decay).
    """

    def __init__(self) -> None:
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create verification tables."""
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS verification_questions (
                question_id TEXT PRIMARY KEY,
                question TEXT,
                source_document_id TEXT,
                source_chunk_id TEXT,
                expected_keywords TEXT,
                category TEXT,
                difficulty TEXT,
                created_at TIMESTAMP,
                last_tested_at TIMESTAMP,
                last_accuracy DOUBLE,
                test_count INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS verification_results (
                result_id TEXT PRIMARY KEY,
                question_id TEXT,
                retrieved_correctly BOOLEAN,
                top_score DOUBLE,
                expected_found_in_top_k BOOLEAN,
                latency_ms DOUBLE,
                tested_at TIMESTAMP
            )
        """)
        conn.close()

    def generate_questions_from_text(
        self,
        text: str,
        document_id: str,
        max_questions: int = 5,
    ) -> list[VerificationQuestion]:
        """
        Generate verification questions from document text.

        Uses pattern-based question generation:
        - Process docs → "What are the steps to..."
        - Error docs → "How to resolve..."
        - Config docs → "What configuration is needed for..."
        """
        questions: list[VerificationQuestion] = []
        text_lower = text.lower()

        # Split into meaningful paragraphs
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 100]

        for i, para in enumerate(paragraphs[:max_questions]):
            # Extract key terms from paragraph
            keywords = self._extract_keywords(para)
            if not keywords:
                continue

            # Determine category and generate question
            category = self._classify_paragraph(para)

            if category == "process":
                question = self._generate_process_question(para, keywords)
            elif category == "error_resolution":
                question = self._generate_error_question(para, keywords)
            elif category == "configuration":
                question = self._generate_config_question(para, keywords)
            else:
                question = self._generate_general_question(para, keywords)

            if question:
                q_id = f"VQ-{document_id}-{i:03d}"
                questions.append(VerificationQuestion(
                    question_id=q_id,
                    question=question,
                    source_document_id=document_id,
                    source_chunk_id="",
                    expected_keywords=keywords[:5],
                    category=category,
                    difficulty="medium",
                    created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                ))

        # Store questions
        self._store_questions(questions)

        return questions

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract meaningful keywords from a text paragraph."""
        # Remove common words and extract significant terms
        words = re.findall(r"\b[A-Za-z]{4,}\b", text)
        word_freq: dict[str, int] = {}
        for word in words:
            w = word.lower()
            if w not in {"this", "that", "with", "from", "have", "been", "will",
                        "more", "when", "what", "your", "they", "than", "also",
                        "into", "some", "could", "other", "about", "which",
                        "their", "there", "were", "would", "should", "could",
                        "these", "those", "then", "each", "just", "over",
                        "such", "only", "very", "most", "some", "after",
                        "first", "step", "process", "following"}:
                word_freq[word] = word_freq.get(w, 0) + 1

        # Get most frequent meaningful words
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [w for w, _ in sorted_words[:8]]

    def _classify_paragraph(self, text: str) -> str:
        """Classify paragraph content type."""
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["step", "procedure", "process", "follow"]):
            return "process"
        elif any(kw in text_lower for kw in ["error", "failure", "resolve", "troubleshoot"]):
            return "error_resolution"
        elif any(kw in text_lower for kw in ["config", "setting", "parameter", "setup"]):
            return "configuration"
        else:
            return "general"

    def _generate_process_question(
        self, text: str, keywords: list[str]
    ) -> Optional[str]:
        """Generate a process-oriented question."""
        if len(keywords) < 2:
            return None
        topic = " and ".join(keywords[:2])
        return f"What are the steps to complete {topic}?"

    def _generate_error_question(
        self, text: str, keywords: list[str]
    ) -> Optional[str]:
        """Generate an error resolution question."""
        if len(keywords) < 2:
            return None
        topic = " and ".join(keywords[:2])
        return f"How to resolve issues with {topic}?"

    def _generate_config_question(
        self, text: str, keywords: list[str]
    ) -> Optional[str]:
        """Generate a configuration question."""
        if len(keywords) < 1:
            return None
        topic = keywords[0]
        return f"What configuration is needed for {topic}?"

    def _generate_general_question(
        self, text: str, keywords: list[str]
    ) -> Optional[str]:
        """Generate a general knowledge question."""
        if len(keywords) < 2:
            return None
        topic = " ".join(keywords[:2])
        return f"What is {topic} and how does it work?"

    def _store_questions(self, questions: list[VerificationQuestion]) -> None:
        """Store generated questions in the database."""
        conn = get_connection()
        for q in questions:
            conn.execute(
                """
                INSERT OR REPLACE INTO verification_questions
                (question_id, question, source_document_id, source_chunk_id,
                 expected_keywords, category, difficulty, created_at,
                 last_tested_at, last_accuracy, test_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0)
                """,
                (
                    q.question_id,
                    q.question,
                    q.source_document_id,
                    q.source_chunk_id,
                    json.dumps(q.expected_keywords),
                    q.category,
                    q.difficulty,
                    q.created_at,
                ),
            )
        conn.close()

    def record_verification(
        self,
        question_id: str,
        retrieved_correctly: bool,
        top_score: float,
        expected_found_in_top_k: bool,
        latency_ms: float,
    ) -> VerificationResult:
        """Record the result of a verification test."""
        result_id = f"VR-{question_id}-{int(time.time())}"
        tested_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        result = VerificationResult(
            question_id=question_id,
            retrieved_correctly=retrieved_correctly,
            top_score=top_score,
            expected_found_in_top_k=expected_found_in_top_k,
            latency_ms=latency_ms,
            tested_at=tested_at,
        )

        conn = get_connection()
        conn.execute(
            """
            INSERT INTO verification_results
            (result_id, question_id, retrieved_correctly, top_score,
             expected_found_in_top_k, latency_ms, tested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result_id,
                question_id,
                retrieved_correctly,
                top_score,
                expected_found_in_top_k,
                latency_ms,
                tested_at,
            ),
        )

        # Update question stats
        conn.execute(
            """
            UPDATE verification_questions
            SET last_tested_at = ?, test_count = test_count + 1,
                last_accuracy = ?
            WHERE question_id = ?
            """,
            (tested_at, top_score, question_id),
        )
        conn.close()

        return result

    def detect_knowledge_decay(
        self, accuracy_threshold: float = 0.5
    ) -> list[dict]:
        """
        Detect questions where accuracy has degraded over time.

        Returns questions that were previously accurate but are now failing.
        """
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT
                vq.question_id,
                vq.question,
                vq.source_document_id,
                vq.last_accuracy,
                vq.test_count,
                COUNT(vr.result_id) as total_tests,
                SUM(CASE WHEN vr.retrieved_correctly THEN 1 ELSE 0 END) as correct_count
            FROM verification_questions vq
            LEFT JOIN verification_results vr ON vq.question_id = vr.question_id
            WHERE vq.test_count > 0
            GROUP BY vq.question_id
            HAVING correct_count * 1.0 / total_tests < ?
            ORDER BY vq.last_accuracy DESC
            """,
            (accuracy_threshold,),
        ).fetchall()
        conn.close()

        return [
            {
                "question_id": r[0],
                "question": r[1],
                "source_document_id": r[2],
                "accuracy": round((r[5] and r[6] or 0) / max(r[5], 1), 3),
                "test_count": r[4],
            }
            for r in rows
        ]

    def get_verification_stats(self) -> dict:
        """Get overall verification statistics."""
        conn = get_connection()
        total_q = conn.execute(
            "SELECT COUNT(*) FROM verification_questions"
        ).fetchone()[0]
        tested_q = conn.execute(
            "SELECT COUNT(*) FROM verification_questions WHERE test_count > 0"
        ).fetchone()[0]
        total_vr = conn.execute(
            "SELECT COUNT(*) FROM verification_results"
        ).fetchone()[0]
        correct_vr = conn.execute(
            "SELECT COUNT(*) FROM verification_results WHERE retrieved_correctly = TRUE"
        ).fetchone()[0]
        conn.close()

        return {
            "total_questions": total_q,
            "tested_questions": tested_q,
            "total_verifications": total_vr,
            "correct_verifications": correct_vr,
            "overall_accuracy": round(
                (correct_vr / max(total_vr, 1)), 3
            ),
        }
