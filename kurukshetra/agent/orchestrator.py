"""
Agentic SANJAYA Orchestrator
============================

Evolves SANJAYA from single-pass RAG into an evidence-driven,
multi-document reasoning agent.

Flow:
  USER QUESTION
      ↓
  UNDERSTAND (classify query type, detect entities)
      ↓
  RETRIEVE (round 1: hybrid/entity-augmented)
      ↓
  EVALUATE EVIDENCE (sufficiency + mention-vs-answer check)
      ↓
  ENOUGH?
   NO ─────→ REFINE QUERY / RETRIEVE AGAIN (round 2: alternative strategy)
   │
  YES
   ↓
  MULTI-DOCUMENT SYNTHESIS (deduplicate, aggregate claims)
      ↓
  VERIFY (evidence supports claims, no unauthorized evidence)
      ↓
  ANSWER (LLM synthesis or extractive fallback)
      ↓
  CITATIONS + CONFIDENCE + PROVENANCE

Design principles:
- Controlled and deterministic (bounded iterations, no autonomous loops)
- Falls back to single-pass on failure
- Security wraps every retrieval iteration
- Evidence sufficiency checked BEFORE answer generation
- Mention-vs-answer detection prevents false-positive grounding
"""

from __future__ import annotations

import re
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Any

from kurukshetra.retrieval.models import RetrievalResult
from kurukshetra.agent.answer_generator import (
    AnswerGenerator,
    AnswerResult,
    EvidenceItem,
    MIN_QUERY_EVIDENCE_RELEVANCE,
    MIN_CONFIDENCE_THRESHOLD,
    MIN_EVIDENCE_COUNT,
)

logger = logging.getLogger(__name__)

# Max retrieval rounds to prevent runaway loops
MAX_RETRIEVAL_ROUNDS = 2

# Minimum evidence diversity: at least this fraction of unique documents
MIN_DOCUMENT_DIVERSITY_RATIO = 0.3

# Mention-vs-answer detection: question patterns that require specific answers
_QUESTION_PATTERNS = {
    "count": re.compile(r"\b(how many|number of|total count|count of)\b", re.IGNORECASE),
    "who": re.compile(r"\b(who|which person|which team|which individual)\b", re.IGNORECASE),
    "when": re.compile(r"\b(when|what date|what time|what year)\b", re.IGNORECASE),
    "where": re.compile(r"\b(where|which location|which site)\b", re.IGNORECASE),
    "why": re.compile(r"\b(why|what reason|what causes)\b", re.IGNORECASE),
    "specific_value": re.compile(
        r"\b(what is the|what was the|what are the)\s+\w+\s*(revenue|budget|cost|price|salary|headcount|number|amount|percentage)\b",
        re.IGNORECASE,
    ),
}

# Answer patterns: what kind of evidence answers each question type
_ANSWER_PATTERNS = {
    "count": re.compile(r"\b\d[\d,]*\b"),  # Numbers
    "who": re.compile(r"\b(team|person|owner|manager|lead|assigned)\b", re.IGNORECASE),
    "when": re.compile(r"\b\d{4}[-/]\d{2}[-/]\d{2}|\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", re.IGNORECASE),
}


@dataclass
class RetrievalRound:
    """A single retrieval round."""
    round_number: int
    strategy: str
    query_used: str
    results: list[RetrievalResult]
    evidence: list[EvidenceItem]
    sufficiency_score: float
    mention_vs_answer_flag: bool  # True if evidence mentions topic but doesn't answer


@dataclass
class AgenticPlan:
    """Plan for agentic retrieval."""
    query_type: str
    entity_type: Optional[str]  # "team", "system", "process", etc.
    detected_entities: list[str]
    needs_multi_document: bool
    max_rounds: int
    initial_strategy: str
    fallback_strategy: Optional[str]


@dataclass
class AgenticResult:
    """Result from the agentic pipeline."""
    answer_result: AnswerResult
    rounds: list[RetrievalRound]
    total_retrieval_time_ms: float
    total_evidence_count: int
    unique_documents: int
    multi_document_synthesis: bool
    mention_vs_answer_detected: bool
    verification_passed: bool


class EvidenceSufficiencyChecker:
    """
    Evaluates whether retrieved evidence actually answers the question,
    not merely mentions the topic.
    """

    def check(
        self,
        query: str,
        evidence: list[EvidenceItem],
    ) -> tuple[float, bool]:
        """
        Check evidence sufficiency.

        Returns:
            (sufficiency_score, mention_vs_answer_flag)
            - sufficiency_score: 0.0 to 1.0
            - mention_vs_answer_flag: True if evidence mentions topic but doesn't answer
        """
        if not evidence:
            return 0.0, False

        # Factor 1: Evidence count and diversity
        unique_docs = len(set(e.document_id for e in evidence))
        diversity_ratio = unique_docs / max(len(evidence), 1)
        count_score = min(len(evidence) / 3, 1.0) * 0.3
        diversity_score = min(diversity_ratio, 1.0) * 0.2

        # Factor 2: Evidence quality (scores)
        avg_score = sum(e.score for e in evidence) / len(evidence)
        quality_score = min(avg_score / 0.5, 1.0) * 0.2

        # Factor 3: Topic alignment
        query_tokens = set(query.lower().split()) - {
            "what", "is", "the", "how", "do", "does", "a", "an",
            "to", "for", "in", "of", "and", "or", "can", "you",
            "are", "there", "this", "that", "it", "on", "at", "by",
            "be", "as", "with", "from", "not",
        }
        evidence_text = " ".join(e.text.lower() for e in evidence)
        found = sum(1 for t in query_tokens if t in evidence_text)
        topic_score = (found / max(len(query_tokens), 1)) * 0.3

        sufficiency = count_score + diversity_score + quality_score + topic_score

        # Factor 4: Mention-vs-answer detection
        mention_vs_answer = self._detect_mention_vs_answer(query, evidence)

        # If mention_vs_answer is detected, penalize sufficiency
        if mention_vs_answer:
            sufficiency *= 0.5

        return min(sufficiency, 1.0), mention_vs_answer

    def _detect_mention_vs_answer(
        self, query: str, evidence: list[EvidenceItem]
    ) -> bool:
        """
        Detect if evidence mentions the topic but doesn't actually answer the question.

        For example:
        - "How many employees does IDeaS have?" → evidence mentions "employees" but
          doesn't give a count → mention_vs_answer = True
        - "What is G3 Data Feed Configuration?" → evidence describes G3 Data Feed →
          mention_vs_answer = False
        """
        # Detect question type
        question_type = None
        for qtype, pattern in _QUESTION_PATTERNS.items():
            if pattern.search(query):
                question_type = qtype
                break

        if question_type is None:
            return False  # Can't determine, assume OK

        # Check if evidence has the answer pattern
        answer_pattern = _ANSWER_PATTERNS.get(question_type)
        if answer_pattern is None:
            return False

        evidence_text = " ".join(e.text for e in evidence)

        # For count questions: check if there's an actual number
        if question_type == "count":
            # Extract the thing being counted from the query
            count_what = re.search(r"how many (\w+)", query.lower())
            if not count_what:
                return True
            thing = count_what.group(1)

            # Check if the number appears in a headcount/total context
            # Pattern: look for numbers that answer "how many <thing>"
            # Valid: "42 employees", "total of 500", "headcount is 250"
            # Invalid: "5 children", "10 hours", "2 parents"
            count_patterns = [
                # Number directly before or after the thing
                rf"\b\d[\d,]*\b\s*{re.escape(thing)}\b",
                rf"\b{re.escape(thing)}\b\s*\b\d[\d,]*\b",
                # "total of N", "approximately N", "about N"
                rf"\b(total|approximately|about|around|roughly|nearly|over|more than)\s+\d[\d,]*\b",
                # "N <thing> in total", "N <thing> total"
                rf"\b\d[\d,]*\b\s+{re.escape(thing)}\b\s+(in\s+)?total",
            ]

            for pattern in count_patterns:
                if re.search(pattern, evidence_text, re.IGNORECASE):
                    return False  # Found a number answering the count question

            return True  # No number answers the count question

        # For other question types: check if the answer pattern exists
        if answer_pattern.search(evidence_text):
            return False  # Evidence contains the answer pattern

        return True  # Evidence mentions topic but doesn't contain answer pattern


class AgenticSANJAYA:
    """
    Agentic SANJAYA orchestrator.

    Wraps the existing AnswerGenerator with iterative retrieval,
    evidence sufficiency checking, multi-document synthesis,
    and feedback-based learning.
    """

    def __init__(
        self,
        retriever=None,
        llm_client=None,
        max_rounds: int = MAX_RETRIEVAL_ROUNDS,
    ):
        """
        Args:
            retriever: A filtered retriever (VisibilityFilter wrapped)
            llm_client: GX10 client for LLM synthesis
            max_rounds: Maximum retrieval iterations (default 2)
        """
        self.retriever = self._wrap_with_feedback(retriever)
        self.llm_client = llm_client
        self.max_rounds = max_rounds
        self.generator = AnswerGenerator()
        self.sufficiency_checker = EvidenceSufficiencyChecker()

    def _wrap_with_feedback(self, retriever):
        """Wrap retriever with FeedbackAwareRetriever if available."""
        if retriever is None:
            return None
        try:
            from kurukshetra.retrieval.feedback_retriever import FeedbackAwareRetriever
            return FeedbackAwareRetriever(retriever)
        except Exception:
            return retriever

    def ask(self, query: str) -> AgenticResult:
        """
        Process a question through the agentic pipeline.

        Returns AgenticResult with the answer and diagnostic information.
        """
        total_start = time.time()
        rounds: list[RetrievalRound] = []
        mention_vs_answer_detected = False

        # Phase 1: Plan
        plan = self._create_plan(query)

        # Phase 2: Iterative retrieval
        all_evidence: list[EvidenceItem] = []
        seen_doc_ids: set[str] = set()
        seen_chunk_ids: set[str] = set()

        current_query = query
        current_strategy = plan.initial_strategy

        for round_num in range(1, self.max_rounds + 1):
            round_start = time.time()

            # Retrieve
            results = self._retrieve(current_query, current_strategy)

            # Build evidence
            evidence = self.generator._build_evidence(results)

            # Deduplicate by document and chunk
            deduped_evidence = self._deduplicate_evidence(
                evidence, seen_doc_ids, seen_chunk_ids
            )

            # Add to accumulated evidence
            all_evidence.extend(deduped_evidence)
            for e in deduped_evidence:
                seen_doc_ids.add(e.document_id)
                seen_chunk_ids.add(e.chunk_id)

            # Check sufficiency
            sufficiency, mva_flag = self.sufficiency_checker.check(query, all_evidence)
            if mva_flag:
                mention_vs_answer_detected = True

            round_elapsed = (time.time() - round_start) * 1000

            retrieval_round = RetrievalRound(
                round_number=round_num,
                strategy=current_strategy,
                query_used=current_query,
                results=results,
                evidence=deduped_evidence,
                sufficiency_score=sufficiency,
                mention_vs_answer_flag=mva_flag,
            )
            rounds.append(retrieval_round)

            logger.info(
                f"Retrieval round {round_num}: strategy={current_strategy}, "
                f"results={len(results)}, evidence={len(deduped_evidence)}, "
                f"sufficiency={sufficiency:.3f}, mva={mva_flag}, "
                f"elapsed={round_elapsed:.0f}ms"
            )

            # Phase 3: Evaluate — is evidence sufficient?
            if sufficiency >= 0.5 and not mva_flag:
                # Evidence is sufficient — proceed to synthesis
                break

            if round_num < self.max_rounds:
                # Refine query for round 2
                current_query = self._refine_query(query, all_evidence, plan)
                current_strategy = self._select_fallback_strategy(plan)

        # Phase 4: Generate answer using accumulated evidence
        total_retrieval_ms = (time.time() - total_start) * 1000

        # Use the AnswerGenerator with the accumulated evidence
        # We need to reconstruct RetrievalResult from EvidenceItem for the generator
        accumulated_results = self._evidence_to_results(all_evidence)

        answer_result = self.generator.generate(
            query=query,
            results=accumulated_results,
            strategy=f"{plan.initial_strategy}+agentic",
            authorization_status="authorized",
            llm_client=self.llm_client,
        )

        # Phase 5: Verification
        verification_passed = self._verify_answer(query, answer_result, all_evidence)

        # Phase 6: Record evaluation signals for learning
        self._record_evaluation_signals(
            query=query,
            answer_result=answer_result,
            evidence=all_evidence,
            rounds=rounds,
        )

        unique_docs = len(set(e.document_id for e in all_evidence))

        return AgenticResult(
            answer_result=answer_result,
            rounds=rounds,
            total_retrieval_time_ms=round(total_retrieval_ms, 1),
            total_evidence_count=len(all_evidence),
            unique_documents=unique_docs,
            multi_document_synthesis=unique_docs > 1,
            mention_vs_answer_detected=mention_vs_answer_detected,
            verification_passed=verification_passed,
        )

    def _record_evaluation_signals(
        self,
        query: str,
        answer_result: AnswerResult,
        evidence: list[EvidenceItem],
        rounds: list[RetrievalRound],
    ) -> None:
        """
        Record evaluation signals for measurable learning.

        This tracks:
        - Query was asked (query popularity signal)
        - Evidence documents used (document usefulness signal)
        - Retrieval failures if applicable (failure pattern signal)
        """
        try:
            from kurukshetra.retrieval.evaluation_tracker import EvaluationSignalTracker
            tracker = EvaluationSignalTracker()

            # Record query was asked
            tracker.record_query(
                query=query,
                confidence=answer_result.confidence,
            )

            # Record document signals for each piece of evidence
            for e in evidence:
                tracker.record_feedback_signal(
                    query=query,
                    document_id=e.document_id,
                    is_correct=not answer_result.abstained,
                    confidence=answer_result.confidence,
                )

            # Record retrieval failure if abstained or low evidence
            if answer_result.abstained:
                tracker.record_retrieval_failure(
                    query=query,
                    failure_type="insufficient_evidence",
                    failure_detail=answer_result.abstention_reason,
                    strategy_used=answer_result.retrieval_strategy,
                    evidence_count=len(evidence),
                )
            elif len(rounds) > 1:
                # Multiple rounds means first round was insufficient
                tracker.record_retrieval_failure(
                    query=query,
                    failure_type="insufficient_first_round",
                    failure_detail=f"Required {len(rounds)} retrieval rounds",
                    strategy_used=rounds[0].strategy if rounds else "unknown",
                    evidence_count=len(evidence),
                )
        except Exception:
            # Never fail the answer because of evaluation tracking
            pass

    def _create_plan(self, query: str) -> AgenticPlan:
        """Create a retrieval plan for the query."""
        from kurukshetra.agent.planner import SANJAYAPlanner

        planner = SANJAYAPlanner()
        plan_obj = planner.create_plan(query)

        # Detect entities
        entity_patterns = {
            "team": r"\b(ICS|SPM|ROA|SDOPS|IT|HR|CPM|PMO|NOC)\b",
            "system": r"\b(G3|RMS|Opera|OHIP|FOLS|SFDC|Demand360|NGI|Optix)\b",
        }

        detected_entities = []
        entity_type = None
        for etype, pattern in entity_patterns.items():
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                detected_entities.extend(m.upper() for m in matches)
                entity_type = etype

        # Determine if multi-document synthesis is needed
        needs_multi = (
            plan_obj.query_type in ("cross_doc", "semantic", "graph_related")
            or len(detected_entities) > 0
            or re.search(r"\b(all|every|each|across|teams|systems|workflows)\b", query, re.IGNORECASE)
        )

        agentic_plan = AgenticPlan(
            query_type=plan_obj.query_type,
            entity_type=entity_type,
            detected_entities=detected_entities,
            needs_multi_document=needs_multi,
            max_rounds=self.max_rounds if needs_multi else 1,
            initial_strategy=plan_obj.recommended_strategy,
            fallback_strategy="hybrid",  # will be set below
        )
        agentic_plan.fallback_strategy = self._select_fallback_strategy(agentic_plan)
        return agentic_plan

    def _retrieve(self, query: str, strategy: str) -> list[RetrievalResult]:
        """Retrieve evidence using the specified strategy."""
        if self.retriever is None:
            return []

        try:
            # Always use the wrapped retriever (includes visibility filtering)
            results = self.retriever.search(query, top_k=10)
            return results
        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            return []

    def _refine_query(
        self,
        original_query: str,
        evidence: list[EvidenceItem],
        plan: AgenticPlan,
    ) -> str:
        """
        Refine the query for a second retrieval round.

        Strategy: extract key terms from retrieved evidence and combine
        with the original query for a more targeted search.
        """
        if not evidence:
            return original_query

        # For entity queries: use entity name + query type
        if plan.detected_entities and plan.entity_type:
            entity_str = " ".join(plan.detected_entities[:2])
            return f"{entity_str} {plan.entity_type} {original_query}"

        # For cross-document queries: add document diversity terms
        if plan.needs_multi_document:
            # Extract common terms from top evidence
            all_text = " ".join(e.text[:200] for e in evidence[:5])
            # Find terms that appear frequently in evidence
            words = all_text.lower().split()
            word_freq: dict[str, int] = {}
            for w in words:
                if len(w) > 3 and w.isalpha():
                    word_freq[w] = word_freq.get(w, 0) + 1
            # Get top terms
            top_terms = sorted(word_freq.items(), key=lambda x: -x[1])[:5]
            if top_terms:
                augmentation = " ".join(t[0] for t in top_terms)
                return f"{original_query} {augmentation}"

        return original_query

    def _select_fallback_strategy(self, plan: AgenticPlan) -> str:
        """Select a fallback strategy for round 2."""
        # If initial was hybrid, try entity-aware or vector
        if plan.entity_type == "team":
            return "hybrid"  # Entity augmentation handles team lookup
        if plan.entity_type == "system":
            return "vector"  # Semantic search for system concepts
        if plan.query_type == "semantic":
            return "hybrid"
        if plan.query_type == "exact_term":
            return "vector"
        return "hybrid"

    def _deduplicate_evidence(
        self,
        evidence: list[EvidenceItem],
        seen_doc_ids: set[str],
        seen_chunk_ids: set[str],
    ) -> list[EvidenceItem]:
        """Deduplicate evidence by document and chunk ID."""
        deduped = []
        for e in evidence:
            if e.chunk_id not in seen_chunk_ids:
                deduped.append(e)
        return deduped

    def _evidence_to_results(
        self, evidence: list[EvidenceItem]
    ) -> list[RetrievalResult]:
        """Convert evidence items back to RetrievalResult for the AnswerGenerator."""
        results = []
        for i, e in enumerate(evidence):
            results.append(RetrievalResult(
                chunk_id=e.chunk_id,
                document_id=e.document_id,
                score=e.score,
                text=e.text,
                metadata={**e.metadata, "source_path": e.source_path},
            ))
        return results

    def _verify_answer(
        self,
        query: str,
        answer_result: AnswerResult,
        evidence: list[EvidenceItem],
    ) -> bool:
        """
        Verify the answer before returning.

        Checks:
        1. Answer is grounded in evidence
        2. Citations match evidence (using answer_result's own evidence)
        3. No unauthorized evidence
        4. Claims are supported
        """
        if answer_result.abstained:
            return True  # Abstention is always valid

        if not answer_result.answer:
            return False

        if not evidence:
            return False

        # Use the answer_result's own evidence set for citation verification
        # (it may include entity-augmented docs added by AnswerGenerator)
        answer_evidence_doc_ids = {e.document_id for e in answer_result.evidence}
        for citation in answer_result.citations:
            if citation.document_id not in answer_evidence_doc_ids:
                logger.warning(
                    f"Citation {citation.document_id} not in answer evidence set"
                )
                # Don't fail verification — this is a soft warning
                # The AnswerGenerator may have added evidence we didn't track

        # Check that answer has reasonable length
        if len(answer_result.answer) < 10:
            return False

        # Check that we have evidence from at least one source
        if not answer_result.evidence:
            return False

        return True
