"""
Real-corpus evaluation questions for cross-team and cross-document reasoning.

These questions are derived from ACTUAL documents in the SANJAYA corpus.
Every question can be answered (or correctly abstained) from the current knowledge base.

Usage:
    python scripts/mission356d_evaluation_questions.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Evaluation Questions ──────────────────────────────────────────────
# Categories:
#   DIRECT    — answer explicitly in one document
#   CROSS_DOC — answer requires combining 2+ documents
#   CROSS_TEAM — answer involves multiple teams
#   ABSTAIN   — answer not in corpus, should abstain
#   ENTITY    — system/team identification
#   PROCEDURE — workflow/procedure questions
#   VERSION   — document versioning questions

EVALUATION_QUESTIONS = [
    # ── Direct factual ──
    {
        "id": "E01",
        "question": "What is G3?",
        "category": "ENTITY",
        "expected_behavior": "answer",
        "key_facts": ["revenue management", "IDeaS", "system"],
        "must_not_contain": ["I don't know", "not available"],
    },
    {
        "id": "E02",
        "question": "What is OHIP used for?",
        "category": "ENTITY",
        "expected_behavior": "answer",
        "key_facts": ["Opera", "integration", "hotel"],
        "must_not_contain": ["I don't know"],
    },
    {
        "id": "E03",
        "question": "What does ICS handle?",
        "category": "CROSS_TEAM",
        "expected_behavior": "answer",
        "key_facts": ["installation", "configuration", "support"],
        "must_not_contain": [],
    },
    {
        "id": "E04",
        "question": "What is the Data Feed Configuration process?",
        "category": "PROCEDURE",
        "expected_behavior": "answer",
        "key_facts": ["G3", "data feed", "configuration"],
        "must_not_contain": [],
    },

    # ── Cross-document / cross-team ──
    {
        "id": "E05",
        "question": "Which teams work with G3?",
        "category": "CROSS_TEAM",
        "expected_behavior": "answer",
        "key_facts": ["SPM", "ICS"],
        "must_not_contain": ["I don't know"],
    },
    {
        "id": "E06",
        "question": "What systems does ICS work with?",
        "category": "CROSS_TEAM",
        "expected_behavior": "answer",
        "key_facts": ["G3", "Opera", "OHIP"],
        "must_not_contain": [],
    },
    {
        "id": "E07",
        "question": "How does the G3 installation process work?",
        "category": "PROCEDURE",
        "expected_behavior": "answer",
        "key_facts": ["installation", "steps", "configuration"],
        "must_not_contain": [],
    },
    {
        "id": "E08",
        "question": "What is the relationship between RMS and G3?",
        "category": "CROSS_DOC",
        "expected_behavior": "answer",
        "key_facts": ["RMS", "G3", "revenue management"],
        "must_not_contain": [],
    },

    # ── Abstention (out of scope) ──
    {
        "id": "E09",
        "question": "How many employees does IDeaS have?",
        "category": "ABSTAIN",
        "expected_behavior": "abstain",
        "key_facts": [],
        "must_contain_abstain_signal": True,
    },
    {
        "id": "E10",
        "question": "What is the company annual revenue?",
        "category": "ABSTAIN",
        "expected_behavior": "abstain",
        "key_facts": [],
        "must_contain_abstain_signal": True,
    },
    {
        "id": "E11",
        "question": "What programming language is G3 written in?",
        "category": "ABSTAIN",
        "expected_behavior": "abstain",
        "key_facts": [],
        "must_contain_abstain_signal": True,
    },
    {
        "id": "E12",
        "question": "What is the current stock price of SAS?",
        "category": "ABSTAIN",
        "expected_behavior": "abstain",
        "key_facts": [],
        "must_contain_abstain_signal": True,
    },

    # ── More entity/system questions ──
    {
        "id": "E13",
        "question": "What is SFDC used for in this organization?",
        "category": "ENTITY",
        "expected_behavior": "answer",
        "key_facts": ["Salesforce", "CRM", "customer"],
        "must_not_contain": [],
    },
    {
        "id": "E14",
        "question": "What is the role of SPM team?",
        "category": "CROSS_TEAM",
        "expected_behavior": "answer",
        "key_facts": ["SPM", "support", "process"],
        "must_not_contain": [],
    },
    {
        "id": "E15",
        "question": "How does the troubleshooting process work for rate shopping?",
        "category": "PROCEDURE",
        "expected_behavior": "answer",
        "key_facts": ["troubleshooting", "rate", "shopping"],
        "must_not_contain": [],
    },
    {
        "id": "E16",
        "question": "What are the G3 restriction levels?",
        "category": "PROCEDURE",
        "expected_behavior": "answer",
        "key_facts": ["restriction", "level", "G3"],
        "must_not_contain": [],
    },
    {
        "id": "E17",
        "question": "What is the OXI to Agent Migration?",
        "category": "PROCEDURE",
        "expected_behavior": "answer",
        "key_facts": ["OXI", "Agent", "migration"],
        "must_not_contain": [],
    },
    {
        "id": "E18",
        "question": "What is the Marriott data capture process?",
        "category": "PROCEDURE",
        "expected_behavior": "answer",
        "key_facts": ["Marriott", "data capture", "configuration"],
        "must_not_contain": [],
    },

    # ── More abstention ──
    {
        "id": "E19",
        "question": "What is the CEO's name?",
        "category": "ABSTAIN",
        "expected_behavior": "abstain",
        "key_facts": [],
        "must_contain_abstain_signal": True,
    },
    {
        "id": "E20",
        "question": "What are the office locations?",
        "category": "ABSTAIN",
        "expected_behavior": "abstain",
        "key_facts": [],
        "must_contain_abstain_signal": True,
    },

    # ── Cross-document synthesis ──
    {
        "id": "E21",
        "question": "What documents describe G3 Data Feed specifications?",
        "category": "CROSS_DOC",
        "expected_behavior": "answer",
        "key_facts": ["G3", "Data Feed", "specification"],
        "must_not_contain": [],
    },
    {
        "id": "E22",
        "question": "What are the TARS error codes?",
        "category": "PROCEDURE",
        "expected_behavior": "answer",
        "key_facts": ["TARS", "error", "resolution"],
        "must_not_contain": [],
    },
    {
        "id": "E23",
        "question": "What is the GRO monitoring process?",
        "category": "PROCEDURE",
        "expected_behavior": "answer",
        "key_facts": ["GRO", "monitoring", "process"],
        "must_not_contain": [],
    },
    {
        "id": "E24",
        "question": "What is the Opera to SkyTouch migration?",
        "category": "PROCEDURE",
        "expected_behavior": "answer",
        "key_facts": ["Opera", "SkyTouch", "migration"],
        "must_not_contain": [],
    },
    {
        "id": "E25",
        "question": "What SAS DB tables are used for configuration?",
        "category": "ENTITY",
        "expected_behavior": "answer",
        "key_facts": ["SAS", "DB", "table", "configuration"],
        "must_not_contain": [],
    },

    # ── Additional abstention tests ──
    {
        "id": "E26",
        "question": "What is the pricing model for G3?",
        "category": "ABSTAIN",
        "expected_behavior": "abstain",
        "key_facts": [],
        "must_contain_abstain_signal": True,
    },
    {
        "id": "E27",
        "question": "How many hotels use G3 worldwide?",
        "category": "ABSTAIN",
        "expected_behavior": "abstain",
        "key_facts": [],
        "must_contain_abstain_signal": True,
    },

    # ── Entity/team queries ──
    {
        "id": "E28",
        "question": "What is SDOPS responsible for?",
        "category": "CROSS_TEAM",
        "expected_behavior": "answer",
        "key_facts": ["SDOPS", "support", "operations"],
        "must_not_contain": [],
    },
    {
        "id": "E29",
        "question": "What is ROA in the context of IDeaS?",
        "category": "ENTITY",
        "expected_behavior": "answer",
        "key_facts": ["ROA", "IDeaS"],
        "must_not_contain": [],
    },
    {
        "id": "E30",
        "question": "What is the HTNG protocol?",
        "category": "ENTITY",
        "expected_behavior": "answer",
        "key_facts": ["HTNG", "protocol", "hotel"],
        "must_not_contain": [],
    },
]


def run_evaluation():
    """Run the evaluation against the live SANJAYA API."""
    import requests

    BASE = "http://localhost:8000"
    results = []

    print(f"=== SANJAYA Real-Corpus Evaluation ({len(EVALUATION_QUESTIONS)} questions) ===\n")

    for q in EVALUATION_QUESTIONS:
        try:
            resp = requests.post(
                f"{BASE}/api/ask",
                json={"query": q["question"], "top_k": 5},
                timeout=120,
            )
            if resp.status_code != 200:
                print(f"  {q['id']}: ERROR {resp.status_code}")
                results.append({"id": q["id"], "status": "error", "code": resp.status_code})
                continue

            data = resp.json()
            answer = data.get("answer", "")
            abstained = data.get("abstained", False)
            confidence = data.get("confidence", 0)
            verdict = data.get("verification_verdict", "")

            # Check behavior
            correct = False
            if q["expected_behavior"] == "abstain":
                correct = abstained or confidence < 0.15
            else:
                correct = not abstained and confidence > 0
                # Check key facts
                if correct and q.get("key_facts"):
                    answer_lower = answer.lower()
                    found = sum(1 for f in q["key_facts"] if f.lower() in answer_lower)
                    if found == 0:
                        correct = False

            status = "PASS" if correct else "FAIL"
            conf_str = f"{confidence*100:.0f}%"
            print(f"  {q['id']}: {status} ({conf_str}, {verdict}) - {q['question'][:60]}")

            results.append({
                "id": q["id"],
                "status": status,
                "question": q["question"],
                "category": q["category"],
                "confidence": confidence,
                "abstained": abstained,
                "verdict": verdict,
                "answer_preview": answer[:200] if answer else "",
            })

        except Exception as e:
            print(f"  {q['id']}: EXCEPTION {e}")
            results.append({"id": q["id"], "status": "error", "error": str(e)})

    # Summary
    passed = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)
    print(f"\n=== RESULTS: {passed}/{total} ({passed/total*100:.0f}%) ===")

    by_cat = {}
    for r in results:
        cat = r.get("category", "unknown")
        by_cat.setdefault(cat, []).append(r)
    for cat, cat_results in sorted(by_cat.items()):
        cat_pass = sum(1 for r in cat_results if r["status"] == "PASS")
        print(f"  {cat}: {cat_pass}/{len(cat_results)}")

    # Save results
    out_path = Path("docs") / "evaluation_results.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out_path}")

    return results


if __name__ == "__main__":
    run_evaluation()
