"""Node for generating adversarial cross-examination questions using Gemini 2.0 Flash."""

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

from src.schemas import Claim, ClaimExtractionResult, QuestionResult

load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=True)

from src.domains import DOMAINS

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TEMPLATE = """{persona_prompt}

You have been given a list of factual claims, each annotated with its potential weakness.
You also have the full history of questions already asked and the answers given.

Your task:
1. From the UNTARGETED claims, select the ONE whose weakness is most damaging to the
   respondent's credibility if exposed. Prefer weaknesses involving:
   - Missing corroboration or documentation (hardest to defend)
   - Causal links that could be disputed
   - Facts that contradict common knowledge or procedure
   Over weaknesses that are merely vague timing or imprecise language (softer targets).
2. Formulate ONE single, direct, natural-sounding spoken question that probes that weakness.
   The question must be sharp, concise, and specific — consistent with the persona above.
   Do NOT ask about definitions or margins of error unless a timing claim directly contradicts
   something else. Do NOT say "I would ask..." or add meta-commentary. Just the question itself.
3. Return ONLY a valid JSON object — no markdown, no commentary — matching this exact schema:
{{
  "question": "<the spoken question>",
  "targets_claim_id": "<id of the claim being targeted>"
}}"""

_USER_TEMPLATE = """\
Claims:
{claims_json}

History of questions and answers so far:
{history_json}

Now generate the next cross-examination question."""


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class QuestionGenerationError(Exception):
    """Raised when question generation fails for any known reason."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _already_targeted_ids(history: list[dict]) -> set[str]:
    """Return the set of claim IDs that have already been targeted in history."""
    return {
        entry["targets_claim_id"]
        for entry in history
        if isinstance(entry, dict) and "targets_claim_id" in entry
    }


def _select_target_claim(claims: list[Claim], already_targeted: set[str]) -> Claim | None:
    """
    Return the best untargeted claim to probe next, or None if all are done.

    'Best' is defined as the first untargeted claim in list order — the model
    is instructed to make the final exploitability judgement, but we surface
    the full untargeted set so it has context.
    """
    return next(
        (c for c in claims if c.id not in already_targeted),
        None,
    )


def _parse_json_response(raw: str, error_class: type) -> dict:
    """
    Parse a JSON string from Gemini, stripping markdown fences on first failure.

    Args:
        raw: Raw text from Gemini.
        error_class: Exception class to raise on unrecoverable parse failure.
    """
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strip ```json ... ``` or ``` ... ``` fences and retry once
    stripped = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    stripped = re.sub(r"\s*```$", "", stripped).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise error_class(
            f"Gemini returned malformed JSON that could not be parsed even after "
            f"stripping markdown fences.\nRaw response (first 500 chars):\n{raw[:500]}"
        ) from exc


# ---------------------------------------------------------------------------
# Main node function
# ---------------------------------------------------------------------------

def generate_question(
    claims: ClaimExtractionResult,
    history: list[dict],
    domain: str = "legal",
) -> QuestionResult:
    """
    Generate the next adversarial question targeting the most exploitable
    untested claim, with tone shaped by the specified domain persona.

    Args:
        claims:  ClaimExtractionResult from Node 1 (the full claims list).
        history: List of dicts with keys "question", "answer", and optionally
                 "targets_claim_id" from previous rounds.
        domain:  Domain key from DOMAINS (default: "legal"). Controls the
                 adversarial persona and question style.

    Returns:
        QuestionResult with the next question and the claim ID it targets.

    Raises:
        QuestionGenerationError: If all claims are targeted, domain unknown,
            the API call fails, response is malformed, or validation fails.
    """
    # --- 1. Check there are untargeted claims remaining ----------------------
    already_targeted = _already_targeted_ids(history)
    next_target = _select_target_claim(claims.claims, already_targeted)

    if next_target is None:
        raise QuestionGenerationError(
            f"All {len(claims.claims)} claim(s) have already been targeted. "
            "No new question can be generated."
        )

    if domain not in DOMAINS:
        raise QuestionGenerationError(
            f"Unknown domain '{domain}'. Valid domains: {', '.join(DOMAINS)}."
        )

    # --- 2. Build domain-aware system prompt ---------------------------------
    persona = DOMAINS[domain]["persona_prompt"]
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(persona_prompt=persona)

    # --- 3. Configure Groq client --------------------------------------------
    api_key = os.getenv("GROQ_API_KEY") or os.getenv("GRoQ_API_KEY")
    if not api_key:
        raise QuestionGenerationError(
            "GROQ_API_KEY is not set. "
            "Add it to your .env file or environment variables."
        )
    client = Groq(api_key=api_key)

    # --- 3. Build context payload --------------------------------------------
    # Separate untargeted claims (candidates) from already-targeted ones so
    # the model clearly sees what is still available.
    untargeted = [c for c in claims.claims if c.id not in already_targeted]
    targeted   = [c for c in claims.claims if c.id in already_targeted]

    claims_payload = {
        "untargeted_claims": [c.model_dump() for c in untargeted],
        "already_targeted_claims": [c.model_dump() for c in targeted],
    }

    history_payload = history if history else []

    user_message = _USER_TEMPLATE.format(
        claims_json=json.dumps(claims_payload, indent=2),
        history_json=json.dumps(history_payload, indent=2),
    )

    # --- 4. Call Groq --------------------------------------------------------
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.4,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        raise QuestionGenerationError(
            f"Groq API call failed during question generation: {exc}"
        ) from exc

    # --- 5. Parse response ---------------------------------------------------
    raw = (response.choices[0].message.content or "").strip()
    if not raw:
        raise QuestionGenerationError(
            "Gemini returned an empty response during question generation."
        )

    data = _parse_json_response(raw, QuestionGenerationError)

    # --- 6. Validate against schema ------------------------------------------
    try:
        result = QuestionResult(**data)
    except Exception as exc:
        raise QuestionGenerationError(
            f"Gemini response did not match QuestionResult schema: {exc}\n"
            f"Parsed data: {data}"
        ) from exc

    # --- 7. Sanity-check: returned claim ID must exist in our list -----------
    valid_ids = {c.id for c in claims.claims}
    if result.targets_claim_id not in valid_ids:
        raise QuestionGenerationError(
            f"Gemini returned targets_claim_id='{result.targets_claim_id}' which "
            f"does not match any known claim ID: {sorted(valid_ids)}."
        )

    return result


# ---------------------------------------------------------------------------
# Manual test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Hardcoded example for quick smoke-testing without needing audio input
    example_claims = ClaimExtractionResult(
        claims=[
            Claim(
                id="c1",
                statement="I was at home alone all evening on the night of March 3rd.",
                potential_weakness="No corroborating witness; relies entirely on self-report.",
            ),
            Claim(
                id="c2",
                statement="I received a phone call from my manager at around 9 PM.",
                potential_weakness="Vague timing ('around 9 PM'); phone records could contradict.",
            ),
            Claim(
                id="c3",
                statement="The contract was signed by both parties before the deadline.",
                potential_weakness=(
                    "No specific date given; 'before the deadline' is unverifiable "
                    "without documentary evidence."
                ),
            ),
        ]
    )

    # Simulate one round of history already done (c2 was targeted)
    example_history: list[dict] = [
        {
            "question": "You mentioned a call at around 9 PM — can you give an exact time?",
            "answer": "Well, it was somewhere between 9 and 9:30, I think.",
            "targets_claim_id": "c2",
        }
    ]

    print("Claims:")
    for c in example_claims.claims:
        print(f"  [{c.id}] {c.statement}")
    print(f"\nHistory: {len(example_history)} round(s) already asked.")
    print("\nGenerating next question...\n")

    try:
        result = generate_question(example_claims, example_history)
        print(f"Question  : {result.question}")
        print(f"Targets   : {result.targets_claim_id}")
    except QuestionGenerationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
