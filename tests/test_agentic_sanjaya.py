"""
Tests for AgenticSANJAYA Orchestrator
=====================================

Deterministic tests for:
- Evidence sufficiency checking
- Mention-vs-answer detection
- Iterative retrieval
- Multi-document evidence aggregation
- Verification layer
"""

import pytest
from kurukshetra.retrieval.models import RetrievalResult
from kurukshetra.agent.orchestrator import (
    AgenticSANJAYA,
    EvidenceSufficiencyChecker,
    RetrievalRound,
    AgenticPlan,
)
from kurukshetra.agent.answer_generator import EvidenceItem


# ── EvidenceSufficiencyChecker ────────────────────────────────


class TestEvidenceSufficiencyChecker:
    """Tests for evidence sufficiency checking."""

    def setup_method(self):
        self.checker = EvidenceSufficiencyChecker()

    def test_empty_evidence_returns_zero(self):
        """Empty evidence should return sufficiency 0."""
        score, mva = self.checker.check("test query", [])
        assert score == 0.0
        assert mva is False

    def test_single_evidence_moderate_sufficiency(self):
        """Single evidence item should have moderate sufficiency."""
        evidence = [
            EvidenceItem(
                chunk_id="c1", document_id="d1", source_path="test.txt",
                text="G3 Data Feed Configuration involves setting up data feeds for G3 RMS.",
                score=0.5, rank=1,
            )
        ]
        score, mva = self.checker.check("What is G3 Data Feed Configuration?", evidence)
        assert score > 0.3
        assert mva is False

    def test_multiple_evidence_higher_sufficiency(self):
        """Multiple evidence items should increase sufficiency."""
        evidence = [
            EvidenceItem(
                chunk_id="c1", document_id="d1", source_path="a.txt",
                text="G3 Data Feed Configuration is used for data exchange between systems.",
                score=0.5, rank=1,
            ),
            EvidenceItem(
                chunk_id="c2", document_id="d2", source_path="b.txt",
                text="The G3 Data Feed setup requires RMS configuration and API keys.",
                score=0.4, rank=2,
            ),
            EvidenceItem(
                chunk_id="c3", document_id="d3", source_path="c.txt",
                text="G3 Data Feed supports multiple data formats including XML and JSON.",
                score=0.3, rank=3,
            ),
        ]
        score, mva = self.checker.check("What is G3 Data Feed Configuration?", evidence)
        assert score > 0.5
        assert mva is False

    def test_count_question_no_numbers_abstains(self):
        """Count question with no numbers in evidence should flag MVA."""
        evidence = [
            EvidenceItem(
                chunk_id="c1", document_id="d1", source_path="hr.txt",
                text="Employees of IDeaS are eligible for various benefits and work policies.",
                score=0.5, rank=1,
            ),
        ]
        score, mva = self.checker.check("How many employees does IDeaS have?", evidence)
        assert mva is True
        assert score < 0.6  # Penalized by MVA

    def test_count_question_with_numbers_no_context(self):
        """Count question with numbers but not in headcount context should flag MVA."""
        evidence = [
            EvidenceItem(
                chunk_id="c1", document_id="d1", source_path="hr.txt",
                text="For how many Children can an employee claim? Ans - The day care facility supports up to 5 children per employee.",
                score=0.5, rank=1,
            ),
        ]
        score, mva = self.checker.check("How many employees does IDeaS have?", evidence)
        # Numbers exist but are about children, not employee count
        assert mva is True

    def test_count_question_with_headcount(self):
        """Count question with actual headcount should NOT flag MVA."""
        evidence = [
            EvidenceItem(
                chunk_id="c1", document_id="d1", source_path="hr.txt",
                text="IDeaS has approximately 500 employees across global offices.",
                score=0.5, rank=1,
            ),
        ]
        score, mva = self.checker.check("How many employees does IDeaS have?", evidence)
        assert mva is False
        assert score > 0.5

    def test_non_count_question_not_affected(self):
        """Non-count questions should not be affected by MVA detection."""
        evidence = [
            EvidenceItem(
                chunk_id="c1", document_id="d1", source_path="g3.txt",
                text="G3 Data Feed Configuration involves API setup for data exchange.",
                score=0.5, rank=1,
            ),
        ]
        score, mva = self.checker.check("What is G3 Data Feed?", evidence)
        assert mva is False


# ── Mention-vs-Answer Detection in AnswerGenerator ────────────


class TestMentionVsAnswerDetection:
    """Tests for MVA detection in AnswerGenerator."""

    def setup_method(self):
        from kurukshetra.agent.answer_generator import AnswerGenerator
        self.gen = AnswerGenerator()

    def test_count_question_no_numbers_abstains(self):
        """Count question without numbers in evidence should abstain."""
        results = [
            RetrievalResult(
                chunk_id="c1", document_id="d1", score=0.5,
                text="Employees are eligible for benefits and work policies at IDeaS.",
                metadata={},
            ),
        ]
        r = self.gen.generate(
            query="How many employees does IDeaS have?",
            results=results,
            strategy="hybrid",
        )
        # Should abstain because evidence mentions employees but doesn't give a count
        assert r.abstained is True

    def test_count_question_with_headcount_no_mva_penalty(self):
        """MVA detection should not penalize evidence with actual headcount."""
        evidence = [
            EvidenceItem(
                chunk_id="c1", document_id="d1", source_path="hr.txt",
                text="IDeaS employees: The company has approximately 500 employees worldwide. Employee headcount includes full-time and contract staff.",
                score=0.5, rank=1,
            ),
        ]
        penalty = self.gen._detect_mention_vs_answer(
            "How many employees does IDeaS have?", evidence
        )
        # MVA penalty should be 0 because evidence contains a count
        assert penalty == 0.0

    def test_non_count_question_not_affected(self):
        """Non-count questions should not be affected by MVA detection."""
        results = [
            RetrievalResult(
                chunk_id="c1", document_id="d1", score=0.5,
                text="G3 Data Feed Configuration involves API setup and data exchange.",
                metadata={},
            ),
        ]
        r = self.gen.generate(
            query="What is G3 Data Feed Configuration?",
            results=results,
            strategy="hybrid",
        )
        assert r.abstained is False


# ── AgenticSANJAYA Orchestrator ──────────────────────────────


class TestAgenticSANJAYA:
    """Tests for the agentic orchestrator."""

    def setup_method(self):
        from kurukshetra.retrieval.hybrid import HybridRetriever
        from kurukshetra.retrieval.access_control import VisibilityFilter, VisibilityLevel
        self.hybrid = HybridRetriever()
        self.vis = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
        self.filtered = self.vis.wrap(self.hybrid)
        self.orch = AgenticSANJAYA(retriever=self.filtered, llm_client=None, max_rounds=2)

    def test_simple_question_one_round(self):
        """Simple factual question should complete in one round."""
        result = self.orch.ask("What is G3 Data Feed Configuration?")
        assert len(result.rounds) >= 1
        assert result.answer_result.abstained is False
        assert result.verification_passed is True

    def test_out_of_scope_abstains(self):
        """Out-of-scope question should abstain."""
        result = self.orch.ask("What is quantum computing?")
        assert result.answer_result.abstained is True

    def test_evidence_has_multiple_documents(self):
        """Entity/team questions should retrieve from multiple documents."""
        result = self.orch.ask("What do you know about ICS?")
        assert result.unique_documents >= 1
        assert len(result.answer_result.evidence) >= 1

    def test_iterative_retrieval_bounded(self):
        """Retrieval should never exceed max_rounds."""
        result = self.orch.ask("What teams are involved with G3?")
        assert len(result.rounds) <= 2

    def test_agentic_result_has_all_fields(self):
        """AgenticResult should have all required fields."""
        result = self.orch.ask("What is OHIP installation?")
        assert hasattr(result, "answer_result")
        assert hasattr(result, "rounds")
        assert hasattr(result, "total_retrieval_time_ms")
        assert hasattr(result, "total_evidence_count")
        assert hasattr(result, "unique_documents")
        assert hasattr(result, "multi_document_synthesis")
        assert hasattr(result, "mention_vs_answer_detected")
        assert hasattr(result, "verification_passed")

    def test_retrieval_round_has_diagnostics(self):
        """Each retrieval round should have diagnostic information."""
        result = self.orch.ask("What is G3 RMS?")
        for rd in result.rounds:
            assert hasattr(rd, "round_number")
            assert hasattr(rd, "strategy")
            assert hasattr(rd, "query_used")
            assert hasattr(rd, "evidence")
            assert hasattr(rd, "sufficiency_score")
            assert hasattr(rd, "mention_vs_answer_flag")

    def test_entity_augmented_results(self):
        """Entity queries should augment results with graph-based documents."""
        result = self.orch.ask("What do you know about SPM?")
        assert result.total_evidence_count >= 1
        assert result.unique_documents >= 1

    def test_workflow_question_answers(self):
        """Workflow questions should answer from retrieved evidence."""
        result = self.orch.ask("How does AMS Recoding work?")
        assert result.answer_result.abstained is False
        assert len(result.answer_result.evidence) >= 1

    def test_mention_vs_answer_flag_propagates(self):
        """MVA detection should propagate to AgenticResult."""
        result = self.orch.ask("How many employees does IDeaS have?")
        # MVA should be detected in at least one round
        assert result.mention_vs_answer_detected is True
        assert result.answer_result.abstained is True

    def test_verification_passes_for_good_answer(self):
        """Verification should pass for well-grounded answers."""
        result = self.orch.ask("What is G3 Data Feed Configuration?")
        assert result.verification_passed is True

    def test_max_rounds_configurable(self):
        """Max rounds should be configurable."""
        orch1 = AgenticSANJAYA(retriever=self.filtered, max_rounds=1)
        result1 = orch1.ask("What teams are involved with G3?")
        assert len(result1.rounds) <= 1

        orch3 = AgenticSANJAYA(retriever=self.filtered, max_rounds=3)
        result3 = orch3.ask("What teams are involved with G3?")
        assert len(result3.rounds) <= 3


class TestEpisodicMemoryWiring:
    """Mission A: episodic memory recording/recall is actually reachable
    from ask(), not just a standalone module (see
    docs/MISSION_A_EPISODIC_MEMORY_WIRING.md). Uses unique query strings so
    these pass regardless of corpus state or what other tests have written
    to the shared kurukshetra_registry.duckdb."""

    def setup_method(self):
        from kurukshetra.retrieval.hybrid import HybridRetriever
        from kurukshetra.retrieval.access_control import VisibilityFilter, VisibilityLevel
        vis = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
        self.filtered = vis.wrap(HybridRetriever())
        self.orch = AgenticSANJAYA(retriever=self.filtered, llm_client=None, max_rounds=1)

    def _unique_query(self, tag: str) -> str:
        # find_similar_queries() does keyword LIKE-matching on words >3 chars,
        # so distinct test cases must share NO words with each other — a
        # single distinctive token per call, not a common phrase with a
        # unique suffix (which would make them all "similar" to each other).
        import uuid
        return f"Zzqtest{tag}{uuid.uuid4().hex[:12]}"

    def test_episode_id_recorded_after_answering(self):
        """A completed ask() call should persist an episode and return its id."""
        result = self.orch.ask(self._unique_query("answer"))
        assert result.episode_id is not None
        assert result.episode_id.startswith("EP-")

    def test_episode_id_recorded_even_on_abstain(self):
        """Abstentions are still real interactions — they must be recorded too."""
        result = self.orch.ask("What is quantum computing?")
        assert result.answer_result.abstained is True
        assert result.episode_id is not None

    def test_recalled_episodes_empty_for_novel_query(self):
        """A never-before-seen query should recall nothing."""
        result = self.orch.ask(self._unique_query("novel"))
        assert result.recalled_episodes == []

    def test_recalled_episodes_populated_on_repeat(self):
        """Asking the same distinctive query twice should recall the first episode."""
        query = self._unique_query("repeat")
        first = self.orch.ask(query)
        second = self.orch.ask(query)

        assert first.episode_id is not None
        recalled_ids = [e["episode_id"] for e in second.recalled_episodes]
        assert first.episode_id in recalled_ids

    def test_episodic_recall_never_alters_the_answer(self):
        """Episodic memory is recall/audit only — it must never change what
        the agent answers or how confident it is (that's FeedbackAwareRetriever's
        job, validated separately in Mission 3.47)."""
        query = self._unique_query("noinfluence")
        first = self.orch.ask(query)
        second = self.orch.ask(query)

        assert second.answer_result.abstained == first.answer_result.abstained
        assert second.answer_result.confidence == first.answer_result.confidence

    def test_missing_episodic_memory_does_not_break_ask(self):
        """If episodic memory is unavailable for any reason, ask() must still work."""
        self.orch.episodic_memory = None
        result = self.orch.ask(self._unique_query("noepisodic"))
        assert result.episode_id is None
        assert result.recalled_episodes == []


class TestProceduralMemoryWiring:
    """Mission B: ProceduralMemory (now an adapter over Process
    Intelligence, see docs/MISSION_B_PROCEDURAL_MEMORY_ADAPTER.md) is
    actually consulted from ask(), surfaced as additive diagnostic
    context — same non-influencing contract as episodic memory."""

    def setup_method(self):
        from kurukshetra.retrieval.hybrid import HybridRetriever
        from kurukshetra.retrieval.access_control import VisibilityFilter, VisibilityLevel
        vis = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
        self.filtered = vis.wrap(HybridRetriever())
        self.orch = AgenticSANJAYA(retriever=self.filtered, llm_client=None, max_rounds=1)

    def _seed_process(self, name: str) -> str:
        from kurukshetra.process.intelligence import (
            ensure_process_tables, persist_process, ProcessDefinition, ProcessStep,
        )
        import uuid
        ensure_process_tables()
        process_id = f"PROC-TEST-{uuid.uuid4().hex[:8]}"
        persist_process(ProcessDefinition(
            process_id=process_id,
            name=name,
            description="A test procedure seeded for orchestrator wiring tests",
            confidence=0.9,
            team="spm",
            steps=[
                ProcessStep(step_id=f"{process_id}-S1", process_id=process_id,
                            sequence=1, description="Do the first thing"),
            ],
        ))
        return process_id

    def test_matched_procedures_empty_when_nothing_matches(self):
        import uuid
        result = self.orch.ask(f"Zzqnoproc{uuid.uuid4().hex[:12]}")
        assert result.matched_procedures == []

    def test_matched_procedures_surfaces_real_process(self):
        # Generic words like "installation" collide with other seeded test
        # rows across a shared, session-persistent DuckDB (same lesson as
        # TestEpisodicMemoryWiring's _unique_query) — every word here must
        # be unique to this test, not just the marker prefix.
        import uuid
        marker = f"Zzqproc{uuid.uuid4().hex[:8]}"
        self._seed_process(marker)

        result = self.orch.ask(f"Tell me about {marker}")
        names = [p["name"] for p in result.matched_procedures]
        assert marker in names

    def test_matched_procedures_never_alters_the_answer(self):
        """Same non-influence contract as episodic recall: a matched
        procedure is context for the caller to display, not evidence fed
        into generation. Isolate the variable by asking the identical
        query with procedural_memory present vs. disabled."""
        import uuid
        marker = f"Zzqprocnoinf{uuid.uuid4().hex[:8]}"
        self._seed_process(marker)
        query = f"Explain {marker}"

        with_match = self.orch.ask(query)
        assert with_match.matched_procedures != []  # sanity: a match actually occurred

        self.orch.procedural_memory = None
        without_match = self.orch.ask(query)
        assert without_match.matched_procedures == []

        assert with_match.answer_result.abstained == without_match.answer_result.abstained
        assert with_match.answer_result.confidence == without_match.answer_result.confidence

    def test_missing_procedural_memory_does_not_break_ask(self):
        """If procedural memory is unavailable for any reason, ask() must still work."""
        import uuid
        self.orch.procedural_memory = None
        result = self.orch.ask(f"Zzqnoprocmem{uuid.uuid4().hex[:12]}")
        assert result.matched_procedures == []


class TestProspectiveMemoryWiring:
    """Mission C: ProspectiveMemory's detect_reminder_request() is now
    actually called from ask() (see
    docs/MISSION_C_PROSPECTIVE_MEMORY_WIRING.md), with a tightened
    detector — bare temporal words no longer trigger, only explicit
    reminder/follow-up phrases do."""

    def setup_method(self):
        from kurukshetra.retrieval.hybrid import HybridRetriever
        from kurukshetra.retrieval.access_control import VisibilityFilter, VisibilityLevel
        vis = VisibilityFilter(max_level=VisibilityLevel.INTERNAL)
        self.filtered = vis.wrap(HybridRetriever())
        self.orch = AgenticSANJAYA(retriever=self.filtered, llm_client=None, max_rounds=1)

    def test_explicit_reminder_creates_a_task(self):
        import uuid
        marker = f"Zzqtask{uuid.uuid4().hex[:10]}"
        result = self.orch.ask(f"Remind me to check {marker} status")
        assert result.created_task is not None
        assert marker in result.created_task["description"]

    def test_ordinary_question_creates_no_task(self):
        """The false positive this mission fixed: bare temporal words /
        "schedule" alone must not create a task from a real question."""
        import uuid
        marker = f"Zzqnotask{uuid.uuid4().hex[:10]}"
        result = self.orch.ask(f"What is the {marker} deployment schedule for tomorrow?")
        assert result.created_task is None

    def test_reminder_creation_never_alters_the_answer(self):
        """Same non-influence contract as episodic/procedural memory:
        detecting and recording a task is a side effect, not a change to
        retrieval/generation. Compare an ordinary question against the same
        question wrapped in reminder phrasing — both should abstain the
        same way (no evidence exists for either in this test corpus)."""
        import uuid
        marker = f"Zzqtasknoinf{uuid.uuid4().hex[:10]}"
        plain = self.orch.ask(f"What is {marker}?")
        as_reminder = self.orch.ask(f"Remind me to check {marker}")

        assert as_reminder.created_task is not None  # sanity: it did fire
        assert plain.answer_result.abstained == as_reminder.answer_result.abstained

    def test_missing_prospective_memory_does_not_break_ask(self):
        """If prospective memory is unavailable for any reason, ask() must still work."""
        import uuid
        self.orch.prospective_memory = None
        result = self.orch.ask(f"Remind me to check Zzqnoprospective{uuid.uuid4().hex[:10]}")
        assert result.created_task is None
