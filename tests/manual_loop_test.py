"""
Manual 4-round loop test using the workplaceincident transcript as the opening
statement and typed fake answers designed to test the full range of the pipeline:
  - Round 1: evasive (no medical evidence produced)
  - Round 2: partial contradiction (pallets were actually noticed loose earlier)
  - Round 3: clean, direct answer
  - Round 4: flat contradiction (operations weren't halted "immediately")

Run with:
    python -m tests.manual_loop_test
or:
    python tests/manual_loop_test.py
"""

import pathlib
import sys

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.orchestrator import CrossExamSession
from src.nodes.scorecard import generate_scorecard, ScorecardError

SEP = "─" * 70

# ---------------------------------------------------------------------------
# Real transcript from workplaceincident.mp3
# ---------------------------------------------------------------------------
STATEMENT = (
    "Incident Report Memo for HR. At approximately 10:30 a.m. in Warehouse B, "
    "Aisle 4, a stack of unfastened pallets on the top rack shifted and fell "
    "into the main walkway. No injuries, but two safety barriers were crushed. "
    "Operations were halted immediately."
)

# ---------------------------------------------------------------------------
# Fake answers — matched to the questions the pipeline actually generates.
# Designed to test contradiction (R2, R4), evasion (R1, R3), and one
# answer that directly contradicts a specific claimed fact.
# ---------------------------------------------------------------------------
FAKE_ANSWERS = [
    # Round 1 — evasive: ignores the corroboration question, deflects to injuries
    (
        "I walked through Aisle 4 right after it happened and nobody was on the "
        "ground or asking for help. I'm confident no one was hurt."
    ),
    # Round 2 — contradiction: admits pallets were already flagged as unsafe,
    # contradicting the implicit claim that the fall was unforeseeable
    (
        "Look, someone had flagged those pallets as unstable in a walk-through "
        "two days before. It was in the log. We just hadn't gotten to fixing it yet."
    ),
    # Round 3 — direct contradiction: admits operations weren't halted immediately
    (
        "Well, the forklift operator finished his current run before we stopped "
        "things — maybe five or ten minutes after the fall. We didn't want to "
        "leave a load half-placed."
    ),
    # Round 4 — clean, specific answer: confirms damage with named barriers
    (
        "Yes, it was specifically two barriers — both the yellow bollard at the "
        "aisle entrance and the chain guard mid-aisle. Both were completely "
        "flattened by the falling load."
    ),
]


def run() -> None:
    print(f"\n{SEP}")
    print("CROSSEX — FULL 4-ROUND MANUAL LOOP TEST")
    print(f"{SEP}\n")
    print("Opening statement:")
    print(f"  {STATEMENT}\n")

    session = CrossExamSession(max_rounds=4)

    # ── Start: extract claims + first question ────────────────────────────
    print(f"{SEP}")
    print("EXTRACTING CLAIMS + GENERATING ROUND 1 QUESTION...")
    print(SEP)
    q = session.start(STATEMENT)
    print(f"\nClaims extracted: {len(session.claims.claims)}")
    for c in session.claims.claims:
        print(f"  [{c.id}] {c.statement}")
        print(f"         weakness: {c.potential_weakness}")

    # ── 4 rounds ─────────────────────────────────────────────────────────
    current_question = q
    for round_num, answer in enumerate(FAKE_ANSWERS, start=1):
        print(f"\n{SEP}")
        print(f"ROUND {round_num}")
        print(SEP)

        # Show targeted claim context
        targeted = next(
            (c for c in session.claims.claims if c.id == current_question.targets_claim_id),
            None,
        )
        if targeted:
            print(f"\n  Targeting [{targeted.id}]: {targeted.statement}")
            print(f"  Weakness  : {targeted.potential_weakness}")

        print(f"\n  Q: {current_question.question}")
        print(f"\n  A: {answer}")

        result = session.submit_answer(answer)
        cr = result["contradiction_result"]

        flag = "⚠  CONTRADICTION" if cr.contradiction_found else "✓  consistent"
        print(f"\n  {flag}")
        print(f"  {cr.explanation}")

        if result["done"]:
            print(f"\n  [All {session.max_rounds} rounds complete]")
        else:
            current_question = result["next_question"]

    # ── Scorecard ─────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("GENERATING FINAL SCORECARD...")
    print(SEP)
    try:
        scorecard = generate_scorecard(session.get_history())
        print(f"\n  Consistency score  : {scorecard.consistency_score}/10")
        print(f"  Evasiveness score  : {scorecard.evasiveness_score}/10")
        print(f"\n  Contradictions ({len(scorecard.contradictions)}):")
        for item in scorecard.contradictions:
            print(f"    - {item}")
        print(f"\n  Summary:\n  {scorecard.summary}")
    except ScorecardError as e:
        print(f"  [Scorecard failed] {e}", file=sys.stderr)

    print(f"\n{SEP}\n")


if __name__ == "__main__":
    run()
