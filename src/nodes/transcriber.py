"""Node for transcribing audio input to text using Groq Whisper."""

import os
import pathlib
import sys

# Ensure the project root is on sys.path when this file is run directly.
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from groq import Groq
from mutagen.mp3 import MP3
from mutagen.wave import WAVE
from mutagen import File as MutagenFile
from dotenv import load_dotenv

from src.schemas import TranscriptionResult

load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=True)

# ---------------------------------------------------------------------------
# Supported formats
# ---------------------------------------------------------------------------
_SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm"}
_MIME_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
}


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------
class AudioTranscriptionError(Exception):
    """Raised when audio transcription fails for any known reason."""


# ---------------------------------------------------------------------------
# Duration helper
# ---------------------------------------------------------------------------
def _get_duration_sec(file_path: pathlib.Path) -> float:
    """
    Return the duration of an audio file in seconds using mutagen.

    Raises AudioTranscriptionError if duration cannot be determined.
    """
    ext = file_path.suffix.lower()
    try:
        if ext == ".mp3":
            audio = MP3(file_path)
        elif ext == ".wav":
            audio = WAVE(file_path)
        else:
            audio = MutagenFile(file_path)
            if audio is None:
                raise AudioTranscriptionError(
                    f"Unsupported audio format '{ext}'. "
                    f"Supported formats: {', '.join(_SUPPORTED_EXTENSIONS)}."
                )
        duration: float = audio.info.length  # type: ignore[union-attr]
    except AudioTranscriptionError:
        raise
    except Exception as exc:
        raise AudioTranscriptionError(
            f"Could not read audio metadata from '{file_path}': {exc}"
        ) from exc

    if duration <= 0:
        raise AudioTranscriptionError(
            f"Audio file '{file_path}' appears to be silent or has zero duration."
        )
    return duration


# ---------------------------------------------------------------------------
# Main node function
# ---------------------------------------------------------------------------
def transcribe_audio(file_path: str) -> TranscriptionResult:
    """
    Transcribe an audio file using Groq Whisper (whisper-large-v3) and
    return a TranscriptionResult with transcript text and audio duration.

    Duration is measured locally via mutagen — not from the API response.

    Args:
        file_path: Absolute or relative path to an audio file.

    Returns:
        TranscriptionResult with transcript and duration_sec fields.

    Raises:
        AudioTranscriptionError: file not found, unsupported format,
            silent audio, API failure, or empty transcript.
    """
    path = pathlib.Path(file_path)

    # 1. File existence
    if not path.exists():
        raise AudioTranscriptionError(
            f"Audio file not found: '{file_path}'. "
            "Please check the path and try again."
        )

    # 2. Format check
    ext = path.suffix.lower()
    if ext not in _SUPPORTED_EXTENSIONS:
        raise AudioTranscriptionError(
            f"Unsupported audio format '{ext}'. "
            f"Supported formats: {', '.join(_SUPPORTED_EXTENSIONS)}."
        )

    # 3. Compute duration locally
    duration_sec = _get_duration_sec(path)

    # 4. Configure Groq client
    api_key = os.getenv("GROQ_API_KEY") or os.getenv("GRoQ_API_KEY")
    if not api_key:
        raise AudioTranscriptionError(
            "GROQ_API_KEY is not set. "
            "Add it to your .env file or environment variables."
        )
    client = Groq(api_key=api_key)

    # 5. Transcribe via Groq Whisper
    try:
        with open(path, "rb") as audio_file:
            response = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=(path.name, audio_file),
                response_format="text",
                prompt=(
                    "Transcribe this audio recording word-for-word. "
                    "Return only the transcript text with no commentary."
                ),
            )
    except Exception as exc:
        raise AudioTranscriptionError(
            f"Groq Whisper transcription failed for '{file_path}': {exc}"
        ) from exc

    # 6. Validate response (text format returns a plain string)
    transcript = (response if isinstance(response, str) else getattr(response, "text", "")).strip()
    if not transcript:
        raise AudioTranscriptionError(
            f"Groq returned an empty transcript for '{file_path}'. "
            "The audio may be silent, too noisy, or in an unrecognised language."
        )

    return TranscriptionResult(transcript=transcript, duration_sec=duration_sec)


# ---------------------------------------------------------------------------
# Manual test entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.nodes.transcriber <path/to/audio.mp3>")
        sys.exit(1)

    audio_path = sys.argv[1]
    try:
        result = transcribe_audio(audio_path)
        print(f"Duration  : {result.duration_sec:.2f}s")
        print(f"Transcript:\n{result.transcript}")
    except AudioTranscriptionError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
