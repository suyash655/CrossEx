"""Streamlit application entry point — CrossEx cross-examination trainer."""

import pathlib
import sys
import tempfile
from datetime import datetime

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st
from audio_recorder_streamlit import audio_recorder
from dotenv import load_dotenv

load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=True)

from src.ui_theme import inject_custom_css
from src.ui_components import render_domain_selector, render_tension_meter
from src.orchestrator import CrossExamSession
from src.nodes.transcriber import transcribe_audio, AudioTranscriptionError
from src.nodes.scorecard import generate_scorecard, ScorecardError
from src.session_store import save_session, load_session_history

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
        "phase": "input",          # input | questioning | scorecard_ready | scorecard
        "session": None,           # CrossExamSession instance
        "current_question": None,  # QuestionResult
        "last_cr": None,           # last ContradictionCheckResult
        "scorecard": None,         # ScorecardResult
        "history_display": [],     # list of {q, a, contradiction_found} for sidebar
        "round_number": 0,
        "statement_text": "",
        "selected_domain": None,   # domain key chosen on the selector screen
        "contradiction_count": 0,  # cumulative contradictions found this session
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
            placeholder="Enter your statement here...",
        )
        if st.button("Use this text", key=f"{key_prefix}_use_text"):
            if text.strip():
                return text.strip()
            else:
                st.markdown(
                    '<div style="color:#b45309;font-family:Courier New,monospace;font-size:0.8rem;'
                    'padding:4px 0;">Please enter some text first.</div>',
                    unsafe_allow_html=True,
                )

    return None


# ── Sidebar — interrogation record ───────────────────────────────────────────
def _render_sidebar() -> None:
    with st.sidebar:
        st.title("⚖️ CrossEx")
        st.caption("Cross-Examination Trainer")
        st.divider()

        # Show selected domain badge
        domain_key = st.session_state.get("selected_domain")
        if domain_key:
            from src.domains import DOMAINS
            cfg = DOMAINS.get(domain_key, {})
            st.markdown(
                f'<div style="background:#1f0707;border:1px solid #B91C1C;'
                f'border-radius:2px;padding:6px 10px;margin-bottom:8px;">'
                f'<span style="font-family:Courier New,monospace;font-size:0.8rem;'
                f'color:#E5E5E5;">{cfg.get("icon","")} {cfg.get("display_name","")}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        if st.session_state.statement_text:
            with st.expander("📋 Opening Statement", expanded=False):
                st.markdown(
                    f'<div style="color:#E5E5E5;font-family:Courier New,monospace;'
                    f'font-size:0.9rem;line-height:1.6;padding:4px 0;">'
                    f'{st.session_state.statement_text}</div>',
                    unsafe_allow_html=True,
                )

        if st.session_state.history_display:
            st.subheader("📝 Interrogation Record")
            for i, entry in enumerate(st.session_state.history_display, 1):
                if entry.get("flagged_unfair"):
                    contradiction_icon = "⚡"
                else:
                    contradiction_icon = "⚠️" if entry["contradiction_found"] else "✓"
                with st.expander(
                    f"Round {i} — {contradiction_icon}",
                    expanded=(i == len(st.session_state.history_display)),
                ):
                    st.markdown(
                        f'<p style="color:#888;font-family:Courier New,monospace;font-size:0.75rem;'
                        f'margin:0 0 4px 0;"><strong>Q:</strong></p>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<p style="color:#E5E5E5;font-family:Courier New,monospace;font-size:0.85rem;'
                        f'margin:0 0 8px 0;line-height:1.5;">{entry["q"]}</p>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<p style="color:#888;font-family:Courier New,monospace;font-size:0.75rem;'
                        f'margin:0 0 4px 0;"><strong>A:</strong></p>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<p style="color:#E5E5E5;font-family:Courier New,monospace;font-size:0.85rem;'
                        f'margin:0 0 12px 0;line-height:1.5;">{entry["a"]}</p>',
                        unsafe_allow_html=True,
                    )
                    if entry.get("flagged_unfair"):
                        st.markdown(
                            '<div style="color:#b45309;font-family:Courier New,monospace;font-size:0.85rem;'
                            'padding:8px 12px;background:#1f1700;border-left:3px solid #b45309;'
                            'border-radius:2px;">Question flagged as unfair — won\'t count against score</div>',
                            unsafe_allow_html=True,
                        )
                    elif entry["contradiction_found"]:
                        st.markdown(
                            f'<div style="color:#E5E5E5;font-family:Courier New,monospace;font-size:0.85rem;'
                            f'padding:8px 12px;background:#2a0808;border-left:3px solid #B91C1C;'
                            f'border-radius:2px;">Contradiction: {entry["explanation"]}</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            f'<div style="color:#E5E5E5;font-family:Courier New,monospace;font-size:0.85rem;'
                            f'padding:8px 12px;background:#0a1f0a;border-left:3px solid #166534;'
                            f'border-radius:2px;">Consistent: {entry["explanation"]}</div>',
                            unsafe_allow_html=True,
                        )
        else:
            st.markdown(
                '<div style="color:#888;font-family:Courier New,monospace;font-size:0.8rem;'
                'padding:4px 0;">Questions and answers will appear here as the session progresses.</div>',
                unsafe_allow_html=True,
            )

        st.divider()
        
        # Past sessions history
        past_sessions = load_session_history()
        if past_sessions:
            st.markdown("### 📚 Your Past Sessions")
            from src.domains import DOMAINS
            for session in reversed(past_sessions[-5:]):  # Show last 5 sessions
                domain_key = session.get("domain", "legal")
                domain_cfg = DOMAINS.get(domain_key, {})
                domain_name = domain_cfg.get("display_name", domain_key).upper()
                domain_icon = domain_cfg.get("icon", "⚖️")
                
                # Parse timestamp
                try:
                    ts = datetime.fromisoformat(session["timestamp"])
                    date_str = ts.strftime("%b %d, %Y")
                except:
                    date_str = session["timestamp"][:10]
                
                consistency = session["final_scorecard"].get("consistency_score", "N/A")
                
                st.markdown(
                    f"""
                    <div style="
                        background:#0f0f0f;
                        border:1px solid #2a0a0a;
                        border-radius:2px;
                        padding:8px 12px;
                        margin-bottom:8px;
                    ">
                        <p style="color:#888;font-size:0.75rem;margin:0 0 4px 0;
                                  font-family:'Courier New',monospace;">
                            {date_str}
                        </p>
                        <p style="color:#E5E5E5;font-size:0.85rem;margin:0 0 4px 0;
                                  font-family:'Georgia',serif;">
                            {domain_icon} {domain_name}
                        </p>
                        <p style="color:#B91C1C;font-size:0.8rem;margin:0;
                                  font-family:'Courier New',monospace;">
                            Consistency: {consistency}/10
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown("### 📚 Your Past Sessions")
            st.markdown(
                '<div style="color:#888;font-family:Courier New,monospace;font-size:0.8rem;'
                'padding:4px 0;">No sessions recorded yet.</div>',
                unsafe_allow_html=True,
            )
        
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
    st.title("⚖️ CrossEx — Adversarial Interview Simulator")
    st.markdown(
        "Choose a domain, then provide the **opening statement** to be challenged."
    )
    st.divider()

    # ── Step 1: domain selection ──────────────────────────────────────────
    st.markdown("### Step 1 — Choose your domain")
    render_domain_selector()

    selected_domain = st.session_state.get("selected_domain")
    if not selected_domain:
        st.markdown(
            '<div style="color:#888;font-family:Courier New,monospace;font-size:0.8rem;'
            'padding:4px 0;">Select a domain above to continue.</div>',
            unsafe_allow_html=True,
        )
        return   # gate: nothing below renders until a domain is chosen

    st.divider()

    # ── Step 2: statement input ───────────────────────────────────────────
    from src.domains import DOMAINS
    cfg = DOMAINS[selected_domain]
    st.markdown(f"### Step 2 — Provide the opening statement")
    st.caption(
        f"{cfg['icon']} You selected **{cfg['display_name']}**. "
        f"{cfg['description']}"
    )

    transcript = _audio_input_widget("statement")

    if transcript:
        st.session_state.statement_text = transcript
        st.success("Statement received. Extracting claims…")

        with st.spinner("Analysing statement and generating first question…"):
            try:
                session = CrossExamSession(
                    max_rounds=MAX_ROUNDS,
                    domain=selected_domain,
                )
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

    # Tension meter — sits directly below the round progress bar
    render_tension_meter(
        contradiction_count=st.session_state.contradiction_count,
        total_rounds=MAX_ROUNDS,
    )
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
            st.markdown(
                f'<p style="color:#888;font-family:Courier New,monospace;font-size:0.8rem;'
                f'margin:0 0 16px 0;">Targeting claim [{targeted.id}]: <em>{targeted.statement}</em></p>',
                unsafe_allow_html=True,
            )

    # The question — label uses domain persona name
    from src.domains import DOMAINS
    domain_key = st.session_state.get("selected_domain", "legal")
    persona_label = DOMAINS.get(domain_key, {}).get("display_name", "OPPOSING COUNSEL").upper()

    # Question display with objection button
    col_q, col_obj = st.columns([14, 1])
    with col_q:
        st.markdown(
            f"""
            <div style="
                background:#1a0505;
                border-left:4px solid #B91C1C;
                border-radius:2px;
                padding:18px 22px;
                margin-bottom:0;
            ">
                <p style="color:#888;font-size:0.78rem;margin:0 0 6px 0;
                          font-family:'Courier New',monospace;letter-spacing:0.08em;">
                    {persona_label} — ROUND {rn}
                </p>
                <p style="color:#f0f0f0;font-size:1.1rem;margin:0;font-style:italic;
                          font-family:'Georgia',serif;">
                    &ldquo;{q.question}&rdquo;
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    with col_obj:
        st.markdown("<div style='height:32px;'></div>", unsafe_allow_html=True)  # Spacer for alignment
        if st.button("⚡", key=f"objection_r{rn}", help="Flag this question as unfair"):
            # Add objection to history display
            st.session_state.history_display.append({
                "q": q.question,
                "a": "[OBJECTION]",
                "contradiction_found": False,
                "explanation": "Question flagged as unfair by user",
                "flagged_unfair": True,
            })
            st.success("Objection noted — this question won't count against your score.")
            
            # Generate next question and move on
            with st.spinner("Generating next question…"):
                try:
                    from src.nodes.questioner import generate_question
                    next_q = generate_question(session.claims, session.history, session.domain)
                    session.current_question = next_q
                    session.round_number += 1
                    st.session_state.current_question = next_q
                    st.session_state.round_number = session.round_number
                    
                    if session.round_number > MAX_ROUNDS:
                        st.session_state.phase = "scorecard_ready"
                    st.rerun()
                except Exception as e:
                    st.error(f"Error generating next question: {e}")

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)  # Spacer

    # "Why this question?" expander
    if session.claims:
        targeted = next(
            (c for c in session.claims.claims if c.id == q.targets_claim_id),
            None,
        )
        if targeted:
            with st.expander("Why this question?"):
                st.markdown(
                    f"""
                    <div style="
                        background:#111111;
                        border:1px solid #2a0a0a;
                        border-radius:2px;
                        padding:12px 16px;
                    ">
                        <p style="color:#888;font-size:0.75rem;margin:0 0 8px 0;
                                  font-family:'Courier New',monospace;">
                            TARGETING CLAIM [{targeted.id}]
                        </p>
                        <p style="color:#E5E5E5;font-size:0.9rem;margin:0 0 8px 0;
                                  font-style:italic;font-family:'Georgia',serif;">
                            "{targeted.statement}"
                        </p>
                        <p style="color:#B91C1C;font-size:0.85rem;margin:0;
                                  font-family:'Courier New',monospace;">
                            ⚠ POTENTIAL WEAKNESS: {targeted.potential_weakness}
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown(
        '<p style="color:#E5E5E5;font-family:Georgia,serif;font-size:1.1rem;'
        'margin:24px 0 12px 0;"><strong>Your answer:</strong></p>',
        unsafe_allow_html=True,
    )
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

                if cr.contradiction_found:
                    st.session_state.contradiction_count += 1

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
    render_tension_meter(
        contradiction_count=st.session_state.contradiction_count,
        total_rounds=MAX_ROUNDS,
    )
    st.divider()

    # Show final contradiction result
    cr = st.session_state.last_cr
    if cr is not None:
        if cr.contradiction_found:
            st.error(f"⚠️ **Contradiction found** — {cr.explanation}")
        else:
            st.success(f"✓ **Consistent** — {cr.explanation}")

    st.divider()
    st.markdown(
        '<h3 style="color:#E5E5E5;font-family:Georgia,serif;font-size:1.5rem;'
        'margin:0 0 12px 0;">All rounds complete.</h3>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="color:#E5E5E5;font-family:Courier New,monospace;font-size:0.93rem;'
        'margin:0 0 16px 0;">Review the interrogation record in the sidebar, then generate the final scorecard.</p>',
        unsafe_allow_html=True,
    )

    if st.button("📊 Generate Scorecard", type="primary", use_container_width=True):
        session: CrossExamSession = st.session_state.session
        with st.spinner("Generating scorecard…"):
            try:
                scorecard = generate_scorecard(session.get_history())
                st.session_state.scorecard = scorecard
                st.session_state.phase = "scorecard"
                
                # Save session to local history
                from src.schemas import ScorecardResult
                session_record = {
                    "domain": st.session_state.get("selected_domain", "legal"),
                    "timestamp": datetime.now().isoformat(),
                    "final_scorecard": {
                        "consistency_score": scorecard.consistency_score,
                        "evasiveness_score": scorecard.evasiveness_score,
                        "contradictions": scorecard.contradictions,
                        "summary": scorecard.summary,
                    },
                }
                save_session(session_record)
                
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
    st.markdown(
        f'<h3 style="color:#E5E5E5;font-family:Georgia,serif;font-size:1.2rem;'
        f'margin:0 0 16px 0;">Contradictions ({len(sc.contradictions)})</h3>',
        unsafe_allow_html=True,
    )
    if sc.contradictions:
        for i, item in enumerate(sc.contradictions, 1):
            with st.expander(f"Contradiction {i}", expanded=True):
                st.markdown(
                    f'<div style="color:#E5E5E5;font-family:Courier New,monospace;'
                    f'font-size:0.9rem;line-height:1.6;padding:4px 0;">{item}</div>',
                    unsafe_allow_html=True,
                )
    else:
        st.markdown(
            '<div style="color:#166534;font-family:Courier New,monospace;font-size:0.9rem;'
            'padding:8px 12px;background:#0a1f0a;border-left:3px solid #166534;'
            'border-radius:2px;">No contradictions found across all rounds.</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # Summary
    st.markdown(
        '<h3 style="color:#E5E5E5;font-family:Georgia,serif;font-size:1.2rem;'
        'margin:0 0 16px 0;">Overall Assessment</h3>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div style="color:#E5E5E5;font-family:Courier New,monospace;font-size:0.9rem;'
        f'line-height:1.6;padding:12px 16px;background:#0f1a2a;border-left:3px solid #1d4ed8;'
        f'border-radius:2px;">{sc.summary}</div>',
        unsafe_allow_html=True,
    )

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
