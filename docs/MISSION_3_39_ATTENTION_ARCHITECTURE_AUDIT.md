# Mission 3.39 — Transformer Attention Architecture Audit

**Date:** August 2026  
**Status:** COMPLETE  
**Test Baseline:** 576/576 pass, 0 failures

---

## Executive Summary

Kurukshetra is an **orchestration/knowledge architecture**, not a foundation model. Transformer attention lives inside the embedding model (BGE-M3), the reranker (BGE-reranker-v2-m3), and the generation model (GX10/Mistral). None of these should be reimplemented inside Kurukshetra itself.

**Key finding:** The existing BGE cross-encoder reranker **regresses accuracy from 85% to 65%** at current corpus scale. Attention-based reranking is NOT currently justified. The foundation models already provide the attention intelligence Kurukshetra needs.

---

## 1. Attention Components Audit

### Where Attention Already Exists (Inside Foundation Models)

| Component | Model | Architecture | Attention Type | Role in Kurukshetra |
|-----------|-------|-------------|---------------|---------------------|
| **Embedding Model** | BAAI/bge-m3 | XLM-RoBERTa | Self-attention (12 heads) | Generates 1024-dim dense vectors for semantic search |
| **Reranker** | BAAI/bge-reranker-v2-m3 | XLM-RoBERTa | Cross-attention (query ↔ document) | Jointly attends to query + candidate for relevance scoring |
| **Generation Model** | Mistral Small (via GX10) | Transformer decoder | Causal self-attention | Synthesizes evidence into natural-language answers |

**None of these should be reimplemented inside Kurukshetra.**

### Status Classification

| Capability | Status | Evidence |
|-----------|--------|----------|
| Self-Attention | ALREADY PROVIDED BY MODEL | BGE-M3 uses XLM-RoBERTa self-attention internally |
| Multi-Head Attention | ALREADY PROVIDED BY MODEL | XLM-RoBERTa has 12 attention heads; Mistral has 32 |
| Positional Encoding | ALREADY PROVIDED BY MODEL | RoPE in Mistral; learned positional in XLM-RoBERTa |
| Transformer Encoder | ALREADY PROVIDED BY MODEL | BGE-M3 encoder; BGE-reranker-v2-m3 encoder |
| Transformer Decoder | ALREADY PROVIDED BY MODEL | Mistral decoder (via GX10) |
| Cross-Attention (Reranking) | AVAILABLE THROUGH EXISTING LIBRARY | `BGEReranker` uses `CrossEncoder` (sentence-transformers) |
| Attention-based Reranking | IMPLEMENTED BUT NOT WIRED INTO SANJAYA | `bge_reranker.py` exists; tested; adds 3-4s latency; regresses accuracy |
| Late Interaction (ColBERT) | MISSING | No multi-vector retrieval |
| Custom Attention | NOT JUSTIFIED | Foundation models provide all needed attention |

---

## 2. Where Attention Provides Value Today

### A. Document Understanding (Embedding)

**BGE-M3** generates dense vector representations using self-attention:

```
Document text → BGE-M3 encoder (12-head self-attention) → 1024-dim vector → cosine similarity
```

This is Kurukshetra's primary semantic retrieval mechanism. The attention is **inside the model**, not in Kurukshetra's orchestration layer. This is correct architecture.

**Status:** ✅ ALREADY PROVIDED BY MODEL — working correctly.

### B. Retrieval (BM25 + Vector + Hybrid)

| Technique | Attention Used | Implementation |
|-----------|---------------|----------------|
| BM25 | None (statistical) | `database_bm25.py` — deterministic TF-IDF scoring |
| Vector | Self-attention (via BGE-M3) | `vector.py` — cosine similarity of attention-derived embeddings |
| Hybrid | Normalized combination | `hybrid.py` — 0.5/0.5 weighted fusion |

**Status:** ✅ CORRECT — attention lives where it should (inside the embedding model).

### C. Reranking (Cross-Encoder Attention)

**BGE-reranker-v2-m3** uses cross-attention between query and document:

```
[query tokens] + [document tokens] → Cross-Encoder (joint attention) → relevance score
```

This is the **only place in Kurukshetra where cross-attention (query ↔ document) exists**. It's the theoretically superior approach to query-document matching because it allows the model to attend to specific query-document token interactions rather than comparing independent embeddings.

**Status:** ⚠️ IMPLEMENTED BUT NOT RECOMMENDED FOR PRODUCTION (see experiment below).

### D. Answer Generation (Causal Attention)

**Mistral Small** via GX10 uses causal self-attention to synthesize evidence:

```
System prompt + Evidence context + User query → Mistral decoder → Natural-language answer
```

This is the **most attention-intensive** component. The LLM uses cross-attention between the system prompt, evidence context, and query to generate grounded answers.

**Status:** ✅ ALREADY PROVIDED BY MODEL — working correctly.

---

## 3. A/B Experiment: Hybrid vs Hybrid + BGE Reranking

### Setup

- 20-question evaluation set (17 in-scope, 3 out-of-scope)
- Same retrieval pipeline, same grounding, same LLM
- Only difference: whether BGE cross-encoder reranking is applied after hybrid retrieval

### Results

| Metric | Hybrid Only | Hybrid + BGE Rerank | Delta |
|--------|------------|-------------------|-------|
| **Overall accuracy** | **17/20 (85%)** | **13/20 (65%)** | **-20 points** |
| Correct answers | 14/17 | 10/17 | -4 |
| Correct abstentions | 3/3 | 3/3 | 0 |
| Wrong abstains | 3/17 | 7/17 | **+4 regressions** |
| Hallucinations | 0/3 | 0/3 | 0 |
| Avg latency | **1.7s** | **5.4s** | **+3.7s (3.2× slower)** |

### Per-Query Changes

| Question | Hybrid | Hybrid+Rerank | Impact |
|----------|--------|--------------|--------|
| Q04 "What do you know about ICS?" | ✅ ANSWER | ❌ ABSTAIN | **REGRESSION** |
| Q05 "What do you know about SPM?" | ✅ ANSWER | ❌ ABSTAIN | **REGRESSION** |
| Q13 "Stats to Inventory Transition?" | ✅ ANSWER | ❌ ABSTAIN | **REGRESSION** |
| Q16 "What pricing workflows exist?" | ✅ ANSWER | ❌ ABSTAIN | **REGRESSION** |
| Q03 "Teams with G3?" | conf=0.83 | conf=0.97 | Improvement (but not needed) |

### Root Cause of Regression

The cross-encoder reranker reduces from 10 retrieved chunks to 5 (top_k=5). This **drops evidence below the grounding threshold** for broad/entity queries (ICS, SPM, pricing workflows) where multiple evidence items collectively support the answer.

The grounding system needs **diverse evidence** — not just the top-5 most relevant chunks. Reranking is too aggressive at current scale.

### Verdict

**BGE reranking is NOT recommended for production at current corpus scale.**

Evidence:
- 20-point accuracy regression
- 3.2× latency increase
- 4 additional wrong abstentions
- No hallucination reduction needed (already 0%)

---

## 4. Chunking & Positional Information

### Current State

| Field | Present | Used |
|-------|---------|------|
| `chunk_id` | ✅ | Yes — retrieval, citations |
| `document_id` | ✅ | Yes — provenance |
| `sequence` | ✅ | Yes — ordering within document |
| `char_start` | ✅ | Yes — character offset |
| `char_end` | ✅ | Yes — character offset |
| `text` | ✅ | Yes — content |
| Section heading | ❌ | Not stored in chunk |
| Parent section | ❌ | Not stored in chunk |
| Document structure | ❌ | Not preserved in retrieval |

### Assessment

Positional information (`sequence`, `char_start`, `char_end`) IS preserved in chunks but is NOT used during retrieval. BM25 and vector search treat all chunks independently.

**Is positional information needed?**

For the current architecture, **no**. The retrieval system returns relevant chunks regardless of position. However, for future multi-document reasoning, knowing that "chunk 3 of document X comes before chunk 4" could help reconstruct document flow.

**Status:** ✅ POSITIONAL DATA PRESERVED — not currently used in retrieval, but available.

---

## 5. Multi-Head Attention Assessment

| Question | Answer |
|----------|--------|
| Does Kurukshetra need custom multi-head attention? | **NO** |
| Do foundation models already use multi-head attention? | **YES** — BGE-M3 has 12 heads, Mistral has 32 |
| Does Kurukshetra's orchestration layer need attention? | **NO** — it orchestrates models that have attention |
| Would custom attention improve anything? | **NO** — would duplicate existing capability |

---

## 6. Cross-Attention Assessment

| Question | Answer |
|----------|--------|
| Where does cross-attention exist? | Inside BGE-reranker-v2-m3 (query ↔ document) and Mistral (context ↔ query) |
| Should Kurukshetra add custom cross-attention? | **NO** |
| Could cross-attention improve query/evidence alignment? | **Already provided by reranker** — but regresses at current scale |
| When would cross-attention become valuable? | When corpus > 10,000 documents and evidence diversity matters less |

---

## 7. Query/Evidence Alignment

The grounding failure ("mentions topic" vs "answers question") is a **semantic understanding problem**, not an attention problem. The current extractive answer generator uses keyword overlap to measure relevance — this is the actual bottleneck.

**Potential attention-based solutions (NOT recommended now):**

1. **Cross-encoder reranking** — Already tested, regresses accuracy
2. **LLM-based evidence evaluation** — GX10 already does this when generating answers
3. **Fine-tuned relevance classifier** — Would require training data; not justified at current scale

**Best current approach:** The GX10 LLM already uses attention to evaluate evidence relevance during answer generation. When it says "insufficient evidence," it's using its Transformer attention to determine the evidence doesn't answer the question. This is the correct architecture.

---

## 8. Architectural Principle

```
┌─────────────────────────────────────────────────────┐
│                   KURUKSHETRA                        │
│  Knowledge + Retrieval + Graph + Memory + Agent     │
│  + Security + Evaluation + Orchestration             │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ BM25     │  │ Vector   │  │ Hybrid Fusion    │  │
│  │ (no attn)│  │ (no attn)│  │ (no attn)        │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Graph    │  │ SEAL     │  │ Security/ACL     │  │
│  │ (no attn)│  │ (no attn)│  │ (no attn)        │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│          TRANSFORMER COMPONENTS (external)           │
│                                                      │
│  ┌──────────────────────┐  ┌─────────────────────┐ │
│  │ BGE-M3 Embedding     │  │ BGE-Reranker-v2-m3  │ │
│  │ Self-Attention (12h) │  │ Cross-Attention      │ │
│  │ 1024-dim vectors     │  │ Query↔Doc scoring   │ │
│  └──────────────────────┘  └─────────────────────┘ │
│                                                      │
│  ┌──────────────────────────────────────────────┐  │
│  │ GX10 / Mistral Small                          │  │
│  │ Causal Self-Attention (32 heads)              │  │
│  │ Evidence synthesis + grounded answers         │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## 9. Long-Term Roadmap Items

Keep these in the SANJAYA architecture roadmap. Implement ONLY when benchmark evidence justifies:

| Item | Priority | Trigger |
|------|----------|---------|
| Attention-based reranking | P2 | Corpus > 10,000 docs; reranking improves precision without regressing recall |
| Late interaction (ColBERT) | P3 | When embedding similarity proves insufficient for fine-grained matching |
| Query decomposition with attention | P2 | When cross-document questions become frequent |
| Positional/structural retrieval | P3 | When document structure preservation becomes measurable valuable |
| Fine-tuned domain embeddings | P1 | When generic BGE-M3 shows measurable domain gap |
| Attention-based evidence verification | P2 | When hallucination rate becomes non-zero |

---

## 10. Decision Matrix

| Technique | Current Value | Complexity | Risk | Recommendation |
|-----------|--------------|------------|------|----------------|
| Self-attention (BGE-M3) | ✅ HIGH | — | — | **KEEP** (external model) |
| Cross-attention (reranker) | ⚠️ NEGATIVE | Low | Low | **DEFER** (regresses at current scale) |
| Causal attention (GX10) | ✅ HIGH | — | — | **KEEP** (external model) |
| Custom attention | ❌ NONE | High | High | **DO NOT BUILD** |
| Late interaction | ❌ NOT JUSTIFIED | Medium | Low | **DEFER** |
| Positional encoders | ❌ NOT JUSTIFIED | Medium | Low | **DEFER** |

---

## 11. Files Examined

| File | Relevance |
|------|-----------|
| `kurukshetra/embeddings/bge.py` | BGE-M3 embedding model (self-attention) |
| `kurukshetra/reranking/bge_reranker.py` | BGE cross-encoder (cross-attention) |
| `kurukshetra/llm/client.py` | GX10/Mistral (causal attention) |
| `kurukshetra/retrieval/vector.py` | Vector retrieval (uses attention-derived embeddings) |
| `kurukshetra/retrieval/hybrid.py` | Hybrid fusion (no attention) |
| `kurukshetra/retrieval/bm25.py` | BM25 (no attention) |
| `kurukshetra/chunking/models.py` | Chunk with positional fields |
| `kurukshetra/graph/extractor.py` | Entity extraction (regex, no attention) |
| `kurukshetra/agent/answer_generator.py` | Evidence grounding (no attention) |

---

## 12. Final Answers

### A. Where does attention provide value in Kurukshetra?

**Inside the foundation models only:**
1. BGE-M3 — self-attention for semantic embeddings
2. BGE-reranker — cross-attention for relevance scoring (exists but not recommended)
3. GX10/Mistral — causal attention for answer generation

### B. Should Kurukshetra implement custom attention?

**NO.** Kurukshetra is orchestration. Attention belongs in foundation models.

### C. Is the BGE reranker justified?

**NO, at current scale.** Regresses accuracy 85% → 65%, adds 3.2× latency.

### D. What is the correct architecture?

**Kurukshetra orchestrates; foundation models attend.** This is the correct separation of concerns.

### E. What would change this assessment?

- Corpus > 10,000 documents (reranking becomes valuable for precision)
- Non-zero hallucination rate (attention-based verification becomes valuable)
- Multi-hop questions become frequent (query decomposition with attention)
- Domain-specific embedding gap measured (fine-tuning justified)
