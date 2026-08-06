"""
Manual end-to-end pipeline runner: transcriber → claim_extractor → questioner.

Usage:
    python run_pipeline.py <audio_file.mp3>

Example:
    python run_pipeline.py data/samples/audio/workplaceincident.mp3
"""

import sys
import pathlib
import json

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.nodes.transcriber import transcribe_audio, AudioTranscriptionError
from src.nodes.claim_extractor import extract_claims, ClaimExtractionError
from src.nodes.questioner import generate_question, QuestionGenerationError


def run(audio_path: str) -> None:
    sep = "─" * 60

    # ── Node 0: Transcribe ────────────────────────────────────────
    print(f"\n{sep}")
    print("NODE 0 — TRANSCRIBER")
    print(sep)
    try:
        transcription = transcribe_audio(audio_path)
    except AudioTranscriptionError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    print(f"Duration  : {transcription.duration_sec:.2f}s")
    print(f"Transcript:\n{transcription.transcript}")

    # ── Node 1: Extract Claims ────────────────────────────────────
    print(f"\n{sep}")
    print("NODE 1 — CLAIM EXTRACTOR")
    print(sep)
    try:
        extraction = extract_claims(transcription.transcript)
    except ClaimExtractionError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    print(f"Extracted {len(extraction.claims)} claim(s):\n")
    for claim in extraction.claims:
        print(f"  [{claim.id}] {claim.statement}")
        print(f"        Weakness: {claim.potential_weakness}\n")

    # ── Node 2: Generate Question (Round 1, empty history) ────────
    print(f"\n{sep}")
    print("NODE 2 — QUESTIONER  (Round 1 — no prior history)")
    print(sep)
    history: list[dict] = []
    try:
        q_result = generate_question(extraction, history)
    except QuestionGenerationError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    print(f"  Question        : {q_result.question}")
    print(f"  Targets claim   : {q_result.targets_claim_id}")

    # Show which claim was targeted
    targeted = next(
        (c for c in extraction.claims if c.id == q_result.targets_claim_id), None
    )
    if targeted:
        print(f"  Claim statement : {targeted.statement}")
        print(f"  Claim weakness  : {targeted.potential_weakness}")

    print(f"\n{sep}")
    print("Pipeline complete.")
    print(sep)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python run_pipeline.py <path/to/audio.mp3>")
        sys.exit(1)
    run(sys.argv[1])
