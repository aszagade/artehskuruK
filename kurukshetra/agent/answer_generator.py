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
    knowledge_source: str = "organization"  # "organization", "conversation", "procedure", "model", "mixed"
    # Claim verification (populated by orchestrator after answer generation)
    verification_verdict: str = ""  # "PASS", "PARTIAL", "FAIL"
    direct_claims: int = 0
    inferred_claims: int = 0
    unsupported_claims: int = 0


# Minimum thresholds for providing an answer
MIN_EVIDENCE_COUNT = 1
MIN_CONFIDENCE_THRESHOLD = 0.2
MIN_SCORE_THRESHOLD = 0.1
MAX_ANSWER_LENGTH = 2000
MIN_QUERY_EVIDENCE_RELEVANCE = 0.45  # Min fraction of query terms found in evidence (co-occurrence weighted)
# Semantic grounding: require the query's CORE meaning to be present, not just incidental tokens
# A query like "What is the company annual revenue" has core meaning in {company, annual, revenue}
# but generic tokens like "annual" appear in many unrelated documents ("annual health checkup")
QUERY_MIN_CONTENT_TOKENS = 2  # Minimum non-trivial content tokens that must co-occur

# Mention-vs-answer detection: question patterns that require specific answer types
_MVA_COUNT_PATTERN = re.compile(r"\b(how many|number of|total count|count of)\b", re.IGNORECASE)
_MVA_WHO_PATTERN = re.compile(r"\b(who|which team|which person)\b", re.IGNORECASE)
_MVA_WHEN_PATTERN = re.compile(r"\b(when|what date|what year)\b", re.IGNORECASE)
_MVA_SALARY_PATTERN = re.compile(r"\b(salary|wage|compensation|pay range|pay scale)\b", re.IGNORECASE)
_MVA_ANSWER_NUMBER = re.compile(r"\b\d[\d,]*\b")
# Domain-specific phrases that indicate genuine topic coverage
# If none of these appear, the evidence is likely incidental keyword overlap


class AnswerGenerator:
    """
    Generates evidence-grounded answers from retrieved chunks.

    Uses extractive approach by default. When an LLM client is provided,
    the LLM generates a natural-language answer grounded in the same evidence.
    Falls back to extractive if the LLM is unavailable or fails.
    """

    def generate(
        self,
        query: str,
        results: list[RetrievalResult],
        strategy: str = "hybrid",
        authorization_status: str = "authorized",
        llm_client=None,
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
        # 0. Entity-aware retrieval augmentation
        results = self._augment_with_entity_results(query, results)

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
        # Skip relevance check if entity augmentation provided evidence
        has_entity_evidence = any(
            e.metadata.get("source") == "entity_lookup" for e in evidence
        )
        if has_entity_evidence:
            relevance = 1.0  # Entity match is inherently relevant
        else:
            relevance = self._validate_query_evidence_relevance(query, evidence)
            if relevance < MIN_QUERY_EVIDENCE_RELEVANCE:
                return self._abstain(
                    query,
                    f"Retrieved evidence does not contain sufficient information "
                    f"about the query (relevance: {relevance:.2f})",
                    strategy, authorization_status,
                )

        # 5. Mention-vs-answer detection
        mva_penalty = self._detect_mention_vs_answer(query, evidence)
        if mva_penalty > 0.5:
            # Evidence mentions the topic but doesn't actually answer the question
            # Check if there's a more specific answer possible
            # For count questions: check if evidence has numbers in answer context
            return self._abstain(
                query,
                f"Retrieved evidence mentions the topic but does not contain "
                f"sufficient information to answer this specific question",
                strategy, authorization_status,
            )

        # 6. Detect conflicts
        conflicts = self._detect_conflicts(evidence)

        # 7. Build citations and evidence quality (needed by both paths)
        citations = self._build_citations(evidence)
        quality = self._assess_evidence_quality(evidence)
        source_docs = list(dict.fromkeys(e.document_id for e in evidence))

        # 7. Try LLM first if available (primary path)
        answer_text = ""
        confidence = 0.0
        llm_used = False
        if llm_client is not None and llm_client.is_available:
            llm_answer = self._generate_llm_answer(query, evidence, llm_client)
            if llm_answer and llm_answer.strip():
                answer_text = llm_answer
                llm_used = True
                # LLM answers get base confidence from evidence quality
                confidence = self._calculate_confidence(query, evidence, [])
                confidence = max(confidence, 0.5)  # LLM with evidence >= 0.5

        # 8. Extractive fallback if LLM didn't produce an answer
        if not answer_text:
            answer_sentences = self._extract_answer(query, evidence)
            confidence = self._calculate_confidence(query, evidence, answer_sentences)

            if confidence < MIN_CONFIDENCE_THRESHOLD:
                return self._abstain(
                    query,
                    f"Insufficient evidence confidence ({confidence:.2f})",
                    strategy, authorization_status,
                )
            answer_text = self._assemble_answer(answer_sentences, evidence)

        # 9. Limitations
        limitations = self._identify_limitations(query, evidence, confidence)
        if llm_used:
            limitations = ["Answer generated by LLM; verify against cited sources"] + limitations

        source_docs = list(dict.fromkeys(e.document_id for e in evidence))

        # Determine knowledge source
        knowledge_source = self._determine_knowledge_source(
            evidence, has_entity_evidence, llm_used
        )

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
            knowledge_source=knowledge_source,
        )

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _augment_with_entity_results(
        self, query: str, results: list[RetrievalResult]
    ) -> list[RetrievalResult]:
        """
        Augment retrieval results with entity-based document lookup.

        When the query is about a known entity (team, system), fetch
        additional documents from the graph and add them to results.
        """
        import re
        from kurukshetra.registry.database import get_connection

        # Detect entity queries
        entity_patterns = {
            'team': r'\b(ICS|SPM|ROA|SDOPS|IT|HR|CPM|PMO|NOC)\b',
            'system': r'\b(G3|RMS|Opera|OHIP|FOLS|SFDC|Demand360|NGI|Optix)\b',
        }

        detected_entities = []
        for etype, pattern in entity_patterns.items():
            matches = re.findall(pattern, query, re.IGNORECASE)
            for m in matches:
                detected_entities.append((m.upper(), etype))

        if not detected_entities:
            return results

        # Fetch related documents from graph
        try:
            conn = get_connection()
            existing_doc_ids = {r.document_id for r in results}
            new_results = []

            for entity_name, entity_type in detected_entities:
                # Find documents by team_owner (for team entities)
                team_rows = conn.execute(
                    """SELECT document_id FROM documents
                    WHERE UPPER(team_owner) = ?
                    LIMIT 5""",
                    (entity_name.upper(),),
                ).fetchall()

                for row in team_rows:
                    doc_id = row[0]
                    if doc_id and doc_id not in existing_doc_ids:
                        chunk_row = conn.execute(
                            """SELECT chunk_id, document_id, text
                            FROM chunks WHERE document_id = ?
                            LIMIT 1""",
                            (doc_id,),
                        ).fetchone()
                        if chunk_row:
                            new_results.append(RetrievalResult(
                                chunk_id=chunk_row[0],
                                document_id=chunk_row[1],
                                score=0.45,
                                text=chunk_row[2],
                                metadata={"source": "entity_lookup", "entity": entity_name},
                            ))
                            existing_doc_ids.add(doc_id)

                # Also find documents containing this entity in graph
                # Only use entities with quality_score >= 0.4 (MEDIUM or above)
                graph_rows = conn.execute(
                    """SELECT DISTINCT ge.owner
                    FROM graph_entities ge
                    WHERE ge.name LIKE ?
                    AND ge.owner IS NOT NULL
                    AND ge.owner != ''
                    AND LENGTH(ge.owner) > 3
                    AND (ge.quality_score IS NULL OR ge.quality_score >= 0.4)
                    LIMIT 5""",
                    (f"%{entity_name}%",),
                ).fetchall()

                for row in graph_rows:
                    doc_id = row[0]
                    if doc_id and doc_id not in existing_doc_ids and doc_id.startswith("DOC-"):
                        chunk_row = conn.execute(
                            """SELECT chunk_id, document_id, text
                            FROM chunks WHERE document_id = ?
                            LIMIT 1""",
                            (doc_id,),
                        ).fetchone()
                        if chunk_row:
                            new_results.append(RetrievalResult(
                                chunk_id=chunk_row[0],
                                document_id=chunk_row[1],
                                score=0.45,
                                text=chunk_row[2],
                                metadata={"source": "entity_lookup", "entity": entity_name},
                            ))
                            existing_doc_ids.add(doc_id)

            conn.close()

            # Combine: original results + entity-augmented results
            if new_results:
                return results + new_results[:5]  # Limit augmentation

        except Exception:
            pass  # Graceful fallback

        return results

    def _generate_llm_answer(
        self, query: str, evidence: list[EvidenceItem], llm_client
    ) -> str:
        """
        Generate a natural-language answer using the LLM, grounded in evidence.

        Returns the LLM response text, or empty string on failure.
        """
        from kurukshetra.llm.client import ChatMessage, SYSTEM_PROMPT_GROUNDED

        # Build evidence context for the LLM
        evidence_text = self._format_evidence_for_llm(evidence)

        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT_GROUNDED),
            ChatMessage(
                role="user",
                content=(
                    f"Based on the following evidence from the knowledge base, "
                    f"answer the question below. If the evidence is insufficient, "
                    f"say so. Cite source documents where possible.\n\n"
                    f"QUESTION: {query}\n\n"
                    f"EVIDENCE:\n{evidence_text}"
                ),
            ),
        ]

        result = llm_client.chat(messages)

        if result.success and result.content.strip():
            return result.content.strip()
        return ""

    def _format_evidence_for_llm(self, evidence: list[EvidenceItem]) -> str:
        """Format evidence items into a structured context string for the LLM.

        Includes document title, team, and source path to help the LLM
        understand which organization/team owns each piece of evidence.
        """
        # Look up document titles and teams
        doc_info: dict[str, dict] = {}
        try:
            from kurukshetra.registry.database import get_connection
            conn = get_connection()
            seen = set()
            for e in evidence:
                if e.document_id not in seen:
                    seen.add(e.document_id)
                    row = conn.execute(
                        "SELECT title, team_owner FROM documents WHERE document_id = ?",
                        (e.document_id,),
                    ).fetchone()
                    if row:
                        doc_info[e.document_id] = {
                            "title": row[0] or e.document_id,
                            "team": row[1] or "unknown",
                        }
            conn.close()
        except Exception:
            pass

        parts = []
        for i, e in enumerate(evidence[:10], 1):  # Limit to top 10
            info = doc_info.get(e.document_id, {})
            title = info.get("title", e.document_id)
            team = info.get("team", "unknown")
            source = e.source_path or e.document_id
            # Truncate long evidence snippets
            text = e.text[:600] + "..." if len(e.text) > 600 else e.text
            parts.append(
                f"[Source {i}: {title}] [Team: {team}] [File: {source}]\n{text}"
            )
        return "\n\n".join(parts)

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
        3. Whether the evidence source documents are topically aligned
        4. Whether retrieval scores indicate genuine relevance
        """
        stop_words = {
            "what", "is", "the", "how", "do", "does", "a", "an",
            "to", "for", "in", "of", "and", "or", "can", "you",
            "are", "there", "this", "that", "it", "on", "at", "by",
            "be", "as", "with", "from", "or", "not",
        }
        # Strip punctuation from tokens (e.g., "configuration?" → "configuration")
        raw_tokens = set(query.lower().split()) - stop_words
        query_tokens = set()
        for t in raw_tokens:
            cleaned = t.strip(".,?!;:'\"\"()")
            if cleaned:
                query_tokens.add(cleaned)
        if not query_tokens:
            return 1.0  # No meaningful tokens to check

        # Factor 1: Global term presence
        evidence_text = " ".join(ev.text.lower() for ev in evidence)
        evidence_tokens = set(evidence_text.split())
        global_found = query_tokens & evidence_tokens
        global_relevance = len(global_found) / len(query_tokens)

        # Factor 2: Co-occurrence — do query terms appear together in chunks?
        max_cooccurrence = 0.0
        best_chunk_coverage = 0.0
        for ev in evidence:
            chunk_tokens = set(ev.text.lower().split())
            chunk_found = query_tokens & chunk_tokens
            cooccurrence = len(chunk_found) / len(query_tokens)
            max_cooccurrence = max(max_cooccurrence, cooccurrence)
            best_chunk_coverage = max(best_chunk_coverage, len(chunk_found))

        # Factor 3: Document-title topic alignment
        # Check whether the SOURCE DOCUMENTS are topically related to the query.
        # A document titled "Employee Wellness Benefit Policy" is NOT about
        # "company annual revenue" even though it contains those tokens.
        # Filter out generic tokens that appear in many document titles.
        _generic_tokens = {
            "company", "employee", "annual", "process", "workflow",
            "case", "task", "status", "date", "owner", "type",
            "step", "new", "old", "update", "delete", "create",
            "add", "remove", "change", "set", "get", "check",
            "configure", "setup", "run", "start", "stop",
        }
        content_query_tokens = query_tokens - _generic_tokens
        doc_titles = self._get_document_titles(evidence)
        title_text = " ".join(doc_titles).lower()
        if content_query_tokens:
            title_tokens_found = sum(1 for t in content_query_tokens if t in title_text)
            title_alignment = title_tokens_found / len(content_query_tokens)
        else:
            # All tokens are generic — fall back to full query check
            title_tokens_found = sum(1 for t in query_tokens if t in title_text)
            title_alignment = title_tokens_found / len(query_tokens) if query_tokens else 1.0

        # Factor 4: Retrieval score quality
        if evidence:
            top_score = max(ev.score for ev in evidence)
            score_quality = min(top_score / 0.3, 1.0)
        else:
            score_quality = 0.0

        # Combined base relevance
        relevance = (
            global_relevance * 0.20
            + max_cooccurrence * 0.25
            + title_alignment * 0.35
            + score_quality * 0.20
        )

        # HARD GATE: If document titles were successfully looked up AND
        # NO title contains any CONTENT query token, the evidence is from
        # unrelated documents that happen to share keywords.
        # Only apply when titles are available (not empty from failed lookup).
        if content_query_tokens and doc_titles and title_tokens_found == 0:
            relevance = min(relevance, 0.35)

        return relevance

    def _get_document_titles(self, evidence: list[EvidenceItem]) -> list[str]:
        """Look up document titles from the registry for the evidence items."""
        titles = []
        seen = set()
        try:
            from kurukshetra.registry.database import get_connection
            conn = get_connection()
            for ev in evidence:
                if ev.document_id not in seen:
                    seen.add(ev.document_id)
                    row = conn.execute(
                        "SELECT title FROM documents WHERE document_id = ?",
                        (ev.document_id,),
                    ).fetchone()
                    if row and row[0]:
                        titles.append(row[0])
            conn.close()
        except Exception:
            pass
        return titles

    def _detect_mention_vs_answer(
        self, query: str, evidence: list[EvidenceItem]
    ) -> float:
        """
        Detect if evidence mentions the topic but doesn't actually answer the question.

        Returns a penalty score (0.0 = evidence answers the question, 1.0 = evidence only mentions topic).
        """
        if not evidence:
            return 0.0

        evidence_text = " ".join(e.text for e in evidence)

        # Count questions: "How many X?" → evidence must contain a number about X
        if _MVA_COUNT_PATTERN.search(query):
            count_what = re.search(r"how many (\w+)", query.lower())
            if count_what:
                thing = count_what.group(1)
                # Check for numbers that answer the count
                count_patterns = [
                    rf"\b\d[\d,]*\b\s*{re.escape(thing)}\b",
                    rf"\b{re.escape(thing)}\b\s*\b\d[\d,]*\b",
                    rf"\b(total|approximately|about|around|roughly|nearly|over|more than)\s+\d[\d,]*\b",
                ]
                for pattern in count_patterns:
                    if re.search(pattern, evidence_text, re.IGNORECASE):
                        return 0.0  # Evidence answers the count
            # No count answer found
            return 0.8  # High penalty — mentions topic but can't answer count

        # Who questions: "Who does X?" → evidence must mention a person/team doing X
        if _MVA_WHO_PATTERN.search(query):
            who_what = re.search(r"who\s+(does|do|is|are|was|were|should|can|will)\s+(\w+)", query.lower())
            if who_what:
                verb = who_what.group(1)
                thing = who_what.group(2)
                # Check for agent/team patterns near the thing
                agent_pattern = rf"\b(team|person|owner|manager|lead|assigned|responsible)\b.*?{re.escape(thing)}\b|{re.escape(thing)}\b.*?\b(team|person|owner|manager|lead|assigned|responsible)\b"
                if re.search(agent_pattern, evidence_text, re.IGNORECASE):
                    return 0.0  # Evidence mentions who does what
            return 0.5  # Moderate penalty

        # When questions: "When did X?" → evidence must contain a date/time
        if _MVA_WHEN_PATTERN.search(query):
            date_pattern = re.compile(r"\b\d{4}[-/]\d{2}[-/]\d{2}\b|\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", re.IGNORECASE)
            if date_pattern.search(evidence_text):
                return 0.0  # Evidence contains dates
            return 0.5  # Moderate penalty

        # Salary/value questions: "What is the salary range for X?" → evidence must
        # contain actual salary data, not just pricing/range terminology
        if _MVA_SALARY_PATTERN.search(query):
            # Check if evidence contains actual salary numbers (e.g., "$50,000", "₹8,00,000")
            salary_patterns = [
                re.compile(r"\$\s*\d[\d,]*"),  # USD amounts
                re.compile(r"₹\s*\d[\d,]*"),  # INR amounts
                re.compile(r"\b(lpa|lakhs?|crores?)\b", re.IGNORECASE),  # Indian salary terms
                re.compile(r"\b(salary|compensation|pay|stipend)\s+(range|band|level|grade|slab)\s+\d", re.IGNORECASE),
            ]
            for pat in salary_patterns:
                if pat.search(evidence_text):
                    return 0.0  # Evidence contains actual salary data
            return 0.8  # High penalty — mentions salary topic but no actual salary data

        return 0.0  # No mention-vs-answer issue detected

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
        - Cross-document corroboration
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
        diversity_factor = min(unique_docs / 3, 1.0)  # 3+ docs = max diversity

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

        # Factor 6: Cross-document corroboration
        # Check if answer sentences are grounded in evidence from multiple documents
        corroborated_docs = set()
        for sent in answer_sentences:
            sent_tokens = set(sent.lower().split())
            for ev in evidence:
                ev_tokens = set(ev.text.lower().split())
                overlap = len(sent_tokens & ev_tokens)
                if overlap > len(sent_tokens) * 0.3:  # 30% token overlap
                    corroborated_docs.add(ev.document_id)
        corroboration_factor = min(len(corroborated_docs) / 2, 1.0) if corroborated_docs else 0.0

        # Weighted combination
        confidence = (
            count_factor * 0.15
            + score_factor * 0.20
            + diversity_factor * 0.20
            + coverage_factor * 0.10
            + consistency_factor * 0.15
            + corroboration_factor * 0.20
        )

        return min(max(confidence, 0.0), 1.0)

    def _detect_conflicts(self, evidence: list[EvidenceItem]) -> list[str]:
        """
        Detect conflicting information in evidence.

        Checks for:
        1. Negation patterns across documents
        2. Version/temporal conflicts (old vs new procedures)
        3. Contradictory factual claims
        """
        conflicts: list[str] = []

        # Group evidence by document
        by_doc: dict[str, list[EvidenceItem]] = {}
        for ev in evidence:
            by_doc.setdefault(ev.document_id, []).append(ev)

        if len(by_doc) < 2:
            return conflicts

        doc_texts = {
            doc_id: " ".join(ev.text.lower() for ev in evs)
            for doc_id, evs in by_doc.items()
        }

        doc_ids = list(doc_texts.keys())

        # 1. Negation patterns across documents
        negation_patterns = [
            (r'\bnot\s+\w+', r'\bis\s+\w+'),
            (r'\bshould\s+not\b', r'\bshould\b'),
            (r'\bdo\s+not\b', r'\bdo\b'),
            (r'\bdoes\s+not\b', r'\bdoes\b'),
            (r'\bnever\b', r'\balways\b'),
            (r'\bprohibited\b', r'\bpermitted\b'),
        ]

        for i in range(len(doc_ids)):
            for j in range(i + 1, len(doc_ids)):
                text_a = doc_texts[doc_ids[i]]
                text_b = doc_texts[doc_ids[j]]
                for neg_pat, pos_pat in negation_patterns:
                    neg_matches_a = len(re.findall(neg_pat, text_a))
                    pos_matches_b = len(re.findall(pos_pat, text_b))
                    if neg_matches_a > 0 and pos_matches_b > 0:
                        conflicts.append(
                            f"Potential conflict: {doc_ids[i]} vs {doc_ids[j]} "
                            f"(contradictory patterns)"
                        )

        # 2. Version/temporal conflicts
        year_pattern = re.compile(r'\b(20\d{2})\b')
        doc_years: dict[str, list[int]] = {}
        for doc_id, text in doc_texts.items():
            years = [int(y) for y in year_pattern.findall(text)]
            doc_years[doc_id] = years

        for i in range(len(doc_ids)):
            for j in range(i + 1, len(doc_ids)):
                years_a = doc_years.get(doc_ids[i], [])
                years_b = doc_years.get(doc_ids[j], [])
                if years_a and years_b:
                    max_a = max(years_a)
                    max_b = max(years_b)
                    if abs(max_a - max_b) >= 3:  # 3+ year gap
                        conflicts.append(
                            f"Version conflict: {doc_ids[i]} ({max_a}) vs "
                            f"{doc_ids[j]} ({max_b}) — may contain outdated information"
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

    def _determine_knowledge_source(
        self,
        evidence: list[EvidenceItem],
        has_entity_evidence: bool,
        llm_used: bool,
    ) -> str:
        """
        Determine the primary knowledge source for this answer.

        Returns one of:
        - 'organization' — answer comes from ingested documents
        - 'conversation' — answer comes from entity augmentation (graph lookup)
        - 'mixed' — combination of organization + entity evidence
        - 'model' — answer primarily from LLM (with evidence context)
        """
        if not evidence:
            return "unknown"

        # Check if entity-augmented evidence is present
        entity_evidence = [e for e in evidence if e.metadata.get("source") == "entity_lookup"]
        org_evidence = [e for e in evidence if e.metadata.get("source") != "entity_lookup"]

        if entity_evidence and org_evidence:
            return "mixed"  # Both graph lookup and document retrieval
        elif entity_evidence and not org_evidence:
            return "conversation"  # Graph/entity lookup only
        elif llm_used:
            return "model"  # LLM synthesized from organizational evidence
        else:
            return "organization"  # Directly from ingested documents

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
            knowledge_source="unknown",
        )
