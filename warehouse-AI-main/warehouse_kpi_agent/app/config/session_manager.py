"""Session Manager for Streamlit UI.

Manages conversation sessions with metadata (name, created_at, last_message).
Stores metadata in JSON file, actual conversation history in SQLite via checkpointer.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.config.memory import create_session_id, MEMORY_DB_PATH

logger = logging.getLogger(__name__)

# ── Session metadata storage path ───────────────────────────────────────────
SESSIONS_METADATA_PATH = Path(MEMORY_DB_PATH).parent / "sessions_metadata.json"


# ── Session metadata structure ─────────────────────────────────────────────
class SessionMetadata:
    """Session metadata container."""
    
    def __init__(
        self,
        session_id: str,
        name: str,
        created_at: str,
        last_accessed: str,
        first_query: Optional[str] = None,
    ):
        self.session_id = session_id
        self.name = name
        self.created_at = created_at
        self.last_accessed = last_accessed
        self.first_query = first_query or ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "name": self.name,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "first_query": self.first_query,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionMetadata":
        return cls(
            session_id=data["session_id"],
            name=data["name"],
            created_at=data["created_at"],
            last_accessed=data["last_accessed"],
            first_query=data.get("first_query", ""),
        )


# ── Utilities ──────────────────────────────────────────────────────────────

def _ensure_metadata_file() -> None:
    """Ensure the metadata file exists."""
    if not SESSIONS_METADATA_PATH.exists():
        SESSIONS_METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        SESSIONS_METADATA_PATH.write_text(json.dumps({}))


def _load_metadata() -> dict[str, SessionMetadata]:
    """Load all session metadata from JSON file."""
    _ensure_metadata_file()
    try:
        data = json.loads(SESSIONS_METADATA_PATH.read_text())
        return {sid: SessionMetadata.from_dict(meta) for sid, meta in data.items()}
    except Exception as exc:
        logger.error("Failed to load session metadata: %s", exc)
        return {}


def _save_metadata(sessions: dict[str, SessionMetadata]) -> None:
    """Save session metadata to JSON file."""
    _ensure_metadata_file()
    try:
        data = {sid: meta.to_dict() for sid, meta in sessions.items()}
        SESSIONS_METADATA_PATH.write_text(json.dumps(data, indent=2))
    except Exception as exc:
        logger.error("Failed to save session metadata: %s", exc)


def generate_session_name(first_query: str, max_words: int = 10) -> str:
    """Generate session name from first query (first N words).
    
    Args:
        first_query: The first user query in the session
        max_words: Maximum number of words to use (default: 10)
    
    Returns:
        Session name string
    """
    if not first_query or not first_query.strip():
        return "New Conversation"
    
    words = first_query.strip().split()
    name_words = words[:max_words]
    name = " ".join(name_words)
    
    # Add ellipsis if truncated
    if len(words) > max_words:
        name += "..."
    
    # Cap length at 100 chars
    if len(name) > 100:
        name = name[:97] + "..."
    
    return name


# ── Public API ─────────────────────────────────────────────────────────────

def create_session(first_query: Optional[str] = None) -> str:
    """Create a new session with auto-generated name.
    
    Args:
        first_query: Optional first query to generate session name from
    
    Returns:
        Session ID (thread_id)
    """
    session_id = create_session_id()
    now = datetime.now().isoformat()
    
    name = generate_session_name(first_query) if first_query else "New Conversation"
    
    sessions = _load_metadata()
    sessions[session_id] = SessionMetadata(
        session_id=session_id,
        name=name,
        created_at=now,
        last_accessed=now,
        first_query=first_query or "",
    )
    _save_metadata(sessions)
    
    logger.info("Created new session: %s (%s)", session_id, name)
    return session_id


def list_sessions(limit: int = 50) -> list[SessionMetadata]:
    """List all sessions, ordered by last_accessed (most recent first).
    
    Args:
        limit: Maximum number of sessions to return
    
    Returns:
        List of SessionMetadata objects
    """
    sessions = _load_metadata()
    sorted_sessions = sorted(
        sessions.values(),
        key=lambda s: s.last_accessed,
        reverse=True,
    )
    return sorted_sessions[:limit]


def get_session(session_id: str) -> Optional[SessionMetadata]:
    """Get session metadata by ID.
    
    Args:
        session_id: Session ID to retrieve
    
    Returns:
        SessionMetadata object or None if not found
    """
    sessions = _load_metadata()
    return sessions.get(session_id)


def update_session_access(session_id: str) -> None:
    """Update the last_accessed timestamp for a session.
    
    Args:
        session_id: Session ID to update
    """
    sessions = _load_metadata()
    if session_id in sessions:
        sessions[session_id].last_accessed = datetime.now().isoformat()
        _save_metadata(sessions)


def rename_session(session_id: str, new_name: str) -> bool:
    """Rename a session.
    
    Args:
        session_id: Session ID to rename
        new_name: New name for the session
    
    Returns:
        True if successful, False otherwise
    """
    sessions = _load_metadata()
    if session_id not in sessions:
        return False
    
    sessions[session_id].name = new_name
    _save_metadata(sessions)
    logger.info("Renamed session %s to: %s", session_id, new_name)
    return True


def delete_session(session_id: str) -> bool:
    """Delete a session (metadata only; checkpoints remain in SQLite).
    
    Args:
        session_id: Session ID to delete
    
    Returns:
        True if successful, False otherwise
    """
    sessions = _load_metadata()
    if session_id not in sessions:
        return False
    
    del sessions[session_id]
    _save_metadata(sessions)
    logger.info("Deleted session: %s", session_id)
    return True


def update_session_first_query(session_id: str, query: str) -> None:
    """Update first query and regenerate session name if needed.
    
    Args:
        session_id: Session ID to update
        query: First query text
    """
    sessions = _load_metadata()
    if session_id not in sessions:
        return
    
    session = sessions[session_id]
    
    # Only update if first_query is empty or was "New Conversation"
    if not session.first_query or session.name == "New Conversation":
        session.first_query = query
        session.name = generate_session_name(query)
        session.last_accessed = datetime.now().isoformat()
        _save_metadata(sessions)
        logger.info("Updated session %s with first query: %s", session_id, session.name)
