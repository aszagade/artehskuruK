"""
Tests for SANJAYA Memory Foundation
=====================================

Tests prove that SANJAYA can distinguish:
- "I know this from the organization" (semantic/external memory)
- "I remember this from our conversation" (working/episodic memory)
- "This is a procedure" (procedural memory)
- "This is a future task" (prospective memory)
- "This is general model knowledge" (parametric — NOT used for org answers)
- "I do not have evidence" (abstention)
"""
import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestWorkingMemory(unittest.TestCase):
    """Test working memory (current conversation state)."""

    def test_working_memory_tracks_query(self):
        from kurukshetra.agent.memory_store import WorkingMemoryState
        wm = WorkingMemoryState()
        wm.current_query = "What is G3?"
        self.assertEqual(wm.current_query, "What is G3?")

    def test_working_memory_tracks_evidence(self):
        from kurukshetra.agent.memory_store import WorkingMemoryState
        wm = WorkingMemoryState()
        evidence = [{"document_id": "D1", "text": "G3 is a system"}]
        wm.set_evidence(evidence)
        self.assertEqual(len(wm.retrieved_evidence), 1)
        self.assertEqual(wm.retrieved_evidence[0]["document_id"], "D1")

    def test_working_memory_tracks_reasoning(self):
        from kurukshetra.agent.memory_store import WorkingMemoryState
        wm = WorkingMemoryState()
        wm.add_reasoning_step("Retrieved 5 documents")
        wm.add_reasoning_step("Found entity G3 in graph")
        self.assertEqual(len(wm.reasoning_trace), 2)
        self.assertIn("Retrieved 5", wm.reasoning_trace[0])

    def test_working_memory_reset(self):
        from kurukshetra.agent.memory_store import WorkingMemoryState
        wm = WorkingMemoryState()
        wm.current_query = "test"
        wm.set_evidence([{"doc": "1"}])
        wm.reset()
        self.assertEqual(wm.current_query, "")
        self.assertEqual(len(wm.retrieved_evidence), 0)

    def test_working_memory_claims(self):
        from kurukshetra.agent.memory_store import WorkingMemoryState, AttributedClaim, KnowledgeSource
        wm = WorkingMemoryState()
        claim = AttributedClaim(
            claim="G3 is used by SPM team",
            source=KnowledgeSource.ORGANIZATION,
            confidence=0.85,
            evidence_ids=["D1", "D2"],
        )
        wm.add_claim(claim)
        self.assertEqual(len(wm.active_claims), 1)
        self.assertEqual(wm.active_claims[0].source, KnowledgeSource.ORGANIZATION)


class TestEpisodicMemory(unittest.TestCase):
    """Test episodic memory (persistent interaction history)."""

    def test_record_episode(self):
        from kurukshetra.agent.memory_store import EpisodicMemory, KnowledgeSource
        em = EpisodicMemory()
        episode = em.record_episode(
            query="What is G3?",
            answer="G3 is a revenue management system.",
            confidence=0.85,
            abstained=False,
            evidence_doc_ids=["D1"],
            knowledge_sources=[KnowledgeSource.ORGANIZATION],
            user_id="test_user",
        )
        self.assertIsNotNone(episode.episode_id)
        self.assertEqual(episode.query, "What is G3?")

    def test_find_similar_queries(self):
        from kurukshetra.agent.memory_store import EpisodicMemory, KnowledgeSource
        em = EpisodicMemory()
        em.record_episode(
            query="What is G3 RMS configuration?",
            answer="G3 RMS configuration involves...",
            confidence=0.8,
            abstained=False,
            evidence_doc_ids=["D1"],
            knowledge_sources=[KnowledgeSource.ORGANIZATION],
        )
        similar = em.find_similar_queries("What is G3 RMS?")
        self.assertGreater(len(similar), 0)

    def test_record_feedback(self):
        from kurukshetra.agent.memory_store import EpisodicMemory, KnowledgeSource
        em = EpisodicMemory()
        episode = em.record_episode(
            query="test", answer="test", confidence=0.5,
            abstained=False, evidence_doc_ids=[],
            knowledge_sources=[KnowledgeSource.ORGANIZATION],
        )
        em.record_feedback(episode.episode_id, is_correct=True)
        stats = em.get_feedback_stats()
        self.assertGreaterEqual(stats["correct"], 1)

    def test_get_recent_episodes(self):
        from kurukshetra.agent.memory_store import EpisodicMemory, KnowledgeSource
        em = EpisodicMemory()
        for i in range(3):
            em.record_episode(
                query=f"query {i}", answer=f"answer {i}", confidence=0.5,
                abstained=False, evidence_doc_ids=[],
                knowledge_sources=[KnowledgeSource.ORGANIZATION],
            )
        recent = em.get_recent_episodes(limit=2)
        self.assertEqual(len(recent), 2)


class TestSemanticMemory(unittest.TestCase):
    """Test semantic memory (organizational knowledge wrapper)."""

    def test_get_teams(self):
        from kurukshetra.agent.memory_store import SemanticMemory
        sm = SemanticMemory()
        teams = sm.get_teams()
        self.assertIsInstance(teams, list)
        # Should have at least some teams from the corpus
        if teams:
            self.assertIn("team", teams[0])
            self.assertIn("document_count", teams[0])

    def test_get_known_concepts(self):
        from kurukshetra.agent.memory_store import SemanticMemory
        sm = SemanticMemory()
        concepts = sm.get_known_concepts(concept_type="system")
        self.assertIsInstance(concepts, list)

    def test_knows_concept(self):
        from kurukshetra.agent.memory_store import SemanticMemory
        sm = SemanticMemory()
        # G3 should be known from the corpus
        result = sm.knows("G3 RMS")
        self.assertIsInstance(result, bool)

    def test_get_glossary(self):
        from kurukshetra.agent.memory_store import SemanticMemory
        sm = SemanticMemory()
        glossary = sm.get_glossary()
        self.assertIsInstance(glossary, list)


class TestProceduralMemory(unittest.TestCase):
    """Test procedural memory — an adapter over Process Intelligence
    (kurukshetra.process.intelligence), not its own store (Mission B).
    Fixtures use the same ensure_process_tables()/persist_process() setup
    as tests/test_process_intelligence.py, for a real, evidence-shaped
    process rather than a synthetic procedural_memory row."""

    def _make_process(self, name=None, description="Steps to install a new property in G3 RMS"):
        from kurukshetra.process.intelligence import (
            ensure_process_tables, persist_process, ProcessDefinition, ProcessStep,
        )
        import uuid
        ensure_process_tables()
        process_id = f"PROC-TEST-{uuid.uuid4().hex[:8]}"
        # Default name must be unique per call — the shared, session-persistent
        # DuckDB accumulates rows across every test method that calls this
        # fixture, and keyword-LIKE matching on generic words ("property",
        # "installation") means a fixed default name collides across tests
        # (found this the hard way: a tie on confidence between two
        # identically-named rows made assertions on found[0] flaky).
        if name is None:
            name = f"Zzqproc{uuid.uuid4().hex[:10]} Property Installation"
        proc = ProcessDefinition(
            process_id=process_id,
            name=name,
            description=description,
            source_documents=["DOC-000160"],
            confidence=0.9,
            team="spm",
            steps=[
                ProcessStep(
                    step_id=f"{process_id}-S1", process_id=process_id, sequence=1,
                    description="Submit request", actor_team="spm",
                ),
                ProcessStep(
                    step_id=f"{process_id}-S2", process_id=process_id, sequence=2,
                    description="Configure system", actor_team="spm",
                ),
            ],
        )
        persist_process(proc)
        return process_id, name

    def test_find_procedure_matches_real_process_intelligence_data(self):
        from kurukshetra.agent.memory_store import ProceduralMemory
        _, name = self._make_process()
        pm = ProceduralMemory()
        # Keyword matching is OR-across-words (see search_processes), so a
        # query mixing one unique word with generic ones ("property",
        # "installation") can also match unrelated rows sharing only the
        # generic words — including stale rows from earlier local test
        # runs in this shared DuckDB. Assert membership, not strict top-of-
        # list position: confidence ties have no guaranteed secondary sort.
        found = pm.find_procedure(name, limit=20)
        self.assertIn(name, [p["name"] for p in found])

    def test_get_procedure_returns_steps_and_gaps(self):
        from kurukshetra.agent.memory_store import ProceduralMemory
        process_id, _ = self._make_process()
        pm = ProceduralMemory()
        detail = pm.get_procedure(process_id)
        self.assertIsNotNone(detail)
        self.assertIn("steps", detail)
        self.assertIn("gaps", detail)
        self.assertEqual(len(detail["steps"]), 2)

    def test_get_all_procedures_filters_by_team(self):
        from kurukshetra.agent.memory_store import ProceduralMemory
        import uuid
        _, name = self._make_process(name=f"Zzqproc{uuid.uuid4().hex[:10]} Team Filter Test")
        pm = ProceduralMemory()
        results = pm.get_all_procedures(team="spm")
        self.assertTrue(any(p["name"] == name for p in results))

    def test_no_longer_owns_a_standalone_table(self):
        """Guard against regressing back to a parallel, unpopulated store."""
        from kurukshetra.agent.memory_store import ProceduralMemory
        self.assertFalse(hasattr(ProceduralMemory, "store_procedure"))


class TestProspectiveMemory(unittest.TestCase):
    """Test prospective memory (future tasks/reminders)."""

    def test_add_task(self):
        from kurukshetra.agent.memory_store import ProspectiveMemory
        pm = ProspectiveMemory()
        task = pm.add_task(
            description="Follow up on G3 installation",
            requested_by="user",
            source_query="Remind me to follow up on G3 installation",
        )
        self.assertIsNotNone(task.task_id)
        self.assertFalse(task.completed)

    def test_get_pending_tasks(self):
        from kurukshetra.agent.memory_store import ProspectiveMemory
        pm = ProspectiveMemory()
        pm.add_task(description="Task 1", source_query="test")
        pm.add_task(description="Task 2", source_query="test")
        pending = pm.get_pending_tasks()
        self.assertGreaterEqual(len(pending), 2)

    def test_complete_task(self):
        from kurukshetra.agent.memory_store import ProspectiveMemory
        pm = ProspectiveMemory()
        task = pm.add_task(description="Test task", source_query="test")
        pm.complete_task(task.task_id)
        pending = pm.get_pending_tasks()
        # The completed task should not appear in pending
        pending_ids = [t.task_id for t in pending]
        self.assertNotIn(task.task_id, pending_ids)

    def test_detect_reminder_request(self):
        from kurukshetra.agent.memory_store import ProspectiveMemory
        pm = ProspectiveMemory()
        result = pm.detect_reminder_request("Remind me to check G3 status tomorrow")
        self.assertIsNotNone(result)
        self.assertIn("G3", result)

    def test_no_false_positive_reminder(self):
        from kurukshetra.agent.memory_store import ProspectiveMemory
        pm = ProspectiveMemory()
        result = pm.detect_reminder_request("What is G3 RMS?")
        self.assertIsNone(result)

    def test_no_false_positive_on_bare_temporal_words(self):
        """Regression guard (Mission C): bare temporal words ("tomorrow",
        "next week", "later") and the bare word "schedule" used to trigger
        detection on their own — real false positives on ordinary factual
        questions, confirmed live before this fix. A temporal word alone is
        not an explicit reminder request."""
        from kurukshetra.agent.memory_store import ProspectiveMemory
        pm = ProspectiveMemory()
        should_not_trigger = [
            "What is the deployment schedule for G3?",
            "What is the maintenance window tomorrow?",
            "What happened later in the incident timeline?",
            "What is the release schedule for next month?",
            "What documents describe the follow up process for ICS?",
        ]
        for query in should_not_trigger:
            self.assertIsNone(
                pm.detect_reminder_request(query),
                f"False positive on: {query!r}",
            )

    def test_explicit_reminder_phrases_still_detected(self):
        """The tightened patterns must still catch genuine requests."""
        from kurukshetra.agent.memory_store import ProspectiveMemory
        pm = ProspectiveMemory()
        should_trigger = [
            "Remind me to check G3 status tomorrow",
            "Please remember to escalate this ticket",
            "Don't forget to update the glossary",
            "Set a reminder for the G3 rollout",
            "Follow up on the SFDC ticket next week",
        ]
        for query in should_trigger:
            self.assertIsNotNone(
                pm.detect_reminder_request(query),
                f"Missed a genuine reminder request: {query!r}",
            )


class TestKnowledgeSourceAttribution(unittest.TestCase):
    """Test that SANJAYA correctly attributes knowledge sources."""

    def test_answer_has_knowledge_source(self):
        """Every answer must have a knowledge_source field."""
        from kurukshetra.agent.answer_generator import AnswerGenerator
        from kurukshetra.retrieval.models import RetrievalResult

        gen = AnswerGenerator()
        results = [
            RetrievalResult(
                chunk_id="C1", document_id="D1", score=0.5,
                text="G3 RMS is a revenue management system used by the SPM team.",
                metadata={},
            ),
        ]
        r = gen.generate(query="What is G3 RMS?", results=results, strategy="hybrid")
        self.assertIn(r.knowledge_source, ("organization", "conversation", "mixed", "model", "unknown"))

    def test_abstention_has_unknown_source(self):
        """Abstained answers should have 'unknown' knowledge source."""
        from kurukshetra.agent.answer_generator import AnswerGenerator
        gen = AnswerGenerator()
        r = gen.generate(query="test", results=[], strategy="hybrid")
        self.assertTrue(r.abstained)
        self.assertEqual(r.knowledge_source, "unknown")

    def test_entity_augmented_answer_source(self):
        """Entity-augmented answers should have 'conversation' or 'mixed' source."""
        from kurukshetra.agent.answer_generator import AnswerGenerator
        from kurukshetra.retrieval.models import RetrievalResult

        gen = AnswerGenerator()
        results = [
            RetrievalResult(
                chunk_id="C1", document_id="D1", score=0.5,
                text="G3 RMS is used by the SPM team for revenue management.",
                metadata={"source": "entity_lookup"},
            ),
        ]
        r = gen.generate(query="What do you know about SPM?", results=results, strategy="hybrid")
        if not r.abstained:
            self.assertIn(r.knowledge_source, ("conversation", "mixed"))

    def test_knowledge_source_distinction(self):
        """Verify SANJAYA distinguishes organization vs conversation vs model knowledge."""
        from kurukshetra.agent.memory_store import KnowledgeSource

        # Organization knowledge
        org = KnowledgeSource.ORGANIZATION
        self.assertEqual(org.value, "organization")

        # Conversation knowledge
        conv = KnowledgeSource.CONVERSATION
        self.assertEqual(conv.value, "conversation")

        # Procedure knowledge
        proc = KnowledgeSource.PROCEDURE
        self.assertEqual(proc.value, "procedure")

        # Model knowledge (parametric)
        model = KnowledgeSource.MODEL
        self.assertEqual(model.value, "model")

        # All sources are distinct
        sources = {org, conv, proc, model}
        self.assertEqual(len(sources), 4)


class TestSANJAYAMemory(unittest.TestCase):
    """Test the unified SANJAYA memory interface."""

    def test_start_query_initializes_working_memory(self):
        from kurukshetra.agent.memory_store import SANJAYAMemory
        mem = SANJAYAMemory()
        mem.start_query("What is G3?")
        self.assertEqual(mem.working.current_query, "What is G3?")
        self.assertGreater(mem.working.started_at, 0)

    def test_record_episode_and_find_similar(self):
        from kurukshetra.agent.memory_store import SANJAYAMemory
        mem = SANJAYAMemory()
        mem.start_query("What is G3 RMS?")
        mem.record_episode(answer="G3 is RMS", confidence=0.8, abstained=False)
        similar = mem.episodic.find_similar_queries("What is G3?")
        self.assertGreater(len(similar), 0)

    def test_prospective_memory_detection(self):
        from kurukshetra.agent.memory_store import SANJAYAMemory
        mem = SANJAYAMemory()
        mem.start_query("Remind me to check G3 status tomorrow")
        pending = mem.prospective.get_pending_tasks()
        self.assertGreater(len(pending), 0)

    def test_knowledge_source_summary(self):
        from kurukshetra.agent.memory_store import SANJAYAMemory, AttributedClaim, KnowledgeSource
        mem = SANJAYAMemory()
        mem.start_query("What is G3?")
        mem.add_claim("G3 is RMS", KnowledgeSource.ORGANIZATION, 0.85, ["D1"])
        mem.add_claim("SPM uses G3", KnowledgeSource.ORGANIZATION, 0.80, ["D2"])
        summary = mem.get_knowledge_source_summary()
        self.assertIn("organization", summary)
        self.assertEqual(summary["organization"]["count"], 2)


if __name__ == "__main__":
    unittest.main()
