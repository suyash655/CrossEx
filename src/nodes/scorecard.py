"""Node for generating the final cross-examination scorecard using Groq Llama."""

import json
import os
import pathlib
import re
import sys

# Ensure the project root is on sys.path when this file is run directly.
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from groq import Groq
from dotenv import load_dotenv

from src.schemas import ScorecardResult

load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=True)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are an experienced legal training evaluator reviewing a completed cross-examination.

You will be given the full round-by-round history of the session: each round includes the question asked,
the witness's answer, whether a contradiction was found, and an explanation of the analysis.

Your task is to produce a final structured evaluation with these four fields:

1. consistency_score (integer 1–10):
   Rate how consistent the witness was across ALL rounds.
   10 = perfectly consistent, no contradictions at all.
   1  = severe contradictions in almost every answer.
   Use the contradiction_found flags and explanations to calibrate this.

2. evasiveness_score (integer 1–10):
   Rate how evasive or vague the witness was across ALL rounds.
   10 = highly evasive — repeatedly deflected, gave non-answers, or avoided specifics.
   1  = direct and forthcoming in every answer.
   Look for answers that change the subject, add unsolicited qualifications, or fail to
   address the question asked.

3. contradictions (list of strings):
   List every specific contradiction or significant evasion found across all rounds,
   in plain language. One short sentence per item. If none were found, return an empty list.

4. summary (string):
   3–4 sentences summarising the witness's overall performance.
   End with ONE specific, actionable improvement suggestion for the witness.

Return ONLY a valid JSON object — no markdown, no commentary — matching this exact schema:
{
  "consistency_score": <integer 1–10>,
  "evasiveness_score": <integer 1–10>,
  "contradictions": ["<plain-language description>", ...],
  "summary": "<3–4 sentence narrative with one improvement suggestion>"
}"""

_USER_TEMPLATE = """\
Cross-examination history ({n} round(s)):

{history_json}

Produce the final scorecard JSON."""


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class ScorecardError(Exception):
    """Raised when scorecard generation fails for any known reason."""


# ---------------------------------------------------------------------------
# JSON parsing helper
# ---------------------------------------------------------------------------

def _parse_json_response(raw: str) -> dict:
    """
    Parse a JSON string from Groq, stripping markdown fences on first failure.
    Retries once after stripping before raising ScorecardError.
    """
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    stripped = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    stripped = re.sub(r"\s*```$", "", stripped).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ScorecardError(
            f"Groq returned malformed JSON that could not be parsed even after "
            f"stripping markdown fences.\nRaw response (first 500 chars):\n{raw[:500]}"
        ) from exc


# ---------------------------------------------------------------------------
# Main node function
# ---------------------------------------------------------------------------

def generate_scorecard(history: list[dict]) -> ScorecardResult:
    """
    Generate a final structured performance scorecard from the full
    cross-examination history using Groq Llama (llama-3.3-70b-versatile).

    Evaluates consistency, evasiveness, lists all contradictions found,
    and writes a summary with one specific improvement suggestion.

    Args:
        history: List of round dicts from CrossExamSession.get_history().
                 Each dict should contain: question, targets_claim_id, answer,
                 contradiction_found, explanation.

    Returns:
        ScorecardResult with consistency_score, evasiveness_score,
        contradictions, and summary.

    Raises:
        ScorecardError: If history is empty, the API call fails, the
            response is malformed, or schema validation fails.
    """
    # --- 1. Input validation -------------------------------------------------
    if not history:
        raise ScorecardError(
            "History is empty. Complete at least one round before generating a scorecard."
        )

    # --- 2. Configure Groq client --------------------------------------------
    api_key = os.getenv("GROQ_API_KEY") or os.getenv("GRoQ_API_KEY")
    if not api_key:
        raise ScorecardError(
            "GROQ_API_KEY is not set. "
            "Add it to your .env file or environment variables."
        )
    client = Groq(api_key=api_key)

    # --- 3. Build prompt -----------------------------------------------------
    user_message = _USER_TEMPLATE.format(
        n=len(history),
        history_json=json.dumps(history, indent=2),
    )

    # --- 4. Call Groq --------------------------------------------------------
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,  # slightly higher for narrative quality, still structured
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        raise ScorecardError(
            f"Groq API call failed during scorecard generation: {exc}"
        ) from exc

    # --- 5. Parse response ---------------------------------------------------
    raw = (response.choices[0].message.content or "").strip()
    if not raw:
        raise ScorecardError(
            "Groq returned an empty response during scorecard generation."
        )

    data = _parse_json_response(raw)

    # --- 6. Validate against schema (includes score range validation) --------
    try:
        result = ScorecardResult(**data)
    except Exception as exc:
        raise ScorecardError(
            f"Groq response did not match ScorecardResult schema: {exc}\n"
            f"Parsed data: {data}"
        ) from exc

    return result


# ---------------------------------------------------------------------------
# Manual test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Hardcoded fake history covering 4 rounds with mixed performance
    fake_history = [
        {
            "question": "Can you produce a copy of the Apex vendor agreement to confirm that Section 4 stipulates delivery by August 1st?",
            "targets_claim_id": "c1",
            "answer": "I don't have it on me right now, but I've seen it. Everyone in the team knows about the August 1st deadline.",
            "contradiction_found": False,
            "explanation": "The witness did not produce the document but did not contradict the claim. The answer is evasive — relying on hearsay rather than evidence.",
        },
        {
            "question": "How do you define 'missed' — did Apex deliver anything before August 1st at all?",
            "targets_claim_id": "c2",
            "answer": "Well, they sent a partial shipment in late July, but it wasn't everything. The full order came weeks later.",
            "contradiction_found": True,
            "explanation": "The witness now admits a partial shipment arrived before the deadline, which contradicts the unqualified claim that Apex 'missed the deadline'. The original statement implied total non-delivery.",
        },
        {
            "question": "What specific part of your deployment was delayed, and by how many days?",
            "targets_claim_id": "c3",
            "answer": "The whole deployment was pushed back. I'm not sure of the exact number of days — it was significant.",
            "contradiction_found": False,
            "explanation": "The answer is vague and evasive — no specific component or day count was given — but does not directly contradict the claim.",
        },
        {
            "question": "Has Apex formally responded in writing to your claim for liquidated damages?",
            "targets_claim_id": "c4",
            "answer": "Not in writing, no. But their sales rep told us verbally they wouldn't pay.",
            "contradiction_found": True,
            "explanation": "The witness concedes there is no written refusal, contradicting the implied certainty of their original claim that Apex is 'refusing' to honor the damages — the evidence is only an informal verbal remark.",
        },
    ]

    print("=== SCORECARD GENERATOR ===")
    print(f"Processing {len(fake_history)} rounds of history...\n")

    try:
        result = generate_scorecard(fake_history)
        print(f"Consistency score  : {result.consistency_score}/10")
        print(f"Evasiveness score  : {result.evasiveness_score}/10")
        print(f"\nContradictions ({len(result.contradictions)}):")
        for c in result.contradictions:
            print(f"  - {c}")
        print(f"\nSummary:\n{result.summary}")
    except ScorecardError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
