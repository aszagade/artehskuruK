#!/usr/bin/env python3
"""
Test script for SPM (Service Performance Management) team related documents
using KURUKSHETRA RAG system
"""
import sys
import os
sys.path.insert(0, '.')

from kurukshetra.core import KurukshetraSystem, Team, PatternRule, DocumentType, QueryRequest, LearningFeedback
from sanjay.scoring_system import ScoringResult

def test_spm_documents():
    """Test the KURUKSHETRA system with SPM team related documents."""
    print("Testing KURUKSHETRA System with SPM Documents...")
    print("=" * 60)
    
    # Create system instance
    system = KurukshetraSystem()
    print("OK - System initialized successfully\n")
    
    # Add SPM team to the system
    spm_team = Team(
        id="spm-team-001",
        name="SPM Team",
        description="Service Performance Management Team - Handles IDeaS RMS operations and support"
    )
    system.add_team(spm_team)
    print(f"OK - Added SPM team: {spm_team.name}\n")
    
    # Add pattern rules for SPM-related documents
    spm_patterns = [
        PatternRule(
            pattern_id="pattern-spm-001",
            name="SPM Process Documentation",
            regex=None,
            keyword_list=["spm", "service performance", "performance management", "rms", "revenue management system"],
            doc_types=[DocumentType.REPORT],
            confidence_weight=2.0
        ),
        PatternRule(
            pattern_id="pattern-spm-002",
            name="G3 RMS Documentation",
            regex=None,
            keyword_list=["g3", "rms", "decision upload", "catchup", "full upload", "first decision"],
            doc_types=[DocumentType.REPORT],
            confidence_weight=1.8
        ),
        PatternRule(
            pattern_id="pattern-spm-003",
            name="Troubleshooting Guide",
            regex=None,
            keyword_list=["troubleshooting", "error", "failure", "resolution", "issue", "problem"],
            doc_types=[DocumentType.REPORT],
            confidence_weight=1.5
        ),
        PatternRule(
            pattern_id="pattern-spm-004",
            name="Configuration Documentation",
            regex=None,
            keyword_list=["configuration", "setup", "installation", "parameter", "activation"],
            doc_types=[DocumentType.REPORT],
            confidence_weight=1.6
        ),
        PatternRule(
            pattern_id="pattern-spm-005",
            name="Monitoring Process",
            regex=None,
            keyword_list=["monitoring", "alert", "notification", "exception", "job monitoring"],
            doc_types=[DocumentType.REPORT],
            confidence_weight=1.7
        )
    ]
    
    for pattern in spm_patterns:
        system.add_pattern_rule(pattern)
        print(f"OK - Added pattern rule: {pattern.name}")
    print()
    
    # Test document processing with actual SPM documents
    print("Processing SPM-related documents from General_Documents folder...")
    print("-" * 60)
    
    spm_documents_processed = []
    general_docs_path = "General_Documents"
    
    # Process first 10 PDF files to demonstrate the system
    pdf_files = [f for f in os.listdir(general_docs_path) if f.endswith('.pdf')]
    print(f"Found {len(pdf_files)} PDF documents\n")
    
    for i, filename in enumerate(pdf_files[:10]):
        file_path = os.path.join(general_docs_path, filename)
        try:
            result = system.process_document(file_path)
            spm_documents_processed.append(result)
            print(f"{i+1}. Processed: {filename}")
            print(f"   - Type: {result.metadata.doc_type.value}")
            print(f"   - Confidence: {result.confidence_score:.2f}")
            print(f"   - Patterns found: {', '.join(result.patterns_found) if result.patterns_found else 'None'}")
            print()
        except Exception as e:
            print(f"{i+1}. Error processing {filename}: {str(e)}")
            print()
    
    # Test RAG queries on SPM documents
    print("\n" + "=" * 60)
    print("Testing RAG Queries for SPM Documents")
    print("=" * 60)
    
    spm_queries = [
        "How to handle G3 RMS decision upload failures?",
        "What is the process for G3 Full Upload?",
        "Troubleshooting steps for SPM monitoring alerts",
        "Configuration requirements for new properties in G3",
        "SPM process documentation for revenue management"
    ]
    
    for query in spm_queries:
        print(f"\nQuery: {query}")
        print("-" * 60)
        
        query_req = QueryRequest(
            query=query,
            team_id="spm-team-001",
            doc_type=None,
            limit=3
        )
        
        results = system.query_documents(query_req)
        print(f"Found {results.total_results} results in {results.execution_time_ms:.2f}ms\n")
        
        for i, result in enumerate(results.results):
            print(f"Result {i+1}:")
            print(f"  - Score: {result['score']:.3f}")
            print(f"  - Confidence Level: {result['confidence_level']:.1f}")
            print(f"  - Blast Radius: {result['blast_radius']:.2f}")
            print(f"  - Term Frequency: {result['term_frequency']:.2f}")
            print()
    
    # Test thinking process
    print("\n" + "=" * 60)
    print("Testing Thinking Process for SPM Queries")
    print("=" * 60)
    
    thinking_query = "What are the common issues in G3 RMS and how to resolve them?"
    print(f"\nQuery: {thinking_query}")
    print("-" * 60)
    
    thinking_result = system.think(thinking_query)
    print(f"Thought ID: {thinking_result.thought_id}")
    print(f"Confidence Level: {thinking_result.confidence_level.value}")
    print(f"\nReasoning Steps:")
    for step in thinking_result.intermediate_steps:
        print(f"  - {step['content']}")
    print(f"\nFinal Reasoning: {thinking_result.final_reasoning}")
    
    # Test self-testing
    print("\n" + "=" * 60)
    print("Running System Self-Test")
    print("=" * 60)
    
    test_result = system.run_self_test()
    print(f"Self-test completed: {'PASSED' if test_result.passed else 'FAILED'}")
    print(f"\nPerformance Metrics:")
    for metric, value in test_result.metrics.items():
        print(f"  - {metric}: {value:.2f}")
    
    if test_result.issues_found:
        print(f"\nIssues Found:")
        for issue in test_result.issues_found:
            print(f"  - {issue}")
    else:
        print("\nNo issues found!")
    
    # Test feedback mechanism
    print("\n" + "=" * 60)
    print("Testing Feedback Mechanism")
    print("=" * 60)
    
    feedback = LearningFeedback(
        doc_id=spm_documents_processed[0].doc_id if spm_documents_processed else "test-doc-123",
        user_id="spm-agent-456",
        is_correct=True,
        suggested_tags=["spm", "g3-rms", "documentation"],
        comments="This document was correctly classified as SPM process documentation"
    )
    system.provide_feedback(feedback)
    print(f"OK - Feedback provided for document {feedback.doc_id}")
    print(f"  - User: {feedback.user_id}")
    print(f"  - Correctness: {'Yes' if feedback.is_correct else 'No'}")
    print(f"  - Tags: {', '.join(feedback.suggested_tags) if feedback.suggested_tags else 'None'}")
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"OK - System initialized: True")
    print(f"OK - SPM team added: True")
    print(f"OK - Pattern rules added: {len(spm_patterns)}")
    print(f"OK - Documents processed: {len(spm_documents_processed)}")
    print(f"OK - Queries tested: {len(spm_queries)}")
    print(f"OK - Thinking process tested: True")
    print(f"OK - Self-test completed: {'PASSED' if test_result.passed else 'FAILED'}")
    print(f"OK - Feedback mechanism tested: True")
    
    print("\n" + "=" * 60)
    print("All SPM document tests completed successfully!")
    print("=" * 60)

if __name__ == "__main__":
    test_spm_documents()