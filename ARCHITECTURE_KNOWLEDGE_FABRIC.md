# ADR-0001: Knowledge Fabric Architecture

## 1. Purpose

The Knowledge Fabric is the ingestion architecture for KURUKSHETRA's enterprise knowledge base. It preserves all documents as the single source of truth while enabling efficient retrieval and adaptive learning through SEAL (Self-Evolving Adaptive Learning).

Key objectives:
- Ingest structured and unstructured knowledge assets from across IDeaS Service Delivery
- Maintain document integrity and traceability
- Support incremental updates without data loss
- Enable hybrid retrieval strategies for optimal performance
- Ensure future compatibility with emerging RAG techniques

## 2. Design Principles

### Architecture First
- Extend existing modules before creating new ones
- Preserve backward compatibility
- Never move or rename files unless explicitly instructed

### Knowledge Integrity
- Repository documents are the primary authority
- All knowledge assets have defined ownership and visibility levels
- Unknown terms are explicitly marked as UNKNOWN

### Development Workflow
- Configuration separated from code
- Strong typing where practical
- Logging over print statements

### AI Governance
- Every knowledge asset belongs to an owner (Service Delivery, Support, Operations, Revenue, QA, Shared Systems)
- Visibility levels: Public, Internal, Confidential, Restricted
- Never expose Restricted content in generated examples

## 3. Asset Types

The Knowledge Fabric handles three primary asset types:

### Structured Documents
- Process guides, policy documents, technical specifications
- Formatted as Markdown with YAML frontmatter
- Include metadata for ownership, visibility, and confidence scoring

### Unstructured Content
- PDFs, Word documents, presentation slides
- Extracted via specialized parsers maintaining original formatting
- Preserved in raw format alongside processed text

### Code Assets
- Source code files, configuration templates, SQL queries
- Parsed for documentation extraction while preserving syntax
- Linked to version control history

## 4. Ingestion Pipeline

```
[Source Documents]
       |
       v
[Preprocessing Stage]
       |
       v
[Parser Selection]
   /    |    \
Structured Parser  Unstructured Parser  Code Parser
   \     |     /
       v
[Metadata Extraction]
       |
       v
[Validation & Normalization]
       |
       v
[Storage Layer]
```

### Preprocessing Stage
- Document fingerprinting for deduplication
- Format normalization (character encoding, line endings)
- Access control validation

### Parser Selection
- Content-type detection based on file extension and magic numbers
- Fallback to generic text parser for unknown formats
- Preservation of original document structure

### Metadata Extraction
- Automatic extraction from document properties
- Manual override capability for curated assets
- Confidence scoring based on extraction reliability

### Validation & Normalization
- Schema validation against metadata requirements
- Content sanitization without data loss
- Visibility level enforcement

## 5. Incremental Indexing

The Knowledge Fabric supports continuous learning through incremental updates:

### Change Detection
- File system monitoring for new/updated documents
- Version control integration (git hooks, webhooks)
- Scheduled crawls of document repositories

### Delta Processing
- Comparison against previous versions using checksums
- Extraction of changes at paragraph/sentence level
- Preservation of historical context

### Index Updates
- Atomic updates to prevent partial states
- Rollback capability for failed updates
- Change logs for audit trail

## 6. Hybrid Retrieval Strategy

Following the Multi-RAG Execution Policy:

### Metadata Filtering (Priority 1)
- Owner-based filtering for access control
- Visibility level enforcement
- Product/system scoping

### Hybrid Retrieval (Priority 2)
- **BM25**: Traditional keyword-based retrieval with term frequency analysis
- **Dense Vector Search**: Semantic understanding via embeddings
- Complementary results from both methods

### Reranking (Priority 3)
- Cross-referencing between BM25 and dense search results
- Confidence score adjustment based on result consistency
- Positional scoring favoring earlier document sections

### Response Generation (Priority 4)
- Evidence-based generation with source attribution
- Conflict resolution when multiple documents provide different answers
- Uncertainty indication for low-confidence results

## 7. Future Compatibility

The Knowledge Fabric is designed to evolve without breaking changes:

### Modular Design
- Pluggable parser architecture for new document types
- Swappable retrieval components
- Configurable pipeline stages

### Graph Retrieval Ready
- Document relationships captured in metadata
- Preparation for knowledge graph integration
- Semantic linking between related documents

### Incremental Indexing Foundation
- Version-aware storage for time-based queries
- Change tracking for continuous learning
- Rollback capabilities for experimentation

### Policy Compatibility
- Maintains compatibility with:
  - Rerankers (future enhancements)
  - Incremental indexing strategies
  - Graph retrieval approaches
  - Agentic routing mechanisms
