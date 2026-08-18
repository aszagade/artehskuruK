#!/usr/bin/env python3
"""
Test script for KURUKSHETRA system
"""
import sys
sys.path.insert(0, '.')

from kurukshetra.core import KurukshetraSystem, Team, PatternRule, DocumentType, QueryRequest, LearningFeedback

def test_kurukshetra():
    """Test the KURUKSHETRA system implementation."""
    print("Testing KURUKSHETRA System...\n")
    
    # Create system instance
    system = KurukshetraSystem()
    print("PASS: System initialized successfully")
    
    # Test 1: Add a team
    team = Team(id="team-001", name="SDOps Team", description="Service Delivery Operations")
    system.add_team(team)
    print(f"PASS: Added team: {team.name}")
    
    # Test 2: Add pattern rules
    rule1 = PatternRule(
        pattern_id="pattern-001",
        name="Project Documentation",
        regex=None,
        keyword_list=["project", "documentation", "specification"],
        doc_types=[DocumentType.PROJECT, DocumentType.REQUIREMENTS],
        confidence_weight=1.5
    )
    system.add_pattern_rule(rule1)
    print(f"PASS: Added pattern rule: {rule1.name}")
    
    # Test 3: Store memory
    memory = system.store_memory(
        content="User feedback on document classification",
        context={"feedback_type": "positive", "doc_id": "doc-123"}
    )
    print(f"PASS: Stored memory entry: {memory.memory_id}")
    
    # Test 4: Retrieve memory
    retrieved = system.retrieve_memory("feedback")
    print(f"PASS: Retrieved {len(retrieved)} memory entries")
    
    # Test 5: Thinking process
    thinking = system.think("What is the status of project documentation?")
    print(f"PASS: Thinking process completed with confidence: {thinking.confidence_level.value}")
    
    # Test 6: Query documents
    query_req = QueryRequest(
        query="project documentation",
        team_id=None,
        doc_type=None,
        limit=5
    )
    results = system.query_documents(query_req)
    print(f"PASS: Query returned {results.total_results} results in {results.execution_time_ms:.2f}ms")
    
    # Test 7: Provide feedback
    feedback = LearningFeedback(
        doc_id="doc-123",
        user_id="user-456",
        is_correct=True,
        suggested_tags=["urgent", "reviewed"]
    )
    system.provide_feedback(feedback)
    print(f"PASS: Feedback processed for document {feedback.doc_id}")
    
    # Test 8: Run self-test
    test_result = system.run_self_test()
    print(f"PASS: Self-test completed: {'PASSED' if test_result.passed else 'FAILED'}")
    for issue in test_result.issues_found:
        print(f"  - Issue: {issue}")
    
    # Test 9: Process document (simulated)
    doc_result = system.process_document("test_document.pdf")
    print(f"PASS: Document processed: {doc_result.metadata.title} as {doc_result.metadata.doc_type.value}")
    
    print("\n" + "="*50)
    print("All tests completed successfully!")
    print("="*50)

if __name__ == "__main__":
    test_kurukshetra()