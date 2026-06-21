from datetime import datetime, timezone
from pymongo.database import Database


def save_message(
    session_id: str,
    store_id: str,
    role: str,           # "user" or "assistant"
    content: str,
    db: Database,
    metadata: dict = None,
) -> None:
    """Appends a single message to the chat history collection."""
    doc = {
        "session_id": session_id,
        "store_id": store_id,
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc),
        "metadata": metadata or {},
    }
    db["chat_history"].insert_one(doc)


def get_history(
    session_id: str,
    store_id: str,
    db: Database,
    limit: int = 50,
) -> list[dict]:
    """
    Returns the last N messages for a session, oldest first.
    Always scoped to store_id to prevent cross-store data leaks.
    """
    messages = list(
        db["chat_history"]
        .find(
            {"session_id": session_id, "store_id": store_id},
            {"_id": 0},
        )
        .sort("timestamp", 1)
        .limit(limit)
    )

    for msg in messages:
        if isinstance(msg.get("timestamp"), datetime):
            msg["timestamp"] = msg["timestamp"].isoformat()

    return messages


def delete_session(session_id: str, store_id: str, db: Database) -> int:
    """
    Deletes all messages for a given session, scoped by store_id.
    Returns the number of messages deleted.
    """
    result = db["chat_history"].delete_many(
        {"session_id": session_id, "store_id": store_id}
    )
    return result.deleted_count


def list_sessions(store_id: str, db: Database) -> list[dict]:
    """
    Returns all unique session IDs for a store with their last message time.
    Useful for a chat history sidebar.
    """
    # Retrieve all messages for the store, sorted by timestamp descending
    messages = list(db["chat_history"].find({"store_id": store_id}).sort("timestamp", -1))
    
    session_map = {}
    for msg in messages:
        sid = msg.get("session_id")
        if not sid: continue
        if sid not in session_map:
            session_map[sid] = {
                "session_id": sid,
                "last_message": msg.get("timestamp"),
                "message_count": 0
            }
        session_map[sid]["message_count"] += 1
        
    sessions = list(session_map.values())
    sessions.sort(key=lambda x: x["last_message"], reverse=True)
    
    for s in sessions:
        if isinstance(s.get("last_message"), datetime):
            s["last_message"] = s["last_message"].isoformat()
    return sessions