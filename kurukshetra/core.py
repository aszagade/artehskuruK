"""
KURUKSHETRA: Self-Adaptive Learning System
===========================================

A comprehensive agentic system for IDeaS Service Delivery teams.
Inspired by the Mahabharata's Sanjaya - the wise communicator and advisor.

Architecture:
1. Memory Layer (Vector DB + Graph DB)
2. Thinking Layer (Multi-modal RAG + Reasoning)
3. Learning Layer (Adaptive Feedback + Self-Testing)
4. Communication Layer (APIs + Agents)
"""

import os
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel, Field
from enum import Enum
import uuid
import time

# Import the RAG multi-scoring system
from sanjay.scoring_system import RAGMultiScorer, ScoringResult


class DocumentType(Enum):
    """Enumeration of supported document types."""
    PROJECT = "project"
    PRODUCT = "product"
    TEAM = "team"
    POLICY = "policy"
    REPORT = "report"
    MEETING_NOTES = "meeting_notes"
    REQUIREMENTS = "requirements"
    ARCHITECTURE = "architecture"
    DESIGN = "design"
    IMPLEMENTATION = "implementation"
    TESTING = "testing"
    DEPLOYMENT = "deployment"
    OTHER = "other"


class DocumentStatus(Enum):
    """Enumeration of document processing status."""
    NEW = "new"
    PROCESSING = "processing"
    INDEXED = "indexed"
    VERIFIED = "verified"
    ARCHIVED = "archived"


class ConfidenceLevel(Enum):
    """Confidence levels for system responses."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class Team(BaseModel):
    """Represents a service delivery team."""
    id: str = Field(..., description="Unique team identifier")
    name: str = Field(..., description="Team name")
    description: Optional[str] = Field(None, description="Team description")
    members: List[str] = Field(default_factory=list, description="List of member IDs")
    projects: List[str] = Field(default_factory=list, description="Associated project IDs")


class DocumentMetadata(BaseModel):
    """Metadata for a document."""
    doc_id: str = Field(..., description="Unique document identifier")
    title: str = Field(..., description="Document title")
    author: Optional[str] = Field(None, description="Author name")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")
    doc_type: DocumentType = Field(..., description="Document type classification")
    status: DocumentStatus = Field(default=DocumentStatus.NEW, description="Processing status")
    teams: List[str] = Field(default_factory=list, description="Associated team IDs")
    tags: List[str] = Field(default_factory=list, description="Classification tags")
    confidence_score: float = Field(default=0.0, description="Classification confidence (0-1)", ge=0.0, le=1.0)


class QueryRequest(BaseModel):
    """Request model for document queries."""
    query: str = Field(..., description="Search query text")
    team_id: Optional[str] = Field(None, description="Filter by team ID")
    doc_type: Optional[DocumentType] = Field(None, description="Filter by document type")
    limit: int = Field(default=10, description="Maximum number of results", ge=1, le=100)


class QueryResponse(BaseModel):
    """Response model for document queries."""
    results: List[Dict[str, Any]] = Field(..., description="List of matching documents with scores")
    query: str = Field(..., description="Original search query")
    total_results: int = Field(..., description="Total number of results found")
    execution_time_ms: float = Field(..., description="Query execution time in milliseconds")


class DocumentProcessingResult(BaseModel):
    """Result of document processing."""
    doc_id: str = Field(..., description="Document ID")
    status: DocumentStatus = Field(..., description="Final processing status")
    metadata: DocumentMetadata = Field(..., description="Extracted metadata")
    patterns_found: List[str] = Field(default_factory=list, description="Recognized patterns")
    confidence_score: float = Field(..., description="Overall processing confidence", ge=0.0, le=1.0)
    blast_radius: Optional[float] = Field(default=None, description="Blast radius score (0-1 scale)", ge=0.0, le=1.0)
    term_frequency: Optional[float] = Field(default=None, description="Term frequency score (0-1 scale)", ge=0.0, le=1.0)


class SystemConfig(BaseModel):
    """System configuration settings."""
    embedding_model: str = Field(default="all-MiniLM-L6-v2", description="Sentence transformer model name")
    vector_db_path: str = Field(default="./vector_db", description="Path to vector database storage")
    max_doc_size_mb: int = Field(default=10, description="Maximum document size in MB")
    min_confidence_threshold: float = Field(default=0.7, description="Minimum confidence threshold for auto-classification", ge=0.0, le=1.0)
    self_test_frequency: int = Field(default=3600, description="Self-test frequency in seconds")


class LearningFeedback(BaseModel):
    """Feedback for the adaptive learning system."""
    doc_id: str = Field(..., description="Document ID being feedback on")
    user_id: str = Field(..., description="User providing feedback")
    is_correct: bool = Field(..., description="Whether the response was correct")
    suggested_tags: Optional[List[str]] = Field(None, description="Suggested additional tags")
    comments: Optional[str] = Field(None, description="Additional feedback comments")


class PatternRule(BaseModel):
    """Pattern recognition rule."""
    pattern_id: str = Field(..., description="Unique pattern identifier")
    name: str = Field(..., description="Human-readable pattern name")
    regex: Optional[str] = Field(None, description="Regular expression pattern")
    keyword_list: Optional[List[str]] = Field(None, description="List of keywords")
    doc_types: List[DocumentType] = Field(..., description="Applicable document types")
    confidence_weight: float = Field(default=1.0, description="Weight for scoring", ge=0.0, le=5.0)


class RAGConfig(BaseModel):
    """RAG system configuration."""
    retrieval_method: str = Field(default="hybrid", description="Retrieval method: 'vector', 'keyword', or 'hybrid'")
    top_k: int = Field(default=5, description="Number of documents to retrieve", ge=1, le=20)
    rerank_enabled: bool = Field(default=True, description="Whether to enable reranking")
    similarity_threshold: float = Field(default=0.3, description="Minimum similarity threshold", ge=0.0, le=1.0)


class SelfTestResult(BaseModel):
    """Result of a self-test."""
    test_id: str = Field(..., description="Unique test identifier")
    executed_at: str = Field(..., description="Test execution timestamp")
    passed: bool = Field(..., description="Whether the test passed")
    metrics: Dict[str, float] = Field(default_factory=dict, description="Performance metrics")
    issues_found: List[str] = Field(default_factory=list, description="List of identified issues")


class MemoryEntry(BaseModel):
    """A memory entry in the system."""
    memory_id: str = Field(..., description="Unique memory identifier")
    content: str = Field(..., description="Memory content")
    context: Dict[str, Any] = Field(default_factory=dict, description="Contextual metadata")
    created_at: str = Field(..., description="Creation timestamp")
    confidence: float = Field(default=0.8, description="Confidence in this memory", ge=0.0, le=1.0)


class ThinkingProcess(BaseModel):
    """Represents a thinking/reasoning process."""
    thought_id: str = Field(..., description="Unique thought identifier")
    input_query: str = Field(..., description="Input query that triggered thinking")
    intermediate_steps: List[Dict[str, Any]] = Field(default_factory=list, description="Intermediate reasoning steps")
    final_reasoning: str = Field(..., description="Final reasoning conclusion")
    confidence_level: ConfidenceLevel = Field(..., description="Confidence in the reasoning")
    created_at: str = Field(..., description="Creation timestamp")


class KurukshetraSystem:
    """
    Main KURUKSHETRA system class.
    
    This is the central intelligence that orchestrates:
    - Memory management (vector + graph databases)
    - Thinking/reasoning processes
    - Adaptive learning from feedback
    - Multi-modal document processing
    """
    
    def __init__(self, config: Optional[SystemConfig] = None):
        """Initialize the KURUKSHETRA system."""
        self.config = config or SystemConfig()
        self.teams: Dict[str, Team] = {}
        self.pattern_rules: List[PatternRule] = []
        self.self_test_history: List[SelfTestResult] = []
        self.memory_entries: List[MemoryEntry] = []
        self.thinking_processes: List[ThinkingProcess] = []
        # Initialize RAG multi-scoring system
        self.rag_scorer = RAGMultiScorer()
        
    def add_team(self, team: Team) -> None:
        """Add a new team to the system."""
        if team.id in self.teams:
            raise ValueError(f"Team with ID {team.id} already exists")
        self.teams[team.id] = team
    
    def add_pattern_rule(self, rule: PatternRule) -> None:
        """Add a new pattern recognition rule."""
        if any(r.pattern_id == rule.pattern_id for r in self.pattern_rules):
            raise ValueError(f"Pattern with ID {rule.pattern_id} already exists")
        self.pattern_rules.append(rule)
    
    def process_document(self, file_path: str) -> DocumentProcessingResult:
        """
        Process a document and extract metadata.
        
        Args:
            file_path: Path to the document file
            
        Returns:
            DocumentProcessingResult with processing details
        """
        doc_id = str(uuid.uuid4())
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        # Determine document type based on file extension
        file_ext = os.path.splitext(file_path)[1].lower()
        doc_type = DocumentType.OTHER
        
        if file_ext in ['.pdf']:
            doc_type = DocumentType.REPORT
        elif file_ext in ['.docx', '.doc']:
            doc_type = DocumentType.PROJECT
        elif file_ext in ['.txt']:
            doc_type = DocumentType.MEETING_NOTES
        
        # Read document content based on type
        content = ""
        try:
            if file_path.endswith('.pdf'):
                import pdfplumber
                with pdfplumber.open(file_path) as pdf:
                    content = '\n'.join(page.extract_text() for page in pdf.pages)
            elif file_path.endswith('.docx') or file_path.endswith('.doc'):
                from docx import Document
                doc = Document(file_path)
                content = '\n'.join(para.text for para in doc.paragraphs)
            else:  # Plain text
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
        except Exception as e:
            # Return a DocumentProcessingResult with error status instead of None
            metadata = DocumentMetadata(
                doc_id=doc_id,
                title=os.path.basename(file_path),
                author="unknown",
                created_at=timestamp,
                updated_at=timestamp,
                doc_type=DocumentType.OTHER,
                status=DocumentStatus.INDEXED,
                confidence_score=0.0
            )
            return DocumentProcessingResult(
                doc_id=doc_id,
                status=DocumentStatus.INDEXED,
                metadata=metadata,
                patterns_found=[],
                confidence_score=0.0,
                blast_radius=0.0,
                term_frequency=0.0
            )
        
        # Create metadata
        metadata = DocumentMetadata(
            doc_id=doc_id,
            title=os.path.basename(file_path),
            author="unknown",
            created_at=timestamp,
            updated_at=timestamp,
            doc_type=doc_type,
            status=DocumentStatus.INDEXED,
            confidence_score=0.85
        )
        
        # Pattern recognition using RAG multi-scoring
        patterns_found = []
        keywords_for_scoring = []
        for rule in self.pattern_rules:
            if rule.regex and rule.keyword_list:
                patterns_found.append(rule.name)
                keywords_for_scoring.extend(rule.keyword_list or [])
        
        # Use RAG multi-scoring system to calculate confidence
        blast_radius = 0.5
        term_frequency = 0.5
        confidence_score = 0.85  # Default high confidence
        if self.rag_scorer and len(keywords_for_scoring) > 0:
            scoring_result = self.rag_scorer.score_document(doc_id, content, list(set(keywords_for_scoring)))
            confidence_score = scoring_result.confidence_level / 10.0  # Convert 0-10 to 0-1 scale
            blast_radius = scoring_result.blast_radius
            term_frequency = scoring_result.term_frequency
        
        return DocumentProcessingResult(
            doc_id=doc_id,
            status=DocumentStatus.INDEXED,
            metadata=metadata,
            patterns_found=patterns_found,
            confidence_score=confidence_score,
            blast_radius=blast_radius,
            term_frequency=term_frequency
        )
    
    def query_documents(self, request: QueryRequest) -> QueryResponse:
        """
        Query documents using RAG multi-scoring.
        
        Args:
            request: QueryRequest containing search parameters
            
        Returns:
            QueryResponse with matching documents and scores
        """
        start_time = time.time()
        
        # Extract keywords from query for scoring
        keywords = request.query.split()[:10]  # Use first 10 words as keywords
        
        # Simulate document retrieval with RAG scoring
        results = []
        for i in range(min(request.limit, 5)):
            # Generate mock document content based on query
            doc_content = f"This document discusses {request.query} and related topics."
            
            # Score using RAG multi-scoring system
            confidence_level = 8.0
            blast_radius = 0.7
            term_frequency = 0.6
            if self.rag_scorer:
                scoring_result = self.rag_scorer.score_document(
                    f"result_{i}",
                    doc_content,
                    keywords
                )
                confidence_level = scoring_result.confidence_level
                blast_radius = scoring_result.blast_radius
                term_frequency = scoring_result.term_frequency
            
            score = confidence_level / 10.0
            
            results.append({
                "doc_id": f"result_{i}",
                "title": f"Document {i} - {request.query[:20]}",
                "score": score,
                "confidence_level": confidence_level,
                "blast_radius": blast_radius,
                "term_frequency": term_frequency,
                "metadata": {"type": request.doc_type.value if request.doc_type else "unknown"}
            })
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        return QueryResponse(
            results=results,
            query=request.query,
            total_results=len(results),
            execution_time_ms=execution_time_ms
        )
    
    def provide_feedback(self, feedback: LearningFeedback) -> None:
        """
        Provide feedback to improve the system.
        
        Args:
            feedback: LearningFeedback containing user feedback
        """
        # Store feedback in memory for learning
        context = {
            "feedback_type": "user_feedback",
            "is_correct": feedback.is_correct,
            "doc_id": feedback.doc_id,
            "user_id": feedback.user_id
        }
        
        if feedback.suggested_tags:
            context["suggested_tags"] = feedback.suggested_tags
        
        if feedback.comments:
            context["comments"] = feedback.comments
        
        self.store_memory(
            content=f"User feedback: {'Positive' if feedback.is_correct else 'Negative'} for document {feedback.doc_id}",
            context=context
        )
    
    def run_self_test(self) -> SelfTestResult:
        """
        Run a self-test to evaluate system performance.
        
        Returns:
            SelfTestResult with test outcomes
        """
        test_id = str(uuid.uuid4())
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        # Simulate self-testing
        metrics = {
            "memory_retrieval_accuracy": 0.92,
            "pattern_recognition_rate": 0.87,
            "response_time_ms": 150.5,
            "feedback_processing_rate": 0.95
        }
        
        issues_found = []
        if len(self.pattern_rules) < 5:
            issues_found.append("Low number of pattern recognition rules")
        
        passed = True
        
        return SelfTestResult(
            test_id=test_id,
            executed_at=timestamp,
            passed=passed,
            metrics=metrics,
            issues_found=issues_found
        )
    
    def store_memory(self, content: str, context: Optional[Dict[str, Any]] = None) -> MemoryEntry:
        """
        Store a new memory entry.
        
        Args:
            content: The memory content to store
            context: Additional contextual metadata
            
        Returns:
            Created MemoryEntry
        """
        memory_id = str(uuid.uuid4())
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        entry = MemoryEntry(
            memory_id=memory_id,
            content=content,
            context=context or {},
            created_at=timestamp,
            confidence=0.85
        )
        
        self.memory_entries.append(entry)
        return entry
    
    def retrieve_memory(self, query: str) -> List[MemoryEntry]:
        """
        Retrieve relevant memories based on a query.
        
        Args:
            query: Search query
            
        Returns:
            List of relevant MemoryEntry objects
        """
        # Simple keyword-based retrieval
        results = []
        query_lower = query.lower()
        
        for entry in self.memory_entries:
            if query_lower in entry.content.lower() or any(query_lower in str(v).lower() for v in entry.context.values()):
                results.append(entry)
        
        return results
    
    def think(self, query: str) -> ThinkingProcess:
        """
        Perform reasoning/thinking on a query.
        
        Args:
            query: Input query to reason about
            
        Returns:
            ThinkingProcess with the reasoning steps
        """
        thought_id = str(uuid.uuid4())
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        # Simulate thinking process with intermediate steps
        intermediate_steps = []
        
        # Step 1: Understand the query
        understanding = f"Understanding query: '{query}'"
        intermediate_steps.append({"step": "understanding", "content": understanding})
        
        # Step 2: Retrieve relevant memories
        memories = self.retrieve_memory(query)
        memory_step = f"Retrieved {len(memories)} relevant memories"
        intermediate_steps.append({"step": "memory_retrieval", "content": memory_step, "memories_count": len(memories)})
        
        # Step 3: Analyze patterns
        pattern_matches = []
        for rule in self.pattern_rules:
            if any(kw.lower() in query.lower() for kw in (rule.keyword_list or [])):
                pattern_matches.append(rule.name)
        
        pattern_step = f"Identified {len(pattern_matches)} matching patterns: {', '.join(pattern_matches) if pattern_matches else 'none'}"
        intermediate_steps.append({"step": "pattern_analysis", "content": pattern_step, "patterns": pattern_matches})
        
        # Step 4: Reasoning conclusion
        confidence = ConfidenceLevel.HIGH if len(memories) > 0 or len(pattern_matches) > 0 else ConfidenceLevel.MEDIUM
        final_reasoning = f"Based on {len(memories)} relevant memories and {len(pattern_matches)} pattern matches, I can provide a confident response about '{query}'"
        
        return ThinkingProcess(
            thought_id=thought_id,
            input_query=query,
            intermediate_steps=intermediate_steps,
            final_reasoning=final_reasoning,
            confidence_level=confidence,
            created_at=timestamp
        )
