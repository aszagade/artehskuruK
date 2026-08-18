# Document Identity Engine

## Purpose

The Identity Engine assigns every knowledge asset a permanent identity before it enters the Knowledge Fabric.

It is independent from RAG, databases, embeddings, and LLMs.

## Responsibilities

- Generate SHA-256 fingerprints
- Create human-readable document IDs
- Represent document identity as a Python model

## Design Principles

- Immutable identity
- Streaming hash generation
- No external dependencies
- Python 3.13 compatible

## Example

| Sequence | Document ID |
|----------|-------------|
| 1 | DOC-000001 |
| 42 | DOC-000042 |
| 325 | DOC-000325 |

The SHA-256 hash remains the cryptographic identity, while the document ID provides a human-friendly reference.