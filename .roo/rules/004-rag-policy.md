# Multi-RAG Execution Policy

## Objective

Retrieve the best evidence before generating an answer.

## Retrieval Strategy

Prefer this order:

1. Metadata filtering
2. Hybrid retrieval (BM25 + dense)
3. Reranking
4. Response generation

Do not rely on semantic search alone.

## Context Discipline

* Retrieve only relevant documents.
* Prefer multiple small evidence chunks over one large document.
* Avoid unnecessary context expansion.

## Response Requirements

Answers should prioritize:

* correctness
* traceability
* maintainability

When evidence is conflicting, present both interpretations with their supporting sources.

## Future Compatibility

This policy must remain compatible with graph retrieval, rerankers, incremental indexing, and agentic routing without requiring changes to higher-level architecture.
