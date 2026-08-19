"""
============================================================
KURUKSHETRA v2.1
SANJAYA Agent + Tool Executors
============================================================
"""

# ==========================================================
# Imports
# ==========================================================

from kurukshetra.agent import SANJAYAPlanner, Tool
from kurukshetra.executors import KnowledgeExecutor


# ==========================================================
# Engine Initialization
# ==========================================================

def build_engine():

    print("Loading KURUKSHETRA Knowledge Base...\n")

    return (
        SANJAYAPlanner(),
        KnowledgeExecutor(),
    )


# ==========================================================
# Confidence Label
# ==========================================================

def confidence(score: float) -> str:

    if score >= 0.08:
        return "HIGH"

    if score >= 0.03:
        return "MEDIUM"

    return "LOW"


# ==========================================================
# Main Chat Loop
# ==========================================================

def main():

    planner, knowledge = build_engine()

    print("=" * 60)
    print("KURUKSHETRA v2.1 - SANJAYA Agent")
    print("Planner + Tool Executors")
    print("Type 'exit' to quit")
    print("=" * 60)

    while True:

        # --------------------------------------------------
        # User Input
        # --------------------------------------------------

        question = input("\nYou: ").strip()

        if question.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break

        # --------------------------------------------------
        # SANJAYA Planning
        # --------------------------------------------------

        plan = planner.create_plan(question)

        print("\nSANJAYA Planner")
        print(f"Intent     : {plan.intent}")
        print(f"Tool       : {plan.tool.value}")
        print(f"Confidence : {plan.confidence:.2f}")
        print(f"Reason     : {plan.reason}")

        # --------------------------------------------------
        # KNOWLEDGE EXECUTOR
        # --------------------------------------------------

        if plan.tool == Tool.KNOWLEDGE:

            result = knowledge.execute(question)

            if not result["success"]:
                print("\nKURUKSHETRA:", result["message"])
                continue

            print("\nKURUKSHETRA Answer")
            print(f"Source     : {result['source']}")
            print(f"Document   : {result['document_id']}")
            print(f"Chunk      : {result['chunk_id']}")
            print(
                f"Confidence : {confidence(result['score'])} ({result['score']:.3f})"
            )

            print("-" * 60)
            print(result["text"][:1500])
            print("-" * 60)

        # --------------------------------------------------
        # SQL EXECUTOR
        # --------------------------------------------------

        elif plan.tool == Tool.SQL:

            print("\nSQL EXECUTOR")
            print("-" * 60)
            print("Status : Placeholder")
            print("Next milestone:")
            print("• Property lookup")
            print("• Client mapping")
            print("• Order information")
            print("-" * 60)

        # --------------------------------------------------
        # DATADOG EXECUTOR
        # --------------------------------------------------

        elif plan.tool == Tool.DATADOG:

            print("\nDATADOG EXECUTOR")
            print("-" * 60)
            print("Status : Placeholder")
            print("Next milestone:")
            print("• Correlation ID detection")
            print("• Log investigation")
            print("• Failure stage identification")
            print("• Recovery recommendation")
            print("-" * 60)

        # --------------------------------------------------
        # SMARTSHEET EXECUTOR
        # --------------------------------------------------

        elif plan.tool == Tool.SMARTSHEET:

            print("\nSMARTSHEET EXECUTOR")
            print("-" * 60)
            print("Status : Placeholder")
            print("Next milestone:")
            print("• Update current state")
            print("• Assign reviewer")
            print("• Modify review status")
            print("-" * 60)

        else:

            print("\nNo suitable executor found.")


# ==========================================================
# Entry Point
# ==========================================================

if __name__ == "__main__":
    main()