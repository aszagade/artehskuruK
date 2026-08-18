"""
RAG Multi-Scoring System
=========================

This module implements a multi-dimensional scoring system for RAG (Retrieval-Augmented Generation)
document processing, with confidence levels ranging from 0 to 10.

Key Features:
- Blast radius scoring based on keyword proximity
- Term frequency analysis
- Contextual relevance scoring
- Confidence level mapping (0-10 scale)
"""

from typing import List, Dict, Any, Optional
import re
import math
from dataclasses import dataclass


@dataclass
class ScoringResult:
    """Result of document scoring with confidence metrics."""
    document_id: str
    score: float
    confidence_level: int  # 0-10 scale
    blast_radius: float
    term_frequency: float
    contextual_relevance: float
    matching_keywords: List[str]


class RAGMultiScorer:
    """
    Multi-dimensional RAG scorer for document processing.
    
    Confidence Scale (0-10):
    - 0-2: No confidence / irrelevant
    - 3-4: Low confidence / minimal relevance
    - 5-6: Medium confidence / some relevance
    - 7-8: High confidence / strong relevance
    - 9-10: Maximum confidence / exact match
    """
    
    def __init__(self):
        self.known_terms = set()
        self.spm_agent_knowledge = {}
    
    def add_known_term(self, term: str, weight: float = 1.0):
        """Add a known term to the knowledge base."""
        self.known_terms.add(term.lower())
    
    def add_spm_agent_knowledge(self, document_id: str, content: str):
        """Add SPM agent knowledge with document ID."""
        self.spm_agent_knowledge[document_id] = {
            'content': content,
            'score': 0.0,
            'confidence': 0
        }
    
    def calculate_blast_radius(self, text: str, keywords: List[str]) -> float:
        """
        Calculate blast radius based on keyword proximity.
        
        Args:
            text: Document text to analyze
            keywords: List of keywords to search for
            
        Returns:
            Blast radius score (0-1)
        """
        text_lower = text.lower()
        keyword_positions = {}
        
        # Find positions of all keywords
        for keyword in keywords:
            keyword_lower = keyword.lower()
            start = 0
            while True:
                pos = text_lower.find(keyword_lower, start)
                if pos == -1:
                    break
                keyword_positions.setdefault(keyword_lower, []).append(pos)
                start = pos + 1
        
        # Calculate proximity scores
        total_score = 0.0
        keyword_count = len(keywords)
        
        if keyword_count == 0:
            return 0.0
        
        for keyword in keywords:
            positions = keyword_positions.get(keyword.lower(), [])
            if len(positions) > 1:
                # Calculate average distance between consecutive occurrences
                distances = [positions[i+1] - positions[i] for i in range(len(positions)-1)]
                avg_distance = sum(distances) / len(distances)
                # Convert to score (smaller distance = higher blast radius)
                proximity_score = 1.0 / (1.0 + math.exp(avg_distance / 50))
                total_score += proximity_score
        
        if keyword_count > 0:
            return min(total_score / keyword_count, 1.0)
        return 0.0
    
    def calculate_term_frequency(self, text: str, keywords: List[str]) -> float:
        """
        Calculate term frequency score.
        
        Args:
            text: Document text to analyze
            keywords: List of keywords to search for
            
        Returns:
            Term frequency score (0-1)
        """
        text_lower = text.lower()
        total_occurrences = 0
        
        for keyword in keywords:
            keyword_lower = keyword.lower()
            count = len(re.findall(r'\b' + re.escape(keyword_lower) + r'\b', text_lower))
            total_occurrences += count
        
        if not keywords:
            return 0.0
        
        # Normalize by number of keywords and document length
        doc_length = len(text.split())
        if doc_length == 0:
            return 0.0
        
        return min(total_occurrences / (len(keywords) * max(1, math.sqrt(doc_length))), 1.0)
    
    def calculate_contextual_relevance(self, text: str, keywords: List[str]) -> float:
        """
        Calculate contextual relevance based on known terms.
        
        Args:
            text: Document text to analyze
            keywords: List of keywords to search for
            
        Returns:
            Contextual relevance score (0-1)
        """
        text_lower = text.lower()
        matching_terms = 0
        
        # Check how many known terms appear in the document
        for term in self.known_terms:
            if term in text_lower:
                matching_terms += 1
        
        if not self.known_terms:
            return 0.5  # Neutral score when no known terms
        
        return min(matching_terms / len(self.known_terms), 1.0)
    
    def calculate_confidence_score(self, blast_radius: float, term_frequency: float,
                                   contextual_relevance: float) -> int:
        """
        Calculate overall confidence score (0-10).
        
        Args:
            blast_radius: Blast radius score (0-1)
            term_frequency: Term frequency score (0-1)
            contextual_relevance: Contextual relevance score (0-1)
            
        Returns:
            Confidence level (0-10)
        """
        # Weighted average
        weighted_score = (
            blast_radius * 0.4 +  # 40% weight
            term_frequency * 0.3 +  # 30% weight
            contextual_relevance * 0.3  # 30% weight
        )
        
        # Convert to 0-10 scale
        confidence = round(weighted_score * 10)
        return max(0, min(10, confidence))
    
    def score_document(self, document_id: str, text: str, keywords: List[str]) -> ScoringResult:
        """
        Score a document using multi-dimensional RAG scoring.
        
        Args:
            document_id: Unique identifier for the document
            text: Document text to analyze
            keywords: List of keywords to search for
            
        Returns:
            ScoringResult with all metrics
        """
        blast_radius = self.calculate_blast_radius(text, keywords)
        term_frequency = self.calculate_term_frequency(text, keywords)
        contextual_relevance = self.calculate_contextual_relevance(text, keywords)
        confidence_level = self.calculate_confidence_score(blast_radius, term_frequency, contextual_relevance)
        
        # Find matching keywords
        text_lower = text.lower()
        matching_keywords = [kw for kw in keywords if kw.lower() in text_lower]
        
        return ScoringResult(
            document_id=document_id,
            score=blast_radius * 0.4 + term_frequency * 0.3 + contextual_relevance * 0.3,
            confidence_level=confidence_level,
            blast_radius=blast_radius,
            term_frequency=term_frequency,
            contextual_relevance=contextual_relevance,
            matching_keywords=matching_keywords
        )
    
    def get_agent_confidence(self, agent_name: str) -> int:
        """
        Get current confidence level for an agent (0-10).
        
        Args:
            agent_name: Name of the agent (e.g., 'SPM Agent')
            
        Returns:
            Confidence level (0-10)
        """
        if agent_name == 'SPM Agent':
            # Calculate based on known documents
            total_score = sum(doc['score'] for doc in self.spm_agent_knowledge.values())
            doc_count = len(self.spm_agent_knowledge)
            
            if doc_count == 0:
                return 0
            
            avg_confidence = round((total_score / doc_count) * 10)
            return max(0, min(10, avg_confidence))
        
        return 0
    
    def update_agent_knowledge(self, agent_name: str, document_id: str, score: float):
        """
        Update agent knowledge with new document scores.
        
        Args:
            agent_name: Name of the agent
            document_id: Document ID to update
            score: New score (0-1)
            
        Returns:
            Updated confidence level (0-10)
        """
        if agent_name == 'SPM Agent' and document_id in self.spm_agent_knowledge:
            self.spm_agent_knowledge[document_id]['score'] = score
            confidence = round(score * 10)
            self.spm_agent_knowledge[document_id]['confidence'] = confidence
            return confidence
        
        return 0