# Mission 3.56B — Claim-Level Evidence Verification UI

## Summary

Exposed the existing Mission 3.53 EvidenceClaimVerifier results in the SANJAYA UI,
allowing users to see which claims in an answer are DIRECT, INFERRED, or UNSUPPORTED.

## What Changed

### Backend (`command_center/backend/routers/chat.py`)
- Added `ClaimVerificationResponse` Pydantic model with: `claim_text`, `classification`,
  `supporting_documents`, `evidence_type`, `reasoning`
- Extended `AskResponse` with: `verification_verdict`, `direct_claims`, `inferred_claims`,
  `unsupported_claims`, `claim_verifications[]`
- Wired `AgenticResult.claim_verification` through the `/api/ask` response

### Frontend (`command_center/frontend/index.html`)
- Added "📋 Claim Verification" panel below the answer bubble
- Each claim rendered with color-coded border:
  - 🟢 DIRECT (green) — explicitly supported by document text
  - 🟡 INFERRED (yellow) — derived from relationships/metadata
  - 🔴 UNSUPPORTED (red) — not supported by evidence
- Shows claim counts: "9 direct, 1 inferred, 3 unsupported"
- Verdict badge: PASS (green) / PARTIAL (yellow) / FAIL (red)

### Tests (`tests/test_claim_level_ui.py`)
- 8 deterministic tests verifying:
  - Verification fields present in response
  - Claim classifications are valid
  - Counts consistent with claims list
  - Abstained answers have empty claims
  - No secrets/tokens leaked through claims
  - No unauthorized evidence in claims
  - Direct claims have supporting documents
  - Inferred classification works

## Real Response Example

```json
{
  "verification_verdict": "PARTIAL",
  "direct_claims": 9,
  "inferred_claims": 1,
  "unsupported_claims": 3,
  "claim_verifications": [
    {
      "claim_text": "Based on the provided evidence, the G3 Data Feed Configuration...",
      "classification": "UNSUPPORTED"
    },
    {
      "claim_text": "The configuration is for RMS to SFDC data flow.",
      "classification": "DIRECT"
    },
    {
      "claim_text": "G3 is associated with SPM team activities.",
      "classification": "INFERRED"
    }
  ]
}
```

## Test Results

| Group | Result |
|-------|--------|
| Claim-level UI (8 tests) | **8/8 pass** |
| Sufficiency Gate (31 tests) | **31/31 pass** |
| Evidence Claim Verification (23 tests) | **23/23 pass** |
| Fabric Wiring (8 tests) | **8/8 pass** |
| LAN/UI (15 tests) | **15/15 pass** |
| Knowledge Explorer (12 tests) | **12/12 pass** |
| Frontend Serving (12 tests) | **12/12 pass** |
| Access/Security (92 tests) | **92 pass, 1 skip** |
| Knowledge Loop (20 tests) | **20/20 pass** |
| Closed Loop Learning (22 tests) | **22/22 pass** |
| **TOTAL** | **243 pass, 1 skip** |

## Files Changed

| File | Change |
|------|--------|
| `command_center/backend/routers/chat.py` | Added `ClaimVerificationResponse` model, wired verification data |
| `command_center/frontend/index.html` | Added claim-level verification panel |
| `tests/test_claim_level_ui.py` | **NEW** — 8 tests |

## Not Committed

Awaiting approval.
