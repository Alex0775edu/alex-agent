"""
actions/knowledge_brain.py — Central Autonomous Knowledge Brain & Memory Action for ALEX 6.0.

Provides autonomous operations for:
  • Natural queries across 6-layer memory and indexed documents
  • Document indexing and re-indexing
  • Memory CRUD (remember, search, forget)
  • Project profile management (create, switch, decisions)
  • Task continuity checkpoints & recovery

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.project_manager import project_manager
from core.security import OWNER_ADDRESS
from core.task_center import task_center
from memory.brain_store import brain_store
from memory.document_indexer import document_indexer
from memory.memory_retriever import memory_retriever


def handle_knowledge_brain(parameters: dict, **kwargs) -> str:
    """Dispatches knowledge brain actions."""
    action = parameters.get("action", "query").lower()
    query_text = parameters.get("query", "")
    project_id = parameters.get("project_id")

    if action == "query":
        res = memory_retriever.query(query_text, project_id=project_id)
        return res.summary_text

    elif action == "index_document":
        file_path = parameters.get("file_path", "")
        if not file_path:
            return f"{OWNER_ADDRESS}, please specify a valid file path to index."
        res = document_indexer.index_file(file_path, project_id=project_id)
        return f"{OWNER_ADDRESS}, document indexing result: {res.get('message', res.get('status'))}"

    elif action == "index_directory":
        dir_path = parameters.get("directory_path", "")
        if not dir_path:
            return f"{OWNER_ADDRESS}, please specify a valid directory path to index."
        res = document_indexer.index_directory(dir_path, project_id=project_id)
        return f"{OWNER_ADDRESS}, indexing completed for {res.get('directory')}: {res.get('indexed_files')} files indexed, {res.get('unchanged_files')} unchanged."

    elif action == "save_memory":
        key = parameters.get("key")
        content = parameters.get("content", query_text)
        category = parameters.get("category", "notes")
        rec = brain_store.save_memory(
            content=content,
            category=category,
            key=key,
            project_id=project_id,
            source="autonomous_agent"
        )
        return f"{OWNER_ADDRESS}, fact saved to [{category}]: {rec.content}"

    elif action == "record_decision":
        decision = parameters.get("decision", "")
        reason = parameters.get("reason", "")
        if not decision:
            return f"{OWNER_ADDRESS}, decision content cannot be empty."
        return project_manager.add_decision(decision, reason, project_name=project_id)

    elif action == "task_recovery":
        rec = task_center.recover_unfinished_tasks()
        return rec.get("summary", "")

    elif action == "stats":
        stats = brain_store.get_brain_stats()
        return (
            f"{OWNER_ADDRESS}, Knowledge Brain statistics:\n"
            f"• Memories: {stats.get('memories', 0)}\n"
            f"• Projects: {stats.get('projects', 0)}\n"
            f"• Indexed Documents: {stats.get('documents', 0)} ({stats.get('document_chunks', 0)} chunks)\n"
            f"• Active Tasks: {stats.get('tasks', 0)}"
        )

    return f"{OWNER_ADDRESS}, unknown knowledge brain action: '{action}'."


TOOL = {
    "name": "knowledge_brain",
    "description": (
        "Query or operate ALEX's 6-layer memory, project profiles, and indexed documents. "
        "Supports natural queries, document indexing, fact saving, architectural decisions, and task recovery."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action: 'query', 'index_document', 'index_directory', 'save_memory', 'record_decision', 'task_recovery', 'stats'",
            },
            "query": {
                "type": "STRING",
                "description": "Natural language query or fact to search/retrieve."
            },
            "project_id": {
                "type": "STRING",
                "description": "Optional project name to scope memory or indexing to."
            },
            "file_path": {
                "type": "STRING",
                "description": "File path when indexing a specific document."
            },
            "directory_path": {
                "type": "STRING",
                "description": "Directory path when indexing a whole project workspace."
            },
            "decision": {
                "type": "STRING",
                "description": "Architectural or design decision text."
            },
            "reason": {
                "type": "STRING",
                "description": "Rationale or reason for the decision."
            }
        },
        "required": ["action"]
    },
    "handler": handle_knowledge_brain
}

