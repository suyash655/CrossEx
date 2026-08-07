"""Streamlit application entry point — CrossEx cross-examination trainer."""

import pathlib
import sys
import tempfile

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st
from audio_recorder_streamlit import audio_recorder
from dotenv import load_dotenv

load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=True)

from src.ui_theme import inject_custom_css
from src.orchestrator import CrossExamSession
from src.nodes.transcriber import transcribe_audio, AudioTranscriptionError
from src.nodes.scorecard import generate_scorecard, ScorecardError

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CrossEx — Cross-Examination Trainer",
    page_icon="⚖️",
    layout="wide",
)
inject_custom_css()

MAX_ROUNDS = 4

# ── Session state bootstrap ──────────────────────────────────────────────────
def _init_state() -> None:
    defaults = {
        "phase": "input",          # input | questioning | scorecard
        "session": None,           # CrossExamSession instance
        "current_question": None,  # QuestionResult
        "last_cr": None,           # last ContradictionCheckResult
        "scorecard": None,         # ScorecardResult
        "history_display": [],     # list of {q, a, contradiction_found} for sidebar
        "round_number": 0,
        "statement_text": "",
        "error": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


def _reset() -> None:
    """Clear all session state and restart."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    _init_state()
    st.rerun()


# ── Helpers ───────────────────────────────────────────────────────────────────
def _transcribe_bytes(audio_bytes: bytes, suffix: str = ".wav") -> str:
    """Write audio bytes to a temp file and transcribe via Groq Whisper."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    result = transcribe_audio(tmp_path)
    return result.transcript


def _audio_input_widget(key_prefix: str) -> str | None:
    """
    Render three input options (record / upload / type) and return
    the plain-text transcript, or None if no input yet.
    """
    tab_rec, tab_up, tab_type = st.tabs(["🎙 Record", "📂 Upload", "⌨️ Type"])

    with tab_rec:
        st.caption("Click the microphone to start/stop recording.")
        audio_bytes = audio_recorder(
            key=f"{key_prefix}_recorder",
            pause_threshold=3.0,
            sample_rate=16_000,
        )
        if audio_bytes:
            st.audio(audio_bytes, format="audio/wav")
            if st.button("Use this recording", key=f"{key_prefix}_use_rec"):
                with st.spinner("Transcribing…"):
                    try:
                        return _transcribe_bytes(audio_bytes, ".wav")
                    except AudioTranscriptionError as e:
                        st.error(f"Transcription failed: {e}")

    with tab_up:
        uploaded = st.file_uploader(
            "Upload an MP3 or WAV file",
            type=["mp3", "wav"],
            key=f"{key_prefix}_upload",
        )
        if uploaded:
            suffix = ".mp3" if uploaded.name.endswith(".mp3") else ".wav"
            if st.button("Use this file", key=f"{key_prefix}_use_up"):
                with st.spinner("Transcribing…"):
                    try:
                        return _transcribe_bytes(uploaded.read(), suffix)
                    except AudioTranscriptionError as e:
                        st.error(f"Transcription failed: {e}")

    with tab_type:
        text = st.text_area(
            "Type or paste your statement here",
            key=f"{key_prefix}_text",
            height=120,
        )
        if st.button("Use this text", key=f"{key_prefix}_use_text"):
            if text.strip():
                return text.strip()
            else:
                st.warning("Please enter some text first.")

    return None


# ── Sidebar — interrogation record ───────────────────────────────────────────
def _render_sidebar() -> None:
    with st.sidebar:
        st.title("⚖️ CrossEx")
        st.caption("Cross-Examination Trainer")
        st.divider()

        if st.session_state.statement_text:
            with st.expander("📋 Opening Statement", expanded=False):
                st.write(st.session_state.statement_text)

        if st.session_state.history_display:
            st.subheader("📝 Interrogation Record")
            for i, entry in enumerate(st.session_state.history_display, 1):
                contradiction_icon = "⚠️" if entry["contradiction_found"] else "✓"
                with st.expander(
                    f"Round {i} — {contradiction_icon}",
                    expanded=(i == len(st.session_state.history_display)),
                ):
                    st.markdown(f"**Q:** {entry['q']}")
                    st.markdown(f"**A:** {entry['a']}")
                    if entry["contradiction_found"]:
                        st.error(f"Contradiction: {entry['explanation']}")
                    else:
                        st.success(f"Consistent: {entry['explanation']}")
        else:
            st.info("Questions and answers will appear here as the session progresses.")

        st.divider()
        if st.button("🔄 Start New Session", use_container_width=True):
            _reset()


# ── Progress bar ──────────────────────────────────────────────────────────────
def _render_progress() -> None:
    rn = st.session_state.round_number
    progress = rn / MAX_ROUNDS
    st.progress(progress, text=f"Round {rn} of {MAX_ROUNDS}")


# ── Phase: input ──────────────────────────────────────────────────────────────
def _phase_input() -> None:
    st.title("⚖️ CrossEx — Cross-Examination Trainer")
    st.markdown(
        "Record, upload, or type the **witness's opening statement**. "
        "CrossEx will extract claims and begin the cross-examination."
    )
    st.divider()

    transcript = _audio_input_widget("statement")

    if transcript:
        st.session_state.statement_text = transcript
        st.success("Statement received. Extracting claims…")

        with st.spinner("Analysing statement and generating first question…"):
            try:
                session = CrossExamSession(max_rounds=MAX_ROUNDS)
                q = session.start(transcript)
                st.session_state.session = session
                st.session_state.current_question = q
                st.session_state.round_number = 1
                st.session_state.phase = "questioning"
                st.rerun()
            except Exception as e:
                st.error(f"Failed to start session: {e}")


# ── Phase: questioning ────────────────────────────────────────────────────────
def _phase_questioning() -> None:
    _render_progress()
    st.divider()

    session: CrossExamSession = st.session_state.session
    q = st.session_state.current_question
    rn = st.session_state.round_number

    # Show last contradiction result if there is one
    if st.session_state.last_cr is not None:
        cr = st.session_state.last_cr
        if cr.contradiction_found:
            st.error(f"⚠️ **Contradiction found** — {cr.explanation}")
        else:
            st.success(f"✓ **Consistent** — {cr.explanation}")
        st.divider()

    # Targeted claim context
    if session.claims:
        targeted = next(
            (c for c in session.claims.claims if c.id == q.targets_claim_id),
            None,
        )
        if targeted:
            st.caption(f"Targeting claim [{targeted.id}]: _{targeted.statement}_")

    # The question
    st.markdown(
        f"""
        <div style="
            background:#1a1a2e;
            border-left:4px solid #e94560;
            border-radius:6px;
            padding:18px 22px;
            margin-bottom:16px;
        ">
            <p style="color:#aaa;font-size:0.8rem;margin:0 0 6px 0;">
                OPPOSING COUNSEL — ROUND {rn}
            </p>
            <p style="color:#f0f0f0;font-size:1.15rem;margin:0;font-style:italic;">
                "{q.question}"
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("**Your answer:**")
    answer_text = _audio_input_widget(f"answer_r{rn}")

    if answer_text:
        with st.spinner("Checking answer…"):
            try:
                result = session.submit_answer(answer_text)
                cr = result["contradiction_result"]

                # Update sidebar history
                st.session_state.history_display.append({
                    "q": q.question,
                    "a": answer_text,
                    "contradiction_found": cr.contradiction_found,
                    "explanation": cr.explanation,
                })

                st.session_state.last_cr = cr

                if result["done"]:
                    st.session_state.phase = "scorecard_ready"
                else:
                    st.session_state.current_question = result["next_question"]
                    st.session_state.round_number += 1

                st.rerun()

            except Exception as e:
                st.error(f"Error processing answer: {e}")


# ── Phase: scorecard_ready ────────────────────────────────────────────────────
def _phase_scorecard_ready() -> None:
    _render_progress()
    st.divider()

    # Show final contradiction result
    cr = st.session_state.last_cr
    if cr is not None:
        if cr.contradiction_found:
            st.error(f"⚠️ **Contradiction found** — {cr.explanation}")
        else:
            st.success(f"✓ **Consistent** — {cr.explanation}")

    st.divider()
    st.markdown("### All rounds complete.")
    st.markdown("Review the interrogation record in the sidebar, then generate the final scorecard.")

    if st.button("📊 Generate Scorecard", type="primary", use_container_width=True):
        session: CrossExamSession = st.session_state.session
        with st.spinner("Generating scorecard…"):
            try:
                scorecard = generate_scorecard(session.get_history())
                st.session_state.scorecard = scorecard
                st.session_state.phase = "scorecard"
                st.rerun()
            except ScorecardError as e:
                st.error(f"Scorecard generation failed: {e}")


# ── Phase: scorecard ──────────────────────────────────────────────────────────
def _phase_scorecard() -> None:
    sc = st.session_state.scorecard
    st.title("📊 Final Scorecard")
    st.divider()

    # Scores
    col1, col2 = st.columns(2)
    with col1:
        consistency_delta = sc.consistency_score - 5
        st.metric(
            label="Consistency Score",
            value=f"{sc.consistency_score} / 10",
            delta=f"{consistency_delta:+d} vs neutral",
            delta_color="normal",
        )
        st.caption("Higher = fewer / less severe contradictions")

    with col2:
        evasiveness_delta = sc.evasiveness_score - 5
        st.metric(
            label="Evasiveness Score",
            value=f"{sc.evasiveness_score} / 10",
            delta=f"{evasiveness_delta:+d} vs neutral",
            delta_color="inverse",  # high evasiveness is bad → red
        )
        st.caption("Higher = more evasive answers")

    st.divider()

    # Contradictions
    st.subheader(f"Contradictions ({len(sc.contradictions)})")
    if sc.contradictions:
        for i, item in enumerate(sc.contradictions, 1):
            with st.expander(f"Contradiction {i}", expanded=True):
                st.warning(item)
    else:
        st.success("No contradictions found across all rounds.")

    st.divider()

    # Summary
    st.subheader("Overall Assessment")
    st.info(sc.summary)

    st.divider()
    if st.button("🔄 Start New Session", type="primary", use_container_width=True):
        _reset()


# ── Router ────────────────────────────────────────────────────────────────────
_render_sidebar()

phase = st.session_state.phase

if phase == "input":
    _phase_input()
elif phase == "questioning":
    _phase_questioning()
elif phase == "scorecard_ready":
    _phase_scorecard_ready()
elif phase == "scorecard":
    _phase_scorecard()
