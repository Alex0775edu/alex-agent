"""
memory/conflict_resolver.py — Memory Quality, Contradiction Detection & Conflict Resolution for ALEX 6.0.

Resolves conflicts between new observations and existing memories:
  1. Detects contradictions (e.g. changed preferences, updated architecture, modified rules).
  2. Applies explicit recent corrections from the owner automatically when unambiguous.
  3. Preserves historical decisions with rationale in the conflict ledger.
  4. Flags ambiguous or critical requirement changes for explicit owner confirmation.
  5. Never silently overwrites core project requirements without a trace.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from memory.brain_store import MemoryRecord, brain_store, redact_secrets


@dataclass
class ConflictItem:
    conflict_id: str
    memory_id: str
    key: str
    old_value: str
    new_value: str
    reason: str
    resolved: bool
    resolution: str
    resolved_at: Optional[str] = None


class ConflictResolver:
    """Manages contradiction detection, automated resolution rules, and human-in-the-loop dispute flags."""

    _instance: Optional[ConflictResolver] = None

    def __init__(self):
        pass

    @classmethod
    def get_instance(cls) -> ConflictResolver:
        if cls._instance is None:
            cls._instance = ConflictResolver()
        return cls._instance

    def evaluate_and_store(
        self,
        key: str,
        new_value: str,
        category: str = "notes",
        project_id: Optional[str] = None,
        source: str = "conversation",
        is_owner_explicit: bool = True
    ) -> Tuple[bool, str, Optional[MemoryRecord]]:
        """
        Evaluates a new memory candidate against existing stored facts.
        Returns: (success: bool, explanation: str, record: Optional[MemoryRecord])
        """
        clean_new = redact_secrets(new_value.strip())

        # Enforce user title rule strictly
        if key == "user_title" and clean_new in ("Aditya Sir", "aditya sir", "Sir"):
            clean_new = "Sir"

        existing = brain_store.get_memory_by_key(category, key, project_id=project_id)

        if not existing:
            # Clean insert, no contradiction
            rec = brain_store.save_memory(
                content=clean_new,
                category=category,
                key=key,
                project_id=project_id,
                source=source,
                confidence=1.0 if is_owner_explicit else 0.8
            )
            return True, f"Stored new fact: [{category}] {key} = {clean_new}", rec

        old_val = existing.content

        # Exact match
        if old_val.strip().lower() == clean_new.strip().lower():
            return True, "Fact matches existing memory; no change needed.", existing

        # Contradiction detected
        # Rule 1: Protected project requirements require confirmation unless explicit
        if category in ("requirements", "architecture") and not is_owner_explicit:
            conflict_id = f"cnf_{uuid.uuid4().hex[:8]}"
            conn = brain_store._get_connection()
            with conn:
                conn.execute("""
                    INSERT INTO conflicts (conflict_id, memory_id, key, old_value, new_value, reason, resolved, resolution, resolved_at)
                    VALUES (?, ?, ?, ?, ?, 'Project requirement contradiction detected without explicit owner command', 0, 'PENDING_OWNER_CONFIRMATION', NULL);
                """, (conflict_id, existing.id, key, old_val, clean_new))
            return False, f"Conflict detected in project requirement '{key}'. Old: '{old_val}', Proposed: '{clean_new}'. Awaiting owner confirmation.", existing

        # Rule 2: Explicit correction from owner takes precedence
        if is_owner_explicit:
            rec = brain_store.save_memory(
                content=clean_new,
                category=category,
                key=key,
                project_id=project_id,
                source=f"owner_correction ({source})",
                confidence=1.0
            )
            return True, f"Updated '{key}' from '{old_val}' to '{clean_new}' based on owner's instruction.", rec

        # Rule 3: Lower confidence observation conflicting with established fact
        return False, f"New observation '{clean_new}' contradicts established fact '{old_val}'. Kept original.", existing

    def list_unresolved_conflicts(self) -> List[Dict[str, Any]]:
        conn = brain_store._get_connection()
        cur = conn.execute("""
            SELECT * FROM conflicts WHERE resolved = 0 ORDER BY rowid DESC;
        """)
        return [dict(r) for r in cur.fetchall()]

    def resolve_conflict(self, conflict_id: str, choice: str, owner_note: str = "") -> bool:
        """
        Manually resolves a flagged conflict.
        choice: 'ACCEPT_NEW' or 'KEEP_OLD'
        """
        conn = brain_store._get_connection()
        cur = conn.execute("SELECT * FROM conflicts WHERE conflict_id = ?;", (conflict_id,))
        row = cur.fetchone()
        if not row:
            return False

        now = datetime.now().isoformat()
        if choice == "ACCEPT_NEW":
            mem_id = row["memory_id"]
            new_val = row["new_value"]
            with conn:
                conn.execute("""
                    UPDATE memories SET content = ?, updated_at = ? WHERE id = ?;
                """, (new_val, now, mem_id))
                conn.execute("DELETE FROM memories_fts WHERE id = ?;", (mem_id,))
                conn.execute("""
                    INSERT INTO memories_fts (id, content, key, category, project_id)
                    SELECT id, content, key, category, project_id FROM memories WHERE id = ?;
                """, (mem_id,))
                conn.execute("""
                    UPDATE conflicts
                    SET resolved = 1, resolution = ?, resolved_at = ?
                    WHERE conflict_id = ?;
                """, (f"Accepted new: {owner_note or 'Owner approved'}", now, conflict_id))
            return True
        else:
            with conn:
                conn.execute("""
                    UPDATE conflicts
                    SET resolved = 1, resolution = ?, resolved_at = ?
                    WHERE conflict_id = ?;
                """, (f"Kept old: {owner_note or 'Owner rejected change'}", now, conflict_id))
            return True


# Singleton Instance
conflict_resolver = ConflictResolver.get_instance()

