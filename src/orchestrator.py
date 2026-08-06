"""Orchestrator for coordinating the multi-node cross-examination pipeline."""

import pathlib
import sys

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.schemas import ClaimExtractionResult, ContradictionCheckResult, QuestionResult
from src.nodes.claim_extractor import extract_claims, ClaimExtractionError
from src.nodes.questioner import generate_question, QuestionGenerationError
from src.nodes.contradiction_checker import check_answer, ContradictionCheckError


class CrossExamSession:
    """
    Stateful session that coordinates the full cross-examination pipeline.

    Lifecycle
    ---------
    1. ``start(statement_transcript)``
       Extract claims from the witness's opening statement and generate
       the first adversarial question.

    2. ``submit_answer(answer_transcript)``  — repeat up to max_rounds times
       Check the answer for contradictions, update the claims, and either
       generate the next question (rounds remaining) or signal completion.

    3. When ``submit_answer`` returns ``{"done": True, ...}``, pass
       ``get_history()`` to the scorecard node to produce the final report.

    Attributes
    ----------
    statement : str | None
        The original witness statement transcript.
    claims : ClaimExtractionResult | None
        The current (possibly updated) claims list.
    current_question : QuestionResult | None
        The question that is currently awaiting an answer.
    history : list[dict]
        Each entry records one complete round:
        ``{question, answer, targets_claim_id, contradiction_found, explanation}``
    round_number : int
        Number of rounds completed so far (increments after each ``submit_answer``).
    max_rounds : int
        Total number of cross-examination rounds (default: 4).
    """

    def __init__(self, max_rounds: int = 4) -> None:
        """Initialise an empty session with no state."""
        self.statement: str | None = None
        self.claims: ClaimExtractionResult | None = None
        self.current_question: QuestionResult | None = None
        self.history: list[dict] = []
        self.round_number: int = 0
        self.max_rounds: int = max_rounds

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, statement_transcript: str) -> QuestionResult:
        """
        Begin a new cross-examination session.

        Extracts factual claims from the opening statement, then generates
        the first adversarial question.

        Args:
            statement_transcript: Plain-text witness statement (from the
                transcriber node or typed directly).

        Returns:
            QuestionResult — the first question to ask the witness.

        Raises:
            ClaimExtractionError: If claim extraction fails.
            QuestionGenerationError: If question generation fails.
        """
        self.statement = statement_transcript
        self.claims = extract_claims(statement_transcript)
        self.current_question = generate_question(self.claims, history=[])
        self.round_number = 1
        return self.current_question

    def submit_answer(self, answer_transcript: str) -> dict:
        """
        Submit the witness's answer to the current question.

        Checks the answer for contradictions, updates the claims list,
        records the round in history, and either generates the next question
        or signals that all rounds are complete.

        Args:
            answer_transcript: Plain-text transcript of the witness's spoken
                answer (from the transcriber node or typed directly).

        Returns:
            A dict with the following keys:

            - ``"contradiction_result"`` (ContradictionCheckResult):
              Analysis of whether the answer contradicted a claim.
            - ``"done"`` (bool):
              True when all ``max_rounds`` are complete.
            - ``"next_question"`` (QuestionResult | None):
              The next question to ask, or None when done.

        Raises:
            RuntimeError: If called before ``start()``.
            ContradictionCheckError: If contradiction checking fails.
            QuestionGenerationError: If question generation fails (mid-session).
        """
        if self.claims is None or self.current_question is None:
            raise RuntimeError(
                "Session has not been started. Call start() first."
            )

        # --- Check for contradictions ----------------------------------------
        contradiction_result: ContradictionCheckResult = check_answer(
            claims=self.claims,
            question=self.current_question,
            answer_transcript=answer_transcript,
        )

        # --- Update claims with refreshed weaknesses -------------------------
        self.claims = ClaimExtractionResult(claims=contradiction_result.updated_claims)

        # --- Record this round in history ------------------------------------
        self.history.append({
            "question": self.current_question.question,
            "targets_claim_id": self.current_question.targets_claim_id,
            "answer": answer_transcript,
            "contradiction_found": contradiction_result.contradiction_found,
            "explanation": contradiction_result.explanation,
        })

        # --- Decide: more rounds or done? ------------------------------------
        if self.round_number >= self.max_rounds:
            self.current_question = None
            return {
                "contradiction_result": contradiction_result,
                "next_question": None,
                "done": True,
            }

        # --- Generate next question ------------------------------------------
        next_question: QuestionResult = generate_question(
            claims=self.claims,
            history=self.history,
        )
        self.current_question = next_question
        self.round_number += 1

        return {
            "contradiction_result": contradiction_result,
            "next_question": next_question,
            "done": False,
        }

    def get_history(self) -> list[dict]:
        """
        Return the full history of rounds completed so far.

        Each entry is a dict with keys:
        ``question``, ``targets_claim_id``, ``answer``,
        ``contradiction_found``, ``explanation``.

        Returns:
            List of round records (may be empty if session not yet started).
        """
        return self.history
