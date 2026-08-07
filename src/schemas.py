"""Pydantic schemas for data validation across the pipeline."""

from pydantic import BaseModel, Field, field_validator


class Claim(BaseModel):
    """A single factual claim extracted from a transcript."""

    id: str = Field(..., description="Unique identifier for this claim (e.g. 'c1', 'c2').")
    statement: str = Field(..., description="The factual claim as a plain sentence.")
    potential_weakness: str = Field(
        ..., description="Why this claim may be weak, ambiguous, or worth probing."
    )


class TranscriptionResult(BaseModel):
    """
    Produced by Node 0 — Voice Transcriber.

    Holds the plain-text transcript of an audio file and its duration.
    duration_sec is computed locally from the audio file metadata
    (e.g. via mutagen), not returned by Gemini.
    """

    transcript: str = Field(..., description="Full text transcription of the audio input.")
    duration_sec: float = Field(
        ..., ge=0.0, description="Duration of the audio file in seconds."
    )


class ClaimExtractionResult(BaseModel):
    """
    Produced by Node 1 — Claim Extractor.

    Breaks the transcript into individual factual claims, each annotated
    with a potential weakness for the questioner to target.
    """

    claims: list[Claim] = Field(
        ..., min_length=1, description="List of claims extracted from the transcript."
    )
    domain: str = Field(
        default="legal",
        description="The domain this extraction was performed under (e.g. 'legal', 'debate').",
    )


class QuestionResult(BaseModel):
    """
    Produced by Node 2 — Adversarial Questioner.

    A single follow-up question targeting the weakest untested claim,
    along with the ID of the claim it is designed to probe.
    """

    question: str = Field(..., description="The adversarial follow-up question.")
    targets_claim_id: str = Field(
        ..., description="ID of the claim this question is targeting."
    )


class ContradictionCheckResult(BaseModel):
    """
    Produced by Node 3 — Contradiction Checker.

    Records whether the witness's latest answer contradicts their original
    statement, explains why, and provides an updated claim list reflecting
    any weaknesses revealed.
    """

    contradiction_found: bool = Field(
        ..., description="True if the answer contradicts or weakens a prior claim."
    )
    explanation: str = Field(
        ..., description="Human-readable explanation of the contradiction (or lack thereof)."
    )
    updated_claims: list[Claim] = Field(
        ..., description="Revised claim list after incorporating the latest answer."
    )


class ScorecardResult(BaseModel):
    """
    Produced by Node 4 — Scorecard Generator.

    Final structured performance report after all cross-examination rounds
    are complete. Scores are integers on a 1–10 scale.
    """

    consistency_score: int = Field(
        ..., ge=1, le=10, description="How consistent the witness was across all answers (1–10)."
    )
    evasiveness_score: int = Field(
        ..., ge=1, le=10, description="How evasive the witness appeared across all answers (1–10)."
    )
    contradictions: list[str] = Field(
        ..., description="Plain-English descriptions of each contradiction detected."
    )
    summary: str = Field(
        ..., description="Overall narrative summary of the witness's performance."
    )

    @field_validator("consistency_score", "evasiveness_score")
    @classmethod
    def score_in_range(cls, v: int) -> int:
        """Ensure every score is strictly between 1 and 10 inclusive."""
        if not (1 <= v <= 10):
            raise ValueError(f"Score must be between 1 and 10, got {v}.")
        return v
