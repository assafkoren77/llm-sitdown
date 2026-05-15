"""JSON-based storage for conversations."""

import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from .config import DATA_DIR


INDEX_FILE_NAME = "conversations_index.json"


def ensure_data_dir():
    """Ensure the data directory exists."""
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)


def get_conversation_path(conversation_id: str) -> str:
    """Get the file path for a conversation."""
    return os.path.join(DATA_DIR, f"{conversation_id}.json")


def get_index_path() -> str:
    """Get the file path for the conversation index."""
    return os.path.join(DATA_DIR, INDEX_FILE_NAME)


def _load_index() -> Optional[List[Dict[str, Any]]]:
    """Load the conversation index file."""
    path = get_index_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_index(index: List[Dict[str, Any]]):
    """Save the conversation index file."""
    ensure_data_dir()
    path = get_index_path()
    with open(path, 'w') as f:
        json.dump(index, f, indent=2)


def rebuild_index() -> List[Dict[str, Any]]:
    """
    Rebuild the conversation index from actual conversation files.
    Use this fallback if index is missing or corrupted.
    """
    ensure_data_dir()
    index = []
    
    for filename in os.listdir(DATA_DIR):
        if filename.endswith('.json') and filename != INDEX_FILE_NAME:
            path = os.path.join(DATA_DIR, filename)
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    index.append({
                        "id": data["id"],
                        "created_at": data["created_at"],
                        "title": data.get("title", "New Conversation"),
                        "message_count": len(data["messages"])
                    })
            except (json.JSONDecodeError, OSError):
                continue

    # Sort by creation time, newest first
    index.sort(key=lambda x: x["created_at"], reverse=True)
    _save_index(index)
    return index


def _update_index_entry(conversation: Dict[str, Any]):
    """Update or add a single entry in the index."""
    index = _load_index()
    if index is None:
        index = rebuild_index()
        return  # rebuild already includes the current state if file was saved

    # Create metadata entry
    entry = {
        "id": conversation["id"],
        "created_at": conversation["created_at"],
        "title": conversation.get("title", "New Conversation"),
        "message_count": len(conversation["messages"])
    }

    # Remove existing entry if present
    index = [item for item in index if item["id"] != conversation["id"]]
    
    # Add new entry
    index.append(entry)
    
    # Sort and save
    index.sort(key=lambda x: x["created_at"], reverse=True)
    _save_index(index)


def _remove_from_index(conversation_id: str):
    """Remove an entry from the index."""
    index = _load_index()
    if index is None:
        return  # No index to remove from

    # Filter out the deleted conversation
    new_index = [item for item in index if item["id"] != conversation_id]
    
    if len(new_index) != len(index):
        _save_index(new_index)


def create_conversation(conversation_id: str) -> Dict[str, Any]:
    """
    Create a new conversation.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        New conversation dict
    """
    ensure_data_dir()

    conversation = {
        "id": conversation_id,
        "created_at": datetime.utcnow().isoformat(),
        "title": "New Conversation",
        "messages": []
    }

    # Save to file
    path = get_conversation_path(conversation_id)
    with open(path, 'w') as f:
        json.dump(conversation, f, indent=2)

    # Update index
    _update_index_entry(conversation)

    return conversation


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """
    Load a conversation from storage.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        Conversation dict or None if not found
    """
    path = get_conversation_path(conversation_id)

    if not os.path.exists(path):
        return None

    with open(path, 'r') as f:
        return json.load(f)


def save_conversation(conversation: Dict[str, Any]):
    """
    Save a conversation to storage.

    Args:
        conversation: Conversation dict to save
    """
    ensure_data_dir()

    path = get_conversation_path(conversation['id'])
    with open(path, 'w') as f:
        json.dump(conversation, f, indent=2)

    # Update index
    _update_index_entry(conversation)


def list_conversations() -> List[Dict[str, Any]]:
    """
    List all conversations (metadata only).
    Uses cached index file for O(1) performance.

    Returns:
        List of conversation metadata dicts
    """
    ensure_data_dir()

    # Try to load from index first
    index = _load_index()
    
    # If index missing or invalid, rebuild it
    if index is None:
        return rebuild_index()
        
    return index


def add_user_message(conversation_id: str, content: str):
    """
    Add a user message to a conversation.

    Args:
        conversation_id: Conversation identifier
        content: User message content
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["messages"].append({
        "role": "user",
        "content": content
    })

    save_conversation(conversation)


def add_assistant_message(
    conversation_id: str,
    stage1: List[Dict[str, Any]],
    stage2: Optional[List[Dict[str, Any]]] = None,
    stage3: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    brainstorm_turns: Optional[List[Dict[str, Any]]] = None,
    brainstorm_summaries: Optional[List[Dict[str, Any]]] = None,
    brainstorm_status: Optional[str] = None,
    brainstorm_final: Optional[Dict[str, Any]] = None,
    brainstorm_user_inputs: Optional[List[Dict[str, Any]]] = None,
):
    """
    Add an assistant message to a conversation.
    
    Supports partial execution modes where stage2 and/or stage3 may be None.
    
    Args:
        conversation_id: Conversation identifier
        stage1: List of individual model responses (always present)
        stage2: List of model rankings (None if execution_mode was 'chat_only')
        stage3: Final synthesized response (None if execution_mode was not 'full')
        metadata: Optional metadata including execution_mode, label_to_model, etc.
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    message = {
        "role": "assistant",
        "stage1": stage1,
    }
    
    if stage2 is not None:
        message["stage2"] = stage2
    if stage3 is not None:
        message["stage3"] = stage3
    if brainstorm_turns is not None:
        message["brainstorm_turns"] = brainstorm_turns
    if brainstorm_summaries is not None:
        message["brainstorm_summaries"] = brainstorm_summaries
    if brainstorm_status is not None:
        message["brainstorm_status"] = brainstorm_status
    if brainstorm_final is not None:
        message["brainstorm_final"] = brainstorm_final
    if brainstorm_user_inputs is not None:
        message["brainstorm_user_inputs"] = brainstorm_user_inputs
    if metadata:
        message["metadata"] = metadata

    conversation["messages"].append(message)

    save_conversation(conversation)


def add_error_message(conversation_id: str, error_text: str):
    """
    Add an error message to a conversation to record a failed turn.

    Args:
        conversation_id: Conversation identifier
        error_text: The error description
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    message = {
        "role": "assistant",
        "content": None,
        "error": error_text,
        "stage1": [],
        "stage2": [],
        "stage3": None
    }

    conversation["messages"].append(message)
    save_conversation(conversation)


def append_chairman_followup(conversation_id: str, user_message: str, chairman_result: Dict[str, Any]):
    """Append a chairman follow-up exchange to the last assistant message."""
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    last_assistant = next(
        (m for m in reversed(conversation["messages"]) if m.get("role") == "assistant"),
        None,
    )
    if last_assistant is None:
        raise ValueError("No assistant message found in conversation")

    entry = {
        "role_user": user_message,
        "role_chairman": chairman_result.get("response", ""),
        "model": chairman_result.get("model", ""),
        "error": chairman_result.get("error", False),
    }
    if "brainstorm_chairman_chat" not in last_assistant:
        last_assistant["brainstorm_chairman_chat"] = []
    last_assistant["brainstorm_chairman_chat"].append(entry)

    save_conversation(conversation)


def update_conversation_title(conversation_id: str, title: str):
    """
    Update the title of a conversation.

    Args:
        conversation_id: Conversation identifier
        title: New title for the conversation
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["title"] = title
    save_conversation(conversation)


def delete_conversation(conversation_id: str) -> bool:
    """
    Delete a conversation.

    Args:
        conversation_id: Conversation identifier

    Returns:
        True if deleted, False if not found
    """
    path = get_conversation_path(conversation_id)

    if not os.path.exists(path):
        return False

    os.remove(path)
    
    # Update index
    _remove_from_index(conversation_id)
    
    return True
