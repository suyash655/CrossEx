"""Node for checking whether a witness's answer contradicts their original claims."""

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

from src.schemas import Claim, ClaimExtractionResult, ContradictionCheckResult, QuestionResult

load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=True)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a meticulous legal analyst reviewing a cross-examination exchange.

You will be given:
- The original list of factual claims made by the witness, each with a potential weakness.
- The question that was just asked (and which claim it targeted).
- The witness's answer to that question.

Your tasks:
1. Determine whether the answer CONTRADICTS, WEAKENS, or is EVASIVE about the targeted claim,
   OR reveals a NEW inconsistency with any other claim in the list.
   - "contradiction_found" should be true if any of these apply.
2. Write a clear, plain-language explanation of your reasoning (2-4 sentences).
   If no contradiction was found, explain why the answer was consistent.
3. Return an updated_claims list — same claims with the same IDs — but refresh the
   "potential_weakness" field for the targeted claim to reflect what was just revealed.
   Leave all other claims unchanged.

Return ONLY a valid JSON object — no markdown, no commentary — matching this exact schema:
{
  "contradiction_found": true or false,
  "explanation": "<plain-language reasoning>",
  "updated_claims": [
    {
      "id": "<same id>",
      "statement": "<same statement>",
      "potential_weakness": "<updated or unchanged weakness>"
    }
  ]
}"""

_USER_TEMPLATE = """\
Original claims:
{claims_json}

Question asked (targets claim {targeted_id}):
{question}

Witness's answer:
{answer}

Analyse the answer and return the JSON result."""


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class ContradictionCheckError(Exception):
    """Raised when contradiction checking fails for any known reason."""


# ---------------------------------------------------------------------------
# JSON parsing helper
# ---------------------------------------------------------------------------

def _parse_json_response(raw: str) -> dict:
    """
    Parse a JSON string from Groq, stripping markdown fences on first failure.
    Retries once after stripping before raising ContradictionCheckError.
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
        raise ContradictionCheckError(
            f"Groq returned malformed JSON that could not be parsed even after "
            f"stripping markdown fences.\nRaw response (first 500 chars):\n{raw[:500]}"
        ) from exc


# ---------------------------------------------------------------------------
# Main node function
# ---------------------------------------------------------------------------

def check_answer(
    claims: ClaimExtractionResult,
    question: QuestionResult,
    answer_transcript: str,
) -> ContradictionCheckResult:
    """
    Check whether the witness's answer to a cross-examination question
    contradicts or weakens any of their original claims.

    Also returns an updated claims list with the targeted claim's
    potential_weakness refreshed to reflect what was just revealed.

    Args:
        claims:            Current ClaimExtractionResult (may have been updated
                           by a previous round).
        question:          The QuestionResult that was just asked, including
                           which claim it targeted.
        answer_transcript: Plain-text transcript of the witness's spoken answer.

    Returns:
        ContradictionCheckResult with contradiction_found, explanation, and
        updated_claims.

    Raises:
        ContradictionCheckError: If the answer is empty, the API call fails,
            the response is malformed, or schema validation fails.
    """
    # --- 1. Input validation -------------------------------------------------
    if not answer_transcript or not answer_transcript.strip():
        raise ContradictionCheckError(
            "Answer transcript is empty. Provide a non-empty answer."
        )

    # --- 2. Configure Groq client --------------------------------------------
    api_key = os.getenv("GROQ_API_KEY") or os.getenv("GRoQ_API_KEY")
    if not api_key:
        raise ContradictionCheckError(
            "GROQ_API_KEY is not set. "
            "Add it to your .env file or environment variables."
        )
    client = Groq(api_key=api_key)

    # --- 3. Build prompt payload ---------------------------------------------
    claims_payload = [c.model_dump() for c in claims.claims]

    user_message = _USER_TEMPLATE.format(
        claims_json=json.dumps(claims_payload, indent=2),
        targeted_id=question.targets_claim_id,
        question=question.question,
        answer=answer_transcript.strip(),
    )

    # --- 4. Call Groq --------------------------------------------------------
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,  # low — we want precise, consistent legal reasoning
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        raise ContradictionCheckError(
            f"Groq API call failed during contradiction check: {exc}"
        ) from exc

    # --- 5. Parse response ---------------------------------------------------
    raw = (response.choices[0].message.content or "").strip()
    if not raw:
        raise ContradictionCheckError(
            "Groq returned an empty response during contradiction check."
        )

    data = _parse_json_response(raw)

    # --- 6. Validate against schema ------------------------------------------
    try:
        result = ContradictionCheckResult(**data)
    except Exception as exc:
        raise ContradictionCheckError(
            f"Groq response did not match ContradictionCheckResult schema: {exc}\n"
            f"Parsed data: {data}"
        ) from exc

    # --- 7. Sanity-check: updated_claims must preserve all original IDs ------
    original_ids = {c.id for c in claims.claims}
    returned_ids = {c.id for c in result.updated_claims}
    if original_ids != returned_ids:
        raise ContradictionCheckError(
            f"updated_claims IDs {sorted(returned_ids)} do not match "
            f"original claim IDs {sorted(original_ids)}. "
            "The model may have added or dropped claims."
        )

    return result


# ---------------------------------------------------------------------------
# Manual test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from src.schemas import Claim

    # Hardcoded example: contract dispute scenario
    example_claims = ClaimExtractionResult(
        claims=[
            Claim(
                id="c1",
                statement="Section 4 of the Apex vendor agreement stipulates delivery by August 1st.",
                potential_weakness="Lack of corroboration — the actual agreement document is not provided.",
            ),
            Claim(
                id="c2",
                statement="Apex missed the delivery deadline of August 1st.",
                potential_weakness="Relies on subjective interpretation; 'missed' is disputed.",
            ),
            Claim(
                id="c3",
                statement="The late shipment from Apex has delayed our deployment phase.",
                potential_weakness="Missing causal link — other factors could have caused the delay.",
            ),
            Claim(
                id="c4",
                statement="Apex is refusing to honor the 15% liquidated damages.",
                potential_weakness="No direct evidence from Apex confirming their refusal.",
            ),
        ]
    )

    example_question = QuestionResult(
        question="Can you produce a copy of the Apex vendor agreement to confirm that Section 4 stipulates delivery by August 1st?",
        targets_claim_id="c1",
    )

    # Evasive answer that doesn't produce the document
    example_answer = (
        "I don't have it on me right now, but I've seen it. "
        "Everyone in the team knows about the August 1st deadline."
    )

    print("=== CONTRADICTION CHECKER ===\n")
    print(f"Question : {example_question.question}")
    print(f"Answer   : {example_answer}\n")

    try:
        result = check_answer(example_claims, example_question, example_answer)
        print(f"Contradiction found : {result.contradiction_found}")
        print(f"Explanation         : {result.explanation}\n")
        print("Updated claims:")
        for c in result.updated_claims:
            print(f"  [{c.id}] weakness: {c.potential_weakness}")
    except ContradictionCheckError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
