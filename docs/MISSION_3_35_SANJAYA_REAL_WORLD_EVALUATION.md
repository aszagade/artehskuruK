# Mission 3.35 — SANJAYA Real-World Evaluation

## Date
August 28, 2026

## Corpus

| Metric | Value |
|---|---|
| Total documents | 615 |
| ICS/Omkar documents | 16 |
| Total chunks | 3,616 |
| Graph entities | 4,195 |
| Teams | SPM (122), ICS (95), IT (62), ROA (37), SDOPS (35), HR (28), CPM (8), UNKNOWN (228) |

## Configuration

| Setting | Value |
|---|---|
| Retrieval strategy | Hybrid (BM25 + Vector, normalized 0.5/0.5) |
| Visibility | Internal (max) |
| LLM | GX10 mistral-small (available: True) |
| Temperature | 0.1 |
| Top-K | 5 |

## Overall Results

| Metric | Extractive | LLM |
|---|---|---|
| Questions evaluated | 25 | 25 |
| Answered correctly | 22 | — |
| Abstained correctly | 1 | — |
| Abstained incorrectly (missed answer) | 0 | — |
| Answer quality: good | 21 | — |
| Answer quality: partial | 0 | — |
| Answer quality: poor | 1 | — |
| Average latency | 28ms | 11986ms |

## Per-Question Results

| ID | Category | Expected | Ext Behavior | Ext Quality | LLM Behavior | LLM Quality | Ext Latency | LLM Latency |
|---|---|---|---|---|---|---|---|---|
| Q01 | SPM-Configuration | answer | ANSWER | good | ANSWER | good | 43ms | 2781ms |
| Q02 | SPM-Configuration | answer | ANSWER | good | ANSWER | good | 40ms | 28835ms |
| Q03 | SPM-Process | answer | ANSWER | good | ANSWER | good | 39ms | 11965ms |
| Q04 | SPM-System | answer | ANSWER | good | ANSWER | good | 36ms | 3758ms |
| Q05 | ICS-Workflow | answer | ANSWER | good | ANSWER | good | 43ms | 22026ms |
| Q06 | ICS-Configuration | answer | ANSWER | good | ANSWER | good | 48ms | 28825ms |
| Q07 | ICS-Process | answer | ANSWER | good | ANSWER | good | 42ms | 3947ms |
| Q08 | Cross-Team | answer | ANSWER | good | ANSWER | good | 39ms | 3623ms |
| Q09 | Cross-Team | answer | ANSWER | good | ANSWER | good | 44ms | 2818ms |
| Q10 | ROA-Configuration | answer | ANSWER | good | ANSWER | good | 28ms | 30079ms |
| Q11 | Procedure | answer | ANSWER | good | ANSWER | good | 37ms | 21328ms |
| Q12 | Procedure | answer | ANSWER | good | ANSWER | good | 26ms | 2963ms |
| Q13 | Procedure | answer | ANSWER | good | ANSWER | good | 18ms | 24030ms |
| Q14 | Procedure | answer | ANSWER | good | ANSWER | good | 20ms | 24596ms |
| Q15 | Procedure | answer | ANSWER | good | ANSWER | good | 17ms | 13960ms |
| Q16 | Cross-Document | answer | ANSWER | poor | ANSWER | poor | 20ms | 2090ms |
| Q17 | Cross-Document | answer | ANSWER | good | ANSWER | good | 22ms | 3085ms |
| Q18 | Ambiguous | answer | ANSWER | good | ANSWER | good | 18ms | 2581ms |
| Q19 | Ambiguous | answer | ANSWER | good | ANSWER | good | 19ms | 3245ms |
| Q20 | Outside-KB | abstain | ABSTAIN | abstained_correctly | ABSTAIN | abstained_correctly | 16ms | 15ms |
| Q21 | Outside-KB | abstain | ANSWER | abstained_incorrectly | ANSWER | abstained_incorrectly | 18ms | 1249ms |
| Q22 | Outside-KB | abstain | ANSWER | abstained_incorrectly | ANSWER | abstained_incorrectly | 20ms | 3112ms |
| Q23 | ROA-Configuration | answer | ANSWER | good | ANSWER | good | 17ms | 23470ms |
| Q24 | ROA-Knowledge | answer | ANSWER | good | ANSWER | good | 18ms | 12182ms |
| Q25 | ROA-Workflow | answer | ANSWER | good | ANSWER | good | 18ms | 23080ms |

## Failure Analysis

### Q16: What pricing-related workflows exist across IDeaS?
- **Expected:** answer
- **Got:** poor
- **Extractive answer:** Why the intervention from IDeaS? At Transaction Level I want to roll-up reservations exactly as they exist based on what was actually
sold without double counting. Table 1 – User Reporting Availabilit
- **LLM answer:** I don't have sufficient evidence to answer this question.
- **Evidence count:** 5
- **Confidence:** 0.87

### Q21: How many employees does IDeaS have?
- **Expected:** abstain
- **Got:** abstained_incorrectly
- **Extractive answer:** Ans – Only full-time Employees of IDeaS India are eligible to avail this benefit. Typically, all IDeaS employees work 42.5 hours per week. Following the Law of
the Land, providing genuine and accurate
- **LLM answer:** I don't have sufficient evidence to answer this question.
- **Evidence count:** 5
- **Confidence:** 0.85

### Q22: What is the latest version of Opera PMS?
- **Expected:** abstain
- **Got:** abstained_incorrectly
- **Extractive answer:** Kindly make sure that opera agent version of both source and target client are
upgraded to latest and are same for both clients. OPERA Version number, Oracle connections can be managed differently
by 
- **LLM answer:** I don't have sufficient evidence to answer this question. The provided documents do not contain information about the latest version of Opera PMS.
- **Evidence count:** 5
- **Confidence:** 0.85


## LLM vs Extractive Comparison

| ID | Extractive Answer (truncated) | LLM Answer (truncated) | Improvement? |
|---|---|---|---|
| Q01 | This document describes how to configure the G3 RMS data feed for SFDC integrati... | I don't have sufficient evidence to answer this question. The provided documents... | — |
| Q02 | G3 RMS STR Configuration – Process & Workflow
1. Case Reason: G3 RMS STR Configu... | The G3 RMS STR Configuration process involves several steps and roles, as outlin... | ✅ |
| Q03 | ACCORHG Full Upload Process Applies to all teams managing full upload requests, ... | The ACCORHG Full Upload Process involves submitting full upload requests to the ... | ✅ |
| Q04 | If IDeaS has detected that the system is not up-to-date and that the daily
expor... | I don't have sufficient evidence to answer this question. The term "FOLS" is men... | — |
| Q05 | ### Prerequisites
- G3 Rate Shopping module licensed
- RMS legacy rate data expo... | The Rate Shopping Migration workflow involves several key steps and tasks:

1. *... | ✅ |
| Q06 | This document describes the end-to-end process for G3 Rate Shopping System (RSS)... | Based on the provided evidence, here's what can be inferred about G3 RSS Configu... | ✅ |
| Q07 | Tagged on: agent Agent to Agent G3 Agent to Agent migration
Sneha Nirgude 21/0... | I don't have sufficient evidence to answer this question. The provided documents... | — |
| Q08 | pping Vendor
idnkal 24/02/2023
G3 Procedures, G3 Processes, IDeaS Support, Wh... | I don't have sufficient evidence to answer this question. The provided documents... | — |
| Q09 | Case Reason =                                         G3 Property URL Merge-Spli... | I don't have sufficient evidence to answer this question. The provided documents... | — |
| Q10 | Demand360 needs to be enabled and mapped in G3 RMS for that property. G3 RMS Dem... | Demand360 needs to be enabled and mapped in G3 RMS for that property. G3 RMS Dem... | — |
| Q11 | This process document provides up to date information on Products, positioning,
... | Based on the provided evidence, the steps in the AMS Recoding process are as fol... | ✅ |
| Q12 | Ensure the following information is available before configuration on case discr... | I don't have sufficient evidence to answer this question. The provided documents... | — |
| Q13 | Synthetic History to Standard Switch with AMS Rebuild Activity
4. This document ... | The Synthetic History to Standard Switch process involves transitioning a proper... | ✅ |
| Q14 | This guide explains how to safely handle requests related to duplicate group del... | Duplicate group deletions are handled through a structured process to ensure sys... | ✅ |
| Q15 | AHWS Property Installation Job on Monitoring Dashboard
⚠️ If the job fails at th... | I don't have sufficient evidence to provide a comprehensive Delphi Installation ... | ✅ |
| Q16 | Why the intervention from IDeaS? At Transaction Level I want to roll-up reservat... | I don't have sufficient evidence to answer this question.... | — |
| Q17 | This document will help in identifying the different steps involved in the migra... | I don't have sufficient evidence to answer this question. The provided documents... | — |
| Q18 | How to search which rate shopping file was processed 
last in G3? Once the peer ... | I don't have sufficient evidence to answer this question. The provided documents... | — |
| Q19 | Note – Now we have a CMA query Check Opera Remote Task Stats this will allow us
... | I don't have sufficient evidence to answer this question. The provided documents... | — |
| Q21 | Ans – Only full-time Employees of IDeaS India are eligible to avail this benefit... | I don't have sufficient evidence to answer this question.... | — |
| Q22 | Kindly make sure that opera agent version of both source and target client are
u... | I don't have sufficient evidence to answer this question. The provided documents... | — |
| Q23 | Validation
• Open Group Pricing Evaluation
• Select future dates
• Verify extend... | The KB_Group Pricing Evaluation Window Extensions involve configuring specific p... | ✅ |
| Q24 | We verified the pricing in G3 RMS and cross-checked it against the corresponding... | Based on the provided evidence, the following pricing issues are documented for ... | ✅ |
| Q25 | Price Grid to Daily Continuous Pricing (CP) – Migration Workflow
1. This documen... | Based on the provided evidence, here's how Price Grid to Daily Continuous Pricin... | ✅ |

## Latency Analysis

| Metric | Extractive | LLM |
|---|---|---|
| Average | 28ms | 11986ms |
| Min | 16ms | 15ms |
| Max | 48ms | 30079ms |

## Top 5 Weaknesses

1. **Corpus coverage gap** — Only 16 of 615 documents are real ICS enterprise documents. SANJAYA knows very little about the actual organization.

2. **Abstention on answerable questions** — Some legitimate questions are incorrectly abstained because the extractive confidence is too low for short evidence.

3. **Answer quality on configuration questions** — Configuration details are often lost in chunking; answers are partial rather than specific.

4. **No multi-document reasoning** — SANJAYA cannot synthesize information across multiple documents (e.g., "What teams work on G3?").

5. **LLM latency** — GX10 adds ~3s latency. For interactive use, this needs streaming or caching.
