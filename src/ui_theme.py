"""Custom CSS theme for CrossEx — dark interrogation room aesthetic."""

import streamlit as st


def inject_custom_css() -> None:
    """
    Inject global CSS into the Streamlit app to apply the CrossEx dark theme.

    - Background: #0D0D0D (near-black)
    - Primary accent: #B91C1C (deep red)
    - Secondary text: #E5E5E5 (off-white)
    - Headers: Georgia serif
    - Body/transcript: Courier New monospace
    - Buttons: sharp corners, red border, red glow on hover
    - Hides Streamlit chrome (hamburger, footer, badge)
    - Removes default top padding
    - Progress bars use red accent
    """
    st.markdown(
        """
        <style>
        /* ── Global reset & background ─────────────────────────────── */
        html, body, [data-testid="stAppViewContainer"],
        [data-testid="stApp"] {
            background-color: #0D0D0D !important;
            color: #E5E5E5 !important;
        }

        /* Main content area */
        [data-testid="stMain"], .main .block-container {
            background-color: #0D0D0D !important;
            padding-top: 1.5rem !important;
            padding-bottom: 2rem !important;
        }

        /* Sidebar */
        [data-testid="stSidebar"] {
            background-color: #111111 !important;
            border-right: 1px solid #2a0a0a !important;
        }
        [data-testid="stSidebar"] * {
            color: #E5E5E5 !important;
        }

        /* ── Typography ─────────────────────────────────────────────── */
        h1, h2, h3, h4, h5, h6 {
            font-family: "Georgia", "Times New Roman", serif !important;
            color: #FFFFFF !important;
            letter-spacing: 0.03em;
        }

        h1 { font-size: 2rem !important; border-bottom: 2px solid #B91C1C; padding-bottom: 0.4rem; }
        h2 { font-size: 1.5rem !important; }
        h3 { font-size: 1.2rem !important; color: #E5E5E5 !important; }

        p, li, span, div, label, .stMarkdown {
            font-family: "Courier New", "Lucida Console", monospace !important;
            color: #E5E5E5 !important;
            font-size: 0.93rem !important;
            line-height: 1.65 !important;
        }

        /* Caption text */
        [data-testid="stCaptionContainer"],
        .stCaption, small {
            font-family: "Courier New", monospace !important;
            color: #888888 !important;
            font-size: 0.8rem !important;
        }

        /* ── Buttons ────────────────────────────────────────────────── */
        .stButton > button {
            background-color: #1a0505 !important;
            color: #E5E5E5 !important;
            border: 1px solid #B91C1C !important;
            border-radius: 2px !important;
            font-family: "Courier New", monospace !important;
            font-size: 0.88rem !important;
            letter-spacing: 0.06em !important;
            text-transform: uppercase !important;
            padding: 0.45rem 1.2rem !important;
            transition: box-shadow 0.2s ease, background-color 0.2s ease !important;
        }
        .stButton > button:hover {
            background-color: #2a0808 !important;
            box-shadow: 0 0 10px 2px rgba(185, 28, 28, 0.55) !important;
            border-color: #dc2626 !important;
        }
        .stButton > button:active {
            box-shadow: 0 0 4px 1px rgba(185, 28, 28, 0.8) !important;
        }
        /* Primary button variant */
        .stButton > button[kind="primary"] {
            background-color: #7f1d1d !important;
            color: #FFFFFF !important;
        }
        .stButton > button[kind="primary"]:hover {
            background-color: #991b1b !important;
            box-shadow: 0 0 14px 3px rgba(185, 28, 28, 0.7) !important;
        }
        /* Icon-only buttons (like objection) */
        .stButton > button:has(> span:only-child) {
            padding: 0.4rem 0.6rem !important;
            font-size: 1.1rem !important;
            min-height: auto !important;
        }

        /* ── Text inputs & text areas ───────────────────────────────── */
        .stTextInput > div > div > input,
        .stTextArea > div > div > textarea {
            background-color: #141414 !important;
            color: #E5E5E5 !important;
            border: 1px solid #3d1515 !important;
            border-radius: 2px !important;
            font-family: "Courier New", monospace !important;
            font-size: 0.9rem !important;
        }
        .stTextInput > div > div > input::placeholder,
        .stTextArea > div > div > textarea::placeholder {
            color: #666666 !important;
        }
        .stTextInput > div > div > input:focus,
        .stTextArea > div > div > textarea:focus {
            border-color: #B91C1C !important;
            box-shadow: 0 0 6px rgba(185, 28, 28, 0.4) !important;
            outline: none !important;
        }

        /* ── File uploader ──────────────────────────────────────────── */
        [data-testid="stFileUploader"] {
            background-color: #141414 !important;
            border: 1px dashed #3d1515 !important;
            border-radius: 2px !important;
        }
        [data-testid="stFileUploader"]:hover {
            border-color: #B91C1C !important;
        }

        /* ── Tabs ───────────────────────────────────────────────────── */
        [data-testid="stTabs"] [role="tab"] {
            font-family: "Courier New", monospace !important;
            font-size: 0.85rem !important;
            color: #888888 !important;
            border-radius: 0 !important;
            letter-spacing: 0.05em;
        }
        [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
            color: #E5E5E5 !important;
            border-bottom: 2px solid #B91C1C !important;
            background-color: transparent !important;
        }
        [data-testid="stTabs"] [role="tabpanel"] {
            background-color: #0D0D0D !important;
        }

        /* ── Progress bar ───────────────────────────────────────────── */
        [data-testid="stProgressBar"] > div > div {
            background-color: #7f1d1d !important;
        }
        [data-testid="stProgressBar"] > div {
            background-color: #1f1f1f !important;
        }
        /* Fallback for inner fill element */
        div[role="progressbar"] > div {
            background-color: #B91C1C !important;
        }

        /* ── Alerts / callout boxes ─────────────────────────────────── */
        [data-testid="stAlert"] {
            border-radius: 2px !important;
            font-family: "Courier New", monospace !important;
        }
        /* st.error */
        [data-testid="stAlert"][data-baseweb="notification"][kind="error"],
        div[data-testid="stException"] {
            background-color: #2a0808 !important;
            border-left: 3px solid #B91C1C !important;
        }
        /* st.success */
        [data-testid="stAlert"][data-baseweb="notification"][kind="success"] {
            background-color: #0a1f0a !important;
            border-left: 3px solid #166534 !important;
        }
        /* st.info */
        [data-testid="stAlert"][data-baseweb="notification"][kind="info"] {
            background-color: #0f1a2a !important;
            border-left: 3px solid #1d4ed8 !important;
        }
        /* st.warning */
        [data-testid="stAlert"][data-baseweb="notification"][kind="warning"] {
            background-color: #1f1700 !important;
            border-left: 3px solid #b45309 !important;
        }

        /* ── Expanders ──────────────────────────────────────────────── */
        [data-testid="stExpander"] {
            background-color: #111111 !important;
            border: 1px solid #2a0a0a !important;
            border-radius: 2px !important;
        }
        [data-testid="stExpander"] summary {
            font-family: "Georgia", serif !important;
            color: #E5E5E5 !important;
        }
        [data-testid="stExpander"] summary:hover {
            color: #FFFFFF !important;
        }

        /* ── Metrics ────────────────────────────────────────────────── */
        [data-testid="stMetric"] {
            background-color: #111111 !important;
            border: 1px solid #2a0a0a !important;
            border-radius: 2px !important;
            padding: 0.8rem 1rem !important;
        }
        [data-testid="stMetricLabel"] {
            font-family: "Georgia", serif !important;
            color: #888888 !important;
            font-size: 0.85rem !important;
        }
        [data-testid="stMetricValue"] {
            font-family: "Georgia", serif !important;
            color: #FFFFFF !important;
            font-size: 1.8rem !important;
        }
        [data-testid="stMetricDelta"] {
            font-family: "Courier New", monospace !important;
            font-size: 0.8rem !important;
        }
        /* Metric delta colors */
        [data-testid="stMetricDelta"][data-color="normal"] {
            color: #166534 !important;
        }
        [data-testid="stMetricDelta"][data-color="inverse"] {
            color: #B91C1C !important;
        }

        /* ── Divider ────────────────────────────────────────────────── */
        hr {
            border-color: #2a0a0a !important;
            margin: 1.2rem 0 !important;
        }

        /* ── Selectbox / dropdown ───────────────────────────────────── */
        [data-testid="stSelectbox"] > div > div {
            background-color: #141414 !important;
            border: 1px solid #3d1515 !important;
            border-radius: 2px !important;
            color: #E5E5E5 !important;
            font-family: "Courier New", monospace !important;
        }

        /* ── Hide Streamlit chrome ──────────────────────────────────── */
        #MainMenu { visibility: hidden !important; }
        footer { visibility: hidden !important; }
        header { visibility: hidden !important; }
        [data-testid="stToolbar"] { display: none !important; }
        [data-testid="manage-app-button"] { display: none !important; }
        .viewerBadge_container__r5tak { display: none !important; }
        #stDecoration { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
