"""
Command Center Backend API

FastAPI backend for querying SPM documents through KURUKSHETRA RAG system.
"""
from fastapi import FastAPI, HTTPException
from typing import List, Optional
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from kurukshetra.core import KurukshetraSystem, Team, QueryRequest, QueryResponse, DocumentMetadata
from sanjay.scoring_system import RAGMultiScorer

app = FastAPI(
    title="Command Center API",
    description="API for querying SPM documents through KURUKSHETRA RAG system",
    version="1.0.0"
)

# Global instances
system: Optional[KurukshetraSystem] = None
scorer: Optional[RAGMultiScorer] = None


@app.on_event("startup")
async def startup_event():
    """Initialize KURUKSHETRA system and RAG scorer on startup"""
    global system, scorer
    
    # Initialize KURUKSHETRA system
    system = KurukshetraSystem()
    
    # Add SPM team with proper Team object instantiation
    spm_team = Team(
        id="spm-team",
        name="SPM Team",
        description="Service Performance Management team handling document processing and queries"
    )
    system.add_team(spm_team)
    
    # Add SPM pattern rules for document classification
    from kurukshetra.core import PatternRule, DocumentType
    spm_rule = PatternRule(
        pattern_id="spm-patterns",
        name="SPM Document Patterns",
        regex=r"(g3|rms|decision.*upload|catchup|installation|configuration)",
        keyword_list=[
            "G3 RMS",
            "decision upload",
            "first decision",
            "full upload",
            "catchup",
            "roll back",
            "add property",
            "installation process",
            "configuration file"
        ],
        doc_types=[DocumentType.PROJECT, DocumentType.REPORT, DocumentType.DESIGN],
        confidence_weight=1.5
    )
    system.add_pattern_rule(spm_rule)
    
    # Initialize RAG scorer
    scorer = RAGMultiScorer()
    
    print("Command Center backend initialized successfully")


@app.get("/api/health", tags=["Health"])
def health_check() -> dict:
    """Health check endpoint"""
    return {"status": "healthy", "system_ready": system is not None}


@app.post("/api/query", response_model=QueryResponse, tags=["Query"])
def query_documents(request: QueryRequest) -> QueryResponse:
    """
    Query documents through KURUKSHETRA RAG system
    
    Example request:
    {
        "query": "How to handle G3 RMS decision upload failures?",
        "team_id": "spm-team",
        "confidence_threshold": 5,
        "max_results": 10
    }
    """
    try:
        if system is None:
            raise HTTPException(status_code=500, detail="System not initialized")
        
        response = system.query_documents(request)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
