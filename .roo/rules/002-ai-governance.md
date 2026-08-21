# KURUKSHETRA AI Governance

## Principle

Repository knowledge is authoritative.

The LLM is a reasoning engine, not the source of truth.

---

## Ownership

Allowed owners:

- Service Delivery
- SDOPS
- Support
- Operations
- Revenue
- QA
- Shared Systems
- UNKNOWN

Never invent ownership.

---

## Visibility

Allowed values:

- Public
- Internal
- Confidential
- Restricted

Never expose Restricted information in examples.

---

## Trust Evaluation

Every answer should internally evaluate:

- Source reliability
- Document freshness
- Evidence availability
- Confidence score

If evidence is weak, clearly state uncertainty.

Never fabricate operational procedures.

---

## Auditability

Architecture decisions must be explainable.

Business terminology must be traceable to repository evidence.

Unknown business terms must remain UNKNOWN until confirmed by the user.