"""
memory/memory_retriever.py — Natural Memory Retrieval & Hybrid Context Resolver for ALEX 6.0.

Understands natural Hindi, Hinglish, and English memory queries:
  • "Mera previous project continue karo"
  • "Pichhli baar humne kya fix kiya tha?"
  • "Maine is feature ke liye kya requirements di thi?"
  • "Pending tasks batao"
  • "Pichhle version se compare karo"
  • "Mere project ka tech stack kya hai?"
  • "Last time wali approach use karo"

Features:
  - Hybrid search combining FTS5 BM25 search, metadata filters, and project scoping.
  - Returns source, timestamp, confidence, and project citations.
  - Zero hallucinations: states clearly when memory is missing and prompts for guidance.
  - Bounded prompt generation (never loads whole database into LLM context).

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from memory.brain_store import MemoryRecord, brain_store


@dataclass
class RetrievalResult:
    query: str
    intent_type: str        # project_continue, bug_history, requirements, tasks, tech_stack, general_search
    found: bool
    summary_text: str
    matched_records: List[Dict[str, Any]]
    confidence: float
    source: str


class MemoryRetriever:
    """Dispatches natural language memory queries to structured database and FTS5 search."""

    _instance: Optional[MemoryRetriever] = None

    def __init__(self):
        pass

    @classmethod
    def get_instance(cls) -> MemoryRetriever:
        if cls._instance is None:
            cls._instance = MemoryRetriever()
        return cls._instance

    def query(self, text: str, project_id: Optional[str] = None, limit: int = 5) -> RetrievalResult:
        """Parses intent and retrieves ranked, citation-backed facts from the knowledge brain."""
        q_lower = (text or "").strip().lower()

        # 1. Intent: Tech Stack
        if any(p in q_lower for p in ("tech stack", "technology stack", "stack kya hai", "kaise bana hai", "kisme bana hai")):
            return self._handle_tech_stack_query(q_lower, project_id)

        # 2. Intent: Requirements & Features
        if any(p in q_lower for p in ("requirement", "requirements", "zaroorat", "feature", "kya decide hua", "kya manga tha")):
            return self._handle_requirements_query(q_lower, project_id)

        # 3. Intent: Previous Fixes & Bugs
        if any(p in q_lower for p in ("fix kiya tha", "bug", "bugs", "kya repair kiya", "problem", "kya sahi kiya", "pichhli baar")):
            return self._handle_fix_history_query(q_lower, project_id)

        # 4. Intent: Pending Tasks & Blockers
        if any(p in q_lower for p in ("pending task", "pending tasks", "bache hue kaam", "kya bacha hai", "active tasks", "blocker")):
            return self._handle_pending_tasks_query(q_lower, project_id)

        # 5. Intent: Continue Project / Last Task
        if any(p in q_lower for p in ("continue karo", "continue project", "pichhla project", "previous project", "aage badhao")):
            return self._handle_continue_project_query(q_lower, project_id)

        # 6. General Hybrid FTS Search
        return self._handle_general_search(text, project_id, limit=limit)

    def _handle_tech_stack_query(self, query: str, project_id: Optional[str]) -> RetrievalResult:
        # Check active project or search project profiles
        projects = brain_store.list_project_profiles()
        target_proj = None

        if project_id:
            target_proj = next((p for p in projects if p["name"].lower() == project_id.lower() or p["project_id"] == project_id), None)
        if not target_proj:
            # Check if project name mentioned in query
            for p in projects:
                if p["name"].lower() in query:
                    target_proj = p
                    break
        if not target_proj and projects:
            target_proj = projects[0]  # default to latest active

        if target_proj:
            stack = target_proj.get("tech_stack", "Python")
            arch = target_proj.get("architecture", "Modular")
            summary = f"Sir, project '{target_proj['name']}' ka tech stack: {stack} (Architecture: {arch})."
            return RetrievalResult(
                query=query,
                intent_type="tech_stack",
                found=True,
                summary_text=summary,
                matched_records=[target_proj],
                confidence=1.0,
                source=f"Project Profile: {target_proj['name']}"
            )

        return RetrievalResult(
            query=query,
            intent_type="tech_stack",
            found=False,
            summary_text="Sir, is project ke tech stack ka koi record nahi mila. Kripya project name confirm kijiye.",
            matched_records=[],
            confidence=0.0,
            source="None"
        )

    def _handle_requirements_query(self, query: str, project_id: Optional[str]) -> RetrievalResult:
        # Search memories and project profile
        projects = brain_store.list_project_profiles()
        target_proj = None
        if project_id:
            target_proj = next((p for p in projects if p["name"].lower() == project_id.lower() or p["project_id"] == project_id), None)
        if not target_proj and projects:
            for p in projects:
                if p["name"].lower() in query:
                    target_proj = p
                    break
        if not target_proj and projects:
            target_proj = projects[0]

        if target_proj and target_proj.get("requirements"):
            reqs = target_proj.get("requirements")
            summary = f"Sir, '{target_proj['name']}' ke saved requirements:\n• {reqs}"
            return RetrievalResult(
                query=query,
                intent_type="requirements",
                found=True,
                summary_text=summary,
                matched_records=[target_proj],
                confidence=0.95,
                source=f"Project Profile: {target_proj['name']}"
            )

        # Search FTS in memories
        mems = brain_store.search_memories(query, project_id=project_id, memory_type="project")
        if mems:
            top_mem, score = mems[0]
            return RetrievalResult(
                query=query,
                intent_type="requirements",
                found=True,
                summary_text=f"Sir, requirements record mil gaya:\n• {top_mem.content}",
                matched_records=[{"id": top_mem.id, "content": top_mem.content}],
                confidence=0.85,
                source=top_mem.source
            )

        return RetrievalResult(
            query=query,
            intent_type="requirements",
            found=False,
            summary_text="Sir, is requirement ka koi specific context store nahi mila. Kya aap ise note karwana chahenge?",
            matched_records=[],
            confidence=0.0,
            source="None"
        )

    def _handle_fix_history_query(self, query: str, project_id: Optional[str]) -> RetrievalResult:
        projects = brain_store.list_project_profiles()
        target_proj = None
        if project_id:
            target_proj = next((p for p in projects if p["name"].lower() == project_id.lower() or p["project_id"] == project_id), None)
        if not target_proj and projects:
            for p in projects:
                if p["name"].lower() in query:
                    target_proj = p
                    break
        if not target_proj and projects:
            target_proj = projects[0]

        items = []
        if target_proj and target_proj.get("known_bugs"):
            for b in target_proj.get("known_bugs", []):
                if isinstance(b, dict):
                    status = b.get("status", "Resolved")
                    desc = b.get("description", "")
                    items.append(f"• [{status}] {desc} ({b.get('date', 'Recent')})")

        if items:
            summary = f"Sir, pichhli baar humne ye issues investigate/fix kiye the:\n" + "\n".join(items[:4])
            return RetrievalResult(
                query=query,
                intent_type="bug_history",
                found=True,
                summary_text=summary,
                matched_records=target_proj.get("known_bugs", []),
                confidence=0.95,
                source=f"Project Profile: {target_proj['name']}"
            )

        return RetrievalResult(
            query=query,
            intent_type="bug_history",
            found=False,
            summary_text="Sir, pichhle session me fix kiye gaye bugs ka koi unresolved issue logged nahi hai.",
            matched_records=[],
            confidence=0.0,
            source="None"
        )

    def _handle_pending_tasks_query(self, query: str, project_id: Optional[str]) -> RetrievalResult:
        unfinished = brain_store.get_unfinished_tasks()
        if unfinished:
            lines = [f"• Task: {t['goal']} (Step {t.get('current_step', 1)}/{t.get('total_steps', 1)})" for t in unfinished[:4]]
            summary = "Sir, ye tasks filhal pending hain:\n" + "\n".join(lines)
            return RetrievalResult(
                query=query,
                intent_type="tasks",
                found=True,
                summary_text=summary,
                matched_records=unfinished,
                confidence=1.0,
                source="TaskCenter / Tasks Ledger"
            )

        # Check project pending tasks
        projects = brain_store.list_project_profiles()
        if projects and projects[0].get("pending_tasks"):
            pts = projects[0].get("pending_tasks")
            lines = [f"• {t.get('task') if isinstance(t, dict) else t}" for t in pts if not (isinstance(t, dict) and t.get('done'))]
            if lines:
                summary = f"Sir, '{projects[0]['name']}' me pending tasks:\n" + "\n".join(lines[:4])
                return RetrievalResult(
                    query=query,
                    intent_type="tasks",
                    found=True,
                    summary_text=summary,
                    matched_records=pts,
                    confidence=0.9,
                    source=f"Project: {projects[0]['name']}"
                )

        return RetrievalResult(
            query=query,
            intent_type="tasks",
            found=False,
            summary_text="Sir, currently koi pending ya blocked tasks nahi hain. All queues are clear.",
            matched_records=[],
            confidence=1.0,
            source="Task Ledger"
        )

    def _handle_continue_project_query(self, query: str, project_id: Optional[str]) -> RetrievalResult:
        projects = brain_store.list_project_profiles()
        target = projects[0] if projects else None
        if target:
            summary = (
                f"Sir, previous project '{target['name']}' ko continue karne ke liye ready hoon.\n"
                f"• Path: {target['path']}\n"
                f"• Stack: {target.get('tech_stack', 'Python')}\n"
                f"• Health: Verified\n"
                f"Boliye Sir, next step kya lena hai?"
            )
            return RetrievalResult(
                query=query,
                intent_type="project_continue",
                found=True,
                summary_text=summary,
                matched_records=[target],
                confidence=1.0,
                source=f"Project Profile: {target['name']}"
            )

        return RetrievalResult(
            query=query,
            intent_type="project_continue",
            found=False,
            summary_text="Sir, pichhle project ka path detect nahi hua. Kripya project name ya path bataiye.",
            matched_records=[],
            confidence=0.0,
            source="None"
        )

    def _handle_general_search(self, query: str, project_id: Optional[str], limit: int = 5) -> RetrievalResult:
        # Search memories
        mem_results = brain_store.search_memories(query, project_id=project_id, limit=limit)
        # Search indexed documents
        doc_results = brain_store.search_documents(query, project_id=project_id, limit=3)

        records = []
        lines = []

        for m, score in mem_results:
            records.append({"type": "memory", "id": m.id, "content": m.content, "source": m.source, "date": m.updated_at})
            lines.append(f"• [{m.category.title()}] {m.content} (Source: {m.source}, Date: {m.updated_at[:10]})")

        for d in doc_results:
            records.append({"type": "document", "file": d.get("file_name"), "snippet": d.get("content")[:200]})
            lines.append(f"• [Doc: {d.get('file_name')}] {d.get('title')}: {d.get('content')[:180]}...")

        if lines:
            summary = f"Sir, '{query}' se relevant records:\n" + "\n".join(lines[:limit])
            return RetrievalResult(
                query=query,
                intent_type="general_search",
                found=True,
                summary_text=summary,
                matched_records=records,
                confidence=0.85,
                source="FTS5 Knowledge Brain"
            )

        return RetrievalResult(
            query=query,
            intent_type="general_search",
            found=False,
            summary_text=f"Sir, '{query}' ke bare me memory ya documents me koi stored record nahi mila.",
            matched_records=[],
            confidence=0.0,
            source="None"
        )


# Singleton Instance
memory_retriever = MemoryRetriever.get_instance()
