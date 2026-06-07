"""Memory & Checkpointing Configuration.

Provides SQLite-backed conversation memory for follow-up questions.

Architecture:
  - SqliteSaver: Stores conversation history and graph checkpoints
  - Thread ID: Session identifier (one per conversation)
  - Checkpoint: Snapshot of graph state at each step

Database Schema:
  - checkpoints: Stores graph state snapshots
  - writes: Stores intermediate node outputs
  
Usage:
  from app.config.memory import get_checkpointer, create_session_id
  
  checkpointer = get_checkpointer()
  session_id = create_session_id()  # Or use existing session
  
  config = {"configurable": {"thread_id": session_id}}
  graph.invoke({"user_query": "..."}, config)
"""

import logging
import sqlite3
import uuid
from pathlib import Path
from typing import Optional

from langgraph.checkpoint.sqlite import SqliteSaver

from app.config.settings import AGENT_DIR

logger = logging.getLogger(__name__)

# ── Memory Database Path ───────────────────────────────────────────────────────
MEMORY_DB_PATH = AGENT_DIR / "data" / "memory" / "conversations.db"
MEMORY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── Checkpointer Singleton ─────────────────────────────────────────────────────
_checkpointer: Optional[SqliteSaver] = None


def get_checkpointer() -> SqliteSaver:
    """Get or create the SQLite checkpointer singleton.
    
    Uses synchronous SqliteSaver with direct connection.
    
    Returns:
        SqliteSaver: Configured checkpointer for conversation memory
    """
    global _checkpointer
    
    if _checkpointer is None:
        logger.info(f"Initializing SQLite checkpointer at: {MEMORY_DB_PATH}")
        
        # Create SQLite connection and pass to SqliteSaver
        conn = sqlite3.connect(str(MEMORY_DB_PATH), check_same_thread=False)
        _checkpointer = SqliteSaver(conn)
        
        logger.info("SQLite checkpointer initialized successfully")
    
    return _checkpointer


def create_session_id() -> str:
    """Generate a new unique session/thread ID.
    
    Returns:
        str: UUID-based session identifier
    """
    return str(uuid.uuid4())


def get_session_config(thread_id: str) -> dict:
    """Create a LangGraph config dict for a specific session.
    
    Args:
        thread_id: Session identifier
        
    Returns:
        dict: Config with thread_id for checkpointing
        
    Example:
        config = get_session_config("user-123-session-1")
        result = graph.invoke({"user_query": "..."}, config)
    """
    return {
        "configurable": {
            "thread_id": thread_id
        }
    }


def list_sessions(limit: int = 50) -> list[dict]:
    """List recent conversation sessions from the database.
    
    Args:
        limit: Maximum number of sessions to return
        
    Returns:
        list[dict]: Session metadata with thread_id, checkpoint count, last updated
    """
    try:
        conn = sqlite3.connect(str(MEMORY_DB_PATH), check_same_thread=False)
        cursor = conn.cursor()
        
        # Query unique thread IDs with metadata
        query = """
        SELECT 
            thread_id,
            COUNT(*) as checkpoint_count,
            MAX(checkpoint_id) as last_checkpoint_id,
            MAX(checkpoint_ns) as last_checkpoint_ns
        FROM checkpoints
        GROUP BY thread_id
        ORDER BY MAX(checkpoint_id) DESC
        LIMIT ?
        """
        
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()
        
        sessions = []
        for row in rows:
            sessions.append({
                "thread_id": row[0],
                "checkpoint_count": row[1],
                "last_checkpoint_id": row[2],
                "last_checkpoint_ns": row[3],
            })
        
        conn.close()
        return sessions
        
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        return []


def get_session_history(thread_id: str) -> list[dict]:
    """Retrieve conversation history for a specific session.
    
    Args:
        thread_id: Session identifier
        
    Returns:
        list[dict]: Checkpoints for this session
    """
    try:
        conn = sqlite3.connect(str(MEMORY_DB_PATH), check_same_thread=False)
        cursor = conn.cursor()
        
        query = """
        SELECT 
            checkpoint_id,
            checkpoint_ns,
            parent_checkpoint_id,
            type,
            checkpoint
        FROM checkpoints
        WHERE thread_id = ?
        ORDER BY checkpoint_id ASC
        """
        
        cursor.execute(query, (thread_id,))
        rows = cursor.fetchall()
        
        checkpoints = []
        for row in rows:
            checkpoints.append({
                "checkpoint_id": row[0],
                "checkpoint_ns": row[1],
                "parent_checkpoint_id": row[2],
                "type": row[3],
                "checkpoint_data": row[4][:100] + "..." if row[4] else None,  # Truncate
            })
        
        conn.close()
        return checkpoints
        
    except Exception as e:
        logger.error(f"Failed to get session history: {e}")
        return []


def get_conversation_history(thread_id: str) -> list[dict[str, str]]:
    """Extract conversation history (Q&A pairs) from checkpoint data.
    
    Args:
        thread_id: Session identifier
        
    Returns:
        list[dict]: List of {"query": "...", "response": "..."} pairs
    """
    try:
        conn = sqlite3.connect(str(MEMORY_DB_PATH), check_same_thread=False)
        cursor = conn.cursor()
        
        # Get the latest checkpoint for this thread
        query = """
        SELECT checkpoint
        FROM checkpoints
        WHERE thread_id = ?
        ORDER BY checkpoint_id DESC
        LIMIT 1
        """
        
        cursor.execute(query, (thread_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row or not row[0]:
            return []
        
        # Deserialize checkpoint data (it's pickled)
        import pickle
        checkpoint_data = pickle.loads(row[0])
        
        # Extract conversation_history from state
        if isinstance(checkpoint_data, dict):
            # Checkpoint structure: {"channel_values": {"state_name": {...}}}
            channel_values = checkpoint_data.get("channel_values", {})
            
            # Try different possible keys
            for key in channel_values:
                if isinstance(channel_values[key], dict):
                    conv_history = channel_values[key].get("conversation_history")
                    if conv_history:
                        return conv_history
        
        return []
        
    except Exception as e:
        logger.error(f"Failed to get conversation history for {thread_id}: {e}")
        return []


def clear_session(thread_id: str) -> bool:
    """Delete all checkpoints for a specific session.
    
    Args:
        thread_id: Session identifier
        
    Returns:
        bool: True if successful
    """
    try:
        conn = sqlite3.connect(str(MEMORY_DB_PATH), check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
        cursor.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Cleared session: {thread_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to clear session {thread_id}: {e}")
        return False


def clear_all_sessions() -> bool:
    """Delete all conversation history (use with caution!).
    
    Returns:
        bool: True if successful
    """
    try:
        conn = sqlite3.connect(str(MEMORY_DB_PATH), check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM checkpoints")
        cursor.execute("DELETE FROM writes")
        
        conn.commit()
        conn.close()
        
        logger.warning("Cleared ALL conversation sessions")
        return True
        
    except Exception as e:
        logger.error(f"Failed to clear all sessions: {e}")
        return False
