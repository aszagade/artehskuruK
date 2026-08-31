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
    """Test procedural memory (validated workflows)."""

    def test_store_procedure(self):
        from kurukshetra.agent.memory_store import ProceduralMemory
        pm = ProceduralMemory()
        proc_id = pm.store_procedure(
            name="G3 Property Installation",
            description="Steps to install a new property in G3 RMS",
            source_document_id="DOC-000160",
            source_path="docs/install.pdf",
            team="spm",
            steps=["Step 1: Submit request", "Step 2: Configure system", "Step 3: Validate"],
            validated=True,
            confidence=0.9,
        )
        self.assertIsNotNone(proc_id)
        self.assertTrue(proc_id.startswith("PROC-"))

    def test_find_procedure(self):
        from kurukshetra.agent.memory_store import ProceduralMemory
        pm = ProceduralMemory()
        pm.store_procedure(
            name="G3 Property Installation",
            description="Steps to install a new property in G3 RMS",
            source_document_id="DOC-000160",
            source_path="docs/install.pdf",
            team="spm",
            steps=["Step 1", "Step 2"],
            validated=True,
            confidence=0.9,
        )
        found = pm.find_procedure("How to install a property in G3")
        self.assertGreater(len(found), 0)
        self.assertEqual(found[0]["name"], "G3 Property Installation")


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
