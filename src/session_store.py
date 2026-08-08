"""Local session history storage for CrossEx practice tracking."""

import json
import pathlib
from datetime import datetime
from typing import Any


def _get_history_path() -> pathlib.Path:
    """Get the path to the session history JSON file."""
    project_root = pathlib.Path(__file__).resolve().parents[1]
    data_dir = project_root / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir / "session_history.json"


def save_session(session_data: dict) -> None:
    """
    Append a session record to the local session history file.

    Args:
        session_data: Dict containing:
            - domain: str (e.g., "legal", "debate")
            - timestamp: str (ISO format datetime)
            - final_scorecard: dict with consistency_score, evasiveness_score, etc.
    """
    history_path = _get_history_path()
    
    # Load existing history
    if history_path.exists():
        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)
    else:
        history = []
    
    # Append new session record
    history.append(session_data)
    
    # Write back to file
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def load_session_history() -> list[dict[str, Any]]:
    """
    Load all past session records from the local history file.

    Returns:
        List of session records, each containing domain, timestamp, and final_scorecard.
        Returns empty list if file doesn't exist.
    """
    history_path = _get_history_path()
    
    if not history_path.exists():
        return []
    
    with open(history_path, "r", encoding="utf-8") as f:
        return json.load(f)
