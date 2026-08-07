"""Node for extracting claims from transcribed text using Gemini 2.0 Flash."""

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

from src.schemas import ClaimExtractionResult

load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=True)

from src.domains import DOMAINS

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TEMPLATE = """{persona_prompt}

Your task is to read the provided statement and decompose it into every distinct factual claim it contains.

For each claim you must:
1. Assign a short unique id (e.g. "c1", "c2", ...).
2. State the claim as a single clear, self-contained sentence (field: "statement").
3. Identify the most significant weakness or ambiguity in that claim — for example:
   - Vague or unverifiable timing ("around noon", "a few days later")
   - Lack of corroboration (no witnesses, no documentation)
   - Internal inconsistency or contradiction with common sense
   - Reliance on subjective perception or memory
   - Missing causal link between events
   (field: "potential_weakness")

Return ONLY a valid JSON object — no markdown, no commentary — matching this exact schema:
{{
  "claims": [
    {{
      "id": "c1",
      "statement": "<the factual claim>",
      "potential_weakness": "<the weakness or ambiguity>"
    }}
  ]
}}"""

_USER_TEMPLATE = "Statement:\n\n{statement}"


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class ClaimExtractionError(Exception):
    """Raised when claim extraction fails for any known reason."""


# ---------------------------------------------------------------------------
# JSON parsing helper
# ---------------------------------------------------------------------------

def _parse_json_response(raw: str) -> dict:
    """
    Attempt to parse a JSON string returned by Gemini.

    If the first parse fails (e.g. the model wrapped output in markdown
    code fences), strip the fences and retry once before raising.
    """
    raw = raw.strip()

    # First attempt — parse as-is
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Second attempt — strip markdown code fences (```json ... ``` or ``` ... ```)
    stripped = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    stripped = re.sub(r"\s*```$", "", stripped).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ClaimExtractionError(
            f"Gemini returned malformed JSON that could not be parsed even after "
            f"stripping markdown fences.\nRaw response (first 500 chars):\n{raw[:500]}"
        ) from exc


# ---------------------------------------------------------------------------
# Main node function
# ---------------------------------------------------------------------------

def extract_claims(statement: str, domain: str = "legal") -> ClaimExtractionResult:
    """
    Extract distinct factual claims from a statement using Groq Llama,
    with the adversarial persona shaped by the specified domain.

    Each claim is returned with a unique id, a clear statement, and an
    identified potential weakness or ambiguity for the questioner to target.

    Args:
        statement: Plain-text statement (e.g. from TranscriptionResult).
        domain:    Domain key from DOMAINS (default: "legal"). Controls the
                   persona and framing used during extraction.

    Returns:
        ClaimExtractionResult containing a list of Claim objects and the domain.

    Raises:
        ClaimExtractionError: If the statement is empty, domain is unknown,
            the API call fails, the response is malformed JSON, or validation fails.
    """
    # --- 1. Input validation -------------------------------------------------
    if not statement or not statement.strip():
        raise ClaimExtractionError(
            "Statement is empty. Provide a non-empty statement."
        )
    if domain not in DOMAINS:
        raise ClaimExtractionError(
            f"Unknown domain '{domain}'. Valid domains: {', '.join(DOMAINS)}."
        )

    # --- 2. Build domain-aware system prompt ---------------------------------
    persona = DOMAINS[domain]["persona_prompt"]
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(persona_prompt=persona)

    # --- 3. Configure Groq client -------------------------------------------
    api_key = os.getenv("GROQ_API_KEY") or os.getenv("GRoQ_API_KEY")
    if not api_key:
        raise ClaimExtractionError(
            "GROQ_API_KEY is not set. "
            "Add it to your .env file or environment variables."
        )
    client = Groq(api_key=api_key)

    # --- 4. Call Groq --------------------------------------------------------
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": _USER_TEMPLATE.format(statement=statement.strip())},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        raise ClaimExtractionError(
            f"Groq API call failed during claim extraction: {exc}"
        ) from exc

    raw = (response.choices[0].message.content or "").strip()
    if not raw:
        raise ClaimExtractionError(
            "Groq returned an empty response. "
            "The statement may be too short or contain no extractable claims."
        )

    data = _parse_json_response(raw)

    # --- 5. Inject domain and validate against schema ------------------------
    data["domain"] = domain
    try:
        result = ClaimExtractionResult(**data)
    except Exception as exc:
        raise ClaimExtractionError(
            f"Groq response did not match the expected schema: {exc}\n"
            f"Parsed data: {data}"
        ) from exc

    return result


# ---------------------------------------------------------------------------
# Manual test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Allow piping a statement via stdin or passing as a quoted argument
        if not sys.stdin.isatty():
            user_statement = sys.stdin.read()
        else:
            print(
                "Usage:\n"
                "  python -m src.nodes.claim_extractor \"<witness statement>\"\n"
                "  echo \"<statement>\" | python -m src.nodes.claim_extractor"
            )
            sys.exit(1)
    else:
        user_statement = " ".join(sys.argv[1:])

    try:
        result = extract_claims(user_statement)
        print(f"Extracted {len(result.claims)} claim(s):\n")
        for claim in result.claims:
            print(f"[{claim.id}] {claim.statement}")
            print(f"     Weakness: {claim.potential_weakness}\n")
    except ClaimExtractionError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
