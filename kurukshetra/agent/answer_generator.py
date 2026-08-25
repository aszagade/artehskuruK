"""
Evidence-Grounded Answer Generator
===================================

Assembles retrieved evidence into answers with:
- Source citations and provenance
- Confidence scoring
- Conflict detection
- Abstention when evidence is insufficient
- Authorisation status tracking

Design principles:
- Every answer is grounded in retrieved evidence
- No facts are invented
- Conflicts are surfaced, not silently resolved
- Insufficient evidence triggers abstention
- Provenance is preserved for every claim
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from kurukshetra.retrieval.models import RetrievalResult


@dataclass(slots=True)
class Citation:
    """A single citation linking an answer claim to its source."""
    chunk_id: str
    document_id: str
    source_path: str
    text_snippet: str
    score: float
    rank: int


@dataclass(slots=True)
class EvidenceItem:
    """A piece of evidence from a retrieved chunk."""
    chunk_id: str
    document_id: str
    source_path: str
    text: str
    score: float
    rank: int
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class AnswerResult:
    """Complete answer with evidence, citations, and confidence."""
    query: str
    answer: str
    confidence: float              # 0.0 to 1.0
    abstained: bool                # True if evidence insufficient
    abstention_reason: str         # Why abstained (empty if not)
    evidence: list[EvidenceItem]   # Retrieved evidence used
    citations: list[Citation]      # Source citations
    source_documents: list[str]    # Unique source document IDs
    retrieval_strategy: str        # Which strategy was used
    authorization_status: str      # "authorized", "partial", "unauthorized"
    limitations: list[str]         # Known limitations of this answer
    conflicts: list[str]           # Detected conflicting evidence
    evidence_count: int = 0
    evidence_quality: str = "none"  # "strong", "moderate", "weak", "none"


# Minimum thresholds for providing an answer
MIN_EVIDENCE_COUNT = 1
MIN_CONFIDENCE_THRESHOLD = 0.2
MIN_SCORE_THRESHOLD = 0.1
MAX_ANSWER_LENGTH = 2000
MIN_QUERY_EVIDENCE_RELEVANCE = 0.30  # Min fraction of query terms found in evidence (co-occurrence weighted)


class AnswerGenerator:
    """
    Generates evidence-grounded answers from retrieved chunks.

    Uses extractive approach: selects and assembles the most relevant
    sentences from retrieved evidence. Does not hallucinate facts.
    """

    def generate(
        self,
        query: str,
        results: list[RetrievalResult],
        strategy: str = "hybrid",
        authorization_status: str = "authorized",
    ) -> AnswerResult:
        """
        Generate an answer from retrieved evidence.

        Args:
            query: The original user query
            results: Retrieved chunks (already filtered by visibility)
            strategy: Which retrieval strategy produced these results
            authorization_status: Whether evidence is authorized

        Returns:
            AnswerResult with answer, evidence, citations, confidence
        """
        # 1. Build evidence items from retrieval results
        evidence = self._build_evidence(results)

        # 2. Check if we have enough evidence
        if not evidence or len(evidence) < MIN_EVIDENCE_COUNT:
            return self._abstain(query, "No relevant evidence found", strategy,
                                 authorization_status)

        # 3. Check authorization
        if authorization_status == "unauthorized":
            return self._abstain(query, "No authorized evidence available", strategy,
                                 authorization_status)

        # 4. Validate query-evidence relevance
        relevance = self._validate_query_evidence_relevance(query, evidence)
        if relevance < MIN_QUERY_EVIDENCE_RELEVANCE:
            return self._abstain(
                query,
                f"Retrieved evidence does not contain sufficient information "
                f"about the query (relevance: {relevance:.2f})",
                strategy, authorization_status,
            )

        # 5. Detect conflicts
        conflicts = self._detect_conflicts(evidence)

        # 6. Extract answer sentences from evidence
        answer_sentences = self._extract_answer(query, evidence)

        # 7. Calculate confidence
        confidence = self._calculate_confidence(query, evidence, answer_sentences)

        # 8. If confidence too low, abstain
        if confidence < MIN_CONFIDENCE_THRESHOLD:
            return self._abstain(
                query,
                f"Insufficient evidence confidence ({confidence:.2f})",
                strategy, authorization_status,
            )

        # 8. Build citations
        citations = self._build_citations(evidence)

        # 9. Assemble final answer
        answer_text = self._assemble_answer(answer_sentences, evidence)

        # 10. Assess evidence quality
        quality = self._assess_evidence_quality(evidence)

        # 11. Identify limitations
        limitations = self._identify_limitations(query, evidence, confidence)

        source_docs = list(dict.fromkeys(e.document_id for e in evidence))

        return AnswerResult(
            query=query,
            answer=answer_text,
            confidence=round(confidence, 3),
            abstained=False,
            abstention_reason="",
            evidence=evidence,
            citations=citations,
            source_documents=source_docs,
            retrieval_strategy=strategy,
            authorization_status=authorization_status,
            limitations=limitations,
            conflicts=conflicts,
            evidence_count=len(evidence),
            evidence_quality=quality,
        )

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _build_evidence(self, results: list[RetrievalResult]) -> list[EvidenceItem]:
        """Convert retrieval results to evidence items."""
        evidence = []
        for rank, r in enumerate(results, 1):
            if r.score < MIN_SCORE_THRESHOLD:
                continue
            source_path = r.metadata.get("source_path", "")
            evidence.append(EvidenceItem(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                source_path=source_path,
                text=r.text,
                score=r.score,
                rank=rank,
                metadata=r.metadata,
            ))
        return evidence

    def _validate_query_evidence_relevance(
        self, query: str, evidence: list[EvidenceItem]
    ) -> float:
        """
        Validate that the evidence actually contains information about the query.

        Returns a relevance score (0.0-1.0) based on:
        1. What fraction of meaningful query terms appear in evidence
        2. Whether query terms co-occur in the same chunks (not just anywhere)
        """
        stop_words = {
            "what", "is", "the", "how", "do", "does", "a", "an",
            "to", "for", "in", "of", "and", "or", "can", "you",
            "are", "there", "this", "that", "it", "on", "at", "by",
            "be", "as", "with", "from", "or", "not",
        }
        query_tokens = set(query.lower().split()) - stop_words
        if not query_tokens:
            return 1.0  # No meaningful tokens to check

        # Factor 1: Global term presence
        evidence_text = " ".join(ev.text.lower() for ev in evidence)
        evidence_tokens = set(evidence_text.split())
        global_found = query_tokens & evidence_tokens
        global_relevance = len(global_found) / len(query_tokens)

        # Factor 2: Co-occurrence — do query terms appear together in chunks?
        # This catches cases where "budget" and "process" appear in different
        # unrelated documents
        max_cooccurrence = 0.0
        for ev in evidence:
            chunk_tokens = set(ev.text.lower().split())
            chunk_found = query_tokens & chunk_tokens
            cooccurrence = len(chunk_found) / len(query_tokens)
            max_cooccurrence = max(max_cooccurrence, cooccurrence)

        # Combined: require both global presence AND co-occurrence
        # Co-occurrence is weighted heavily — if no single chunk covers
        # the query well, the evidence is likely unrelated
        relevance = global_relevance * 0.4 + max_cooccurrence * 0.6

        return relevance

    def _extract_answer(self, query: str, evidence: list[EvidenceItem]) -> list[str]:
        """
        Extract the most relevant sentences from evidence.

        Deterministic extractive approach: score each sentence by
        keyword overlap with the query, then select top sentences.
        """
        query_tokens = set(query.lower().split())
        # Remove common stop words from query
        stop_words = {
            "what", "is", "the", "how", "do", "does", "a", "an",
            "to", "for", "in", "of", "and", "or", "can", "you",
            "are", "there", "this", "that", "it", "on", "at", "by",
        }
        meaningful_tokens = query_tokens - stop_words
        if not meaningful_tokens:
            meaningful_tokens = query_tokens

        scored_sentences: list[tuple[float, str, EvidenceItem]] = []

        for ev in evidence:
            # Split text into sentences
            sentences = self._split_sentences(ev.text)
            for sent in sentences:
                sent_lower = sent.lower()
                sent_tokens = set(sent_lower.split())
                # Score by keyword overlap
                overlap = len(meaningful_tokens & sent_tokens)
                # Bonus for longer, more informative sentences
                length_bonus = min(len(sent) / 200, 1.0)
                # Bonus for higher-ranked evidence
                rank_bonus = max(0, 1.0 - (ev.rank - 1) * 0.1)
                score = overlap * 0.5 + length_bonus * 0.2 + rank_bonus * 0.3

                if overlap > 0 and len(sent.strip()) > 20:
                    scored_sentences.append((score, sent.strip(), ev))

        # Sort by score and take top sentences
        scored_sentences.sort(key=lambda x: -x[0])

        # Deduplicate similar sentences
        seen = set()
        selected: list[str] = []
        for score, sent, ev in scored_sentences:
            # Simple dedup: skip if >60% token overlap with already selected
            sent_tokens = set(sent.lower().split())
            is_dup = False
            for s in selected:
                s_tokens = set(s.lower().split())
                if sent_tokens and s_tokens:
                    overlap = len(sent_tokens & s_tokens) / min(len(sent_tokens), len(s_tokens))
                    if overlap > 0.6:
                        is_dup = True
                        break
            if not is_dup:
                selected.append(sent)
                if len(selected) >= 5:
                    break

        return selected

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Split text into sentences deterministically."""
        # Handle common sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', text)
        # Also split on newlines that look like list items or steps
        expanded: list[str] = []
        for s in sentences:
            parts = re.split(r'\n\s*(?=\d+[\.\)]\s|[A-Z])', s)
            expanded.extend(p.strip() for p in parts if p.strip())
        return expanded

    def _calculate_confidence(
        self,
        query: str,
        evidence: list[EvidenceItem],
        answer_sentences: list[str],
    ) -> float:
        """
        Calculate confidence in the answer.

        Factors:
        - Number of evidence items
        - Score distribution
        - Whether multiple documents agree
        - Whether answer sentences are well-grounded
        """
        if not evidence or not answer_sentences:
            return 0.0

        # Factor 1: Evidence count (more evidence = more confidence)
        count_factor = min(len(evidence) / 3, 1.0)

        # Factor 2: Score quality (higher scores = more confidence)
        avg_score = sum(e.score for e in evidence) / len(evidence)
        score_factor = min(avg_score, 1.0)

        # Factor 3: Document diversity (multiple sources = more confidence)
        unique_docs = len(set(e.document_id for e in evidence))
        diversity_factor = min(unique_docs / 2, 1.0)

        # Factor 4: Answer coverage (more answer sentences = more coverage)
        coverage_factor = min(len(answer_sentences) / 3, 1.0)

        # Factor 5: Score consistency (low variance = more confidence)
        if len(evidence) > 1:
            scores = [e.score for e in evidence]
            mean_s = sum(scores) / len(scores)
            variance = sum((s - mean_s) ** 2 for s in scores) / len(scores)
            consistency_factor = max(0, 1.0 - variance * 5)
        else:
            consistency_factor = 0.5  # Single source = moderate

        # Weighted combination
        confidence = (
            count_factor * 0.20
            + score_factor * 0.25
            + diversity_factor * 0.20
            + coverage_factor * 0.15
            + consistency_factor * 0.20
        )

        return min(max(confidence, 0.0), 1.0)

    def _detect_conflicts(self, evidence: list[EvidenceItem]) -> list[str]:
        """
        Detect conflicting information in evidence.

        Simple heuristic: if evidence from different documents
        contains contradictory keywords about the same topic,
        flag as potential conflict.
        """
        conflicts: list[str] = []

        # Group evidence by document
        by_doc: dict[str, list[EvidenceItem]] = {}
        for ev in evidence:
            by_doc.setdefault(ev.document_id, []).append(ev)

        if len(by_doc) < 2:
            return conflicts

        # Check for negation patterns across documents
        negation_patterns = [
            (r'\bnot\s+\w+', r'\bis\s+\w+'),
            (r'\bshould\s+not\b', r'\bshould\b'),
            (r'\bdo\s+not\b', r'\bdo\b'),
            (r'\bdoes\s+not\b', r'\bdoes\b'),
        ]

        doc_texts = {
            doc_id: " ".join(ev.text.lower() for ev in evs)
            for doc_id, evs in by_doc.items()
        }

        doc_ids = list(doc_texts.keys())
        for i in range(len(doc_ids)):
            for j in range(i + 1, len(doc_ids)):
                text_a = doc_texts[doc_ids[i]]
                text_b = doc_texts[doc_ids[j]]
                for neg_pat, pos_pat in negation_patterns:
                    neg_matches_a = len(re.findall(neg_pat, text_a))
                    pos_matches_b = len(re.findall(pos_pat, text_b))
                    if neg_matches_a > 0 and pos_matches_b > 0:
                        conflicts.append(
                            f"Potential conflict between {doc_ids[i]} and {doc_ids[j]}: "
                            f"contradictory patterns detected"
                        )

        return conflicts[:5]  # Limit conflict count

    def _build_citations(self, evidence: list[EvidenceItem]) -> list[Citation]:
        """Build citation list from evidence."""
        citations: list[Citation] = []
        for ev in evidence:
            # Create a short snippet from the evidence text
            snippet = ev.text[:200].replace("\n", " ").strip()
            citations.append(Citation(
                chunk_id=ev.chunk_id,
                document_id=ev.document_id,
                source_path=ev.source_path,
                text_snippet=snippet,
                score=ev.score,
                rank=ev.rank,
            ))
        return citations

    def _assemble_answer(
        self, sentences: list[str], evidence: list[EvidenceItem]
    ) -> str:
        """Assemble final answer from extracted sentences."""
        if not sentences:
            return "No relevant information found in the knowledge base."

        # Join sentences with proper spacing
        answer = " ".join(sentences)

        # Truncate if too long
        if len(answer) > MAX_ANSWER_LENGTH:
            answer = answer[:MAX_ANSWER_LENGTH] + "..."

        return answer

    def _assess_evidence_quality(self, evidence: list[EvidenceItem]) -> str:
        """Assess overall quality of evidence."""
        if not evidence:
            return "none"

        avg_score = sum(e.score for e in evidence) / len(evidence)
        unique_docs = len(set(e.document_id for e in evidence))

        if avg_score > 0.5 and unique_docs >= 2:
            return "strong"
        elif avg_score > 0.3 and len(evidence) >= 2:
            return "moderate"
        elif avg_score > 0.1:
            return "weak"
        else:
            return "none"

    def _identify_limitations(
        self, query: str, evidence: list[EvidenceItem], confidence: float
    ) -> list[str]:
        """Identify limitations of the current answer."""
        limitations: list[str] = []

        if len(evidence) < 2:
            limitations.append("Answer based on a single source")

        if confidence < 0.5:
            limitations.append("Low confidence due to limited evidence")

        unique_docs = len(set(e.document_id for e in evidence))
        if unique_docs < 2:
            limitations.append("No cross-document corroboration")

        avg_score = sum(e.score for e in evidence) / len(evidence)
        if avg_score < 0.3:
            limitations.append("Evidence relevance scores are moderate")

        return limitations

    def _abstain(
        self,
        query: str,
        reason: str,
        strategy: str,
        authorization_status: str,
    ) -> AnswerResult:
        """Generate an abstention response."""
        return AnswerResult(
            query=query,
            answer=(
                "I cannot provide a confident answer to this question based on "
                "the available knowledge. "
                f"Reason: {reason}. "
                "Please consult the source documents directly or ask a more "
                "specific question."
            ),
            confidence=0.0,
            abstained=True,
            abstention_reason=reason,
            evidence=[],
            citations=[],
            source_documents=[],
            retrieval_strategy=strategy,
            authorization_status=authorization_status,
            limitations=["Insufficient evidence for this query"],
            conflicts=[],
            evidence_count=0,
            evidence_quality="none",
        )
