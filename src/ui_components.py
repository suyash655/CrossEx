"""Reusable UI components for the CrossEx Streamlit app."""

import streamlit as st

from src.domains import DOMAINS

# ── CSS injected once for card grid ──────────────────────────────────────────
_CARD_CSS = """
<style>
/* Scope all card styles to .crossex-card-grid */
.crossex-card-grid {
    display: flex;
    gap: 0;
}

/* Each Streamlit column that holds a card button gets this wrapper */
div[data-testid="column"] .crossex-card-btn > button {
    width: 100% !important;
    height: 140px !important;
    padding: 12px 8px !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 6px !important;
    background-color: #111111 !important;
    border: 1px solid #2a0a0a !important;
    border-radius: 2px !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
    line-height: 1.3 !important;
    white-space: normal !important;
    transition: border-color 0.18s ease, transform 0.18s ease,
                box-shadow 0.18s ease !important;
    cursor: pointer !important;
}

div[data-testid="column"] .crossex-card-btn > button:hover {
    border-color: #B91C1C !important;
    transform: scale(1.04) !important;
    box-shadow: 0 0 14px 2px rgba(185, 28, 28, 0.40) !important;
    background-color: #1a0505 !important;
    z-index: 2 !important;
}

/* Selected state — brighter red border + persistent glow */
div[data-testid="column"] .crossex-card-selected > button {
    border: 2px solid #B91C1C !important;
    background-color: #1f0707 !important;
    box-shadow: 0 0 18px 3px rgba(185, 28, 28, 0.55) !important;
}

div[data-testid="column"] .crossex-card-selected > button:hover {
    transform: scale(1.02) !important;
}
</style>
"""


def render_domain_selector() -> None:
    """
    Display the 5 domains as a clickable card grid.

    Clicking a card stores its key in st.session_state["selected_domain"]
    and triggers a rerun. The selected card shows a highlighted border.
    The function reads and writes st.session_state["selected_domain"].
    """
    # Inject card CSS once per page load
    st.markdown(_CARD_CSS, unsafe_allow_html=True)

    selected = st.session_state.get("selected_domain", None)
    cols = st.columns(5, gap="small")

    for col, (domain_key, cfg) in zip(cols, DOMAINS.items()):
        is_selected = domain_key == selected
        card_class = "crossex-card-selected" if is_selected else "crossex-card-btn"

        with col:
            # Wrap button in a div with the appropriate class
            st.markdown(f'<div class="{card_class}">', unsafe_allow_html=True)

            # Button label: icon + name + description stacked via newlines
            label = f"{cfg['icon']}\n**{cfg['display_name']}**\n{cfg['description']}"

            if st.button(
                label,
                key=f"domain_card_{domain_key}",
                use_container_width=True,
                help=cfg["description"],
            ):
                st.session_state["selected_domain"] = domain_key
                st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

            # Show description below the card as caption for readability
            st.caption(cfg["description"])
