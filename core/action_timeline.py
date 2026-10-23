"""
core/action_timeline.py — Real-time Searchable Action Timeline & Audit Trail for ALEX 3.0.

Provides an immutable chronological record of all significant operations:
  • User requests & parsed intents
  • Actions taken & tools executed
  • Permission decisions (SAFE, CONFIRM, CRITICAL, BLOCKED)
  • Verification status & outcomes
  • Errors & bounded recovery attempts
  • Automatic secret redaction for sensitive tokens & credentials

Owner: Aditya Rajak
Salutation: Sir
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
TIMELINE_FILE = BASE_DIR / "memory" / "action_timeline.json"
MAX_MEMORY_EVENTS = 500


@dataclass
class TimelineEvent:
    timestamp: str                         # e.g. "2026-10-10 10:30:15"
    time_short: str                        # e.g. "10:30"
    event_type: str                        # WAKE, AUTH, INTENT, EXEC, TOOL, VERIFY, RECOVER, LOCK, STOP, ALERT, TASK
    title: str                             # Short summary
    details: str                           # Detailed logs or explanation
    status: str = "SUCCESS"                # SUCCESS, FAILED, BLOCKED, WARNING, INFO
    source: str = "ALEX Core"
    latency_ms: Optional[float] = None
    user_request: str = ""
    action_taken: str = ""
    tool_used: str = ""
    permission_decision: str = "SAFE"      # SAFE, CONFIRMED, CRITICAL, BLOCKED
    result: str = ""
    verification_status: str = "VERIFIED"  # VERIFIED, FAILED, PENDING, SKIPPED
    errors: List[str] = field(default_factory=list)
    recovery_attempts: int = 0


class ActionTimeline:
    """Thread-safe persistent Action Timeline & Security Audit Trail."""

    _instance: Optional[ActionTimeline] = None
    _lock = threading.Lock()

    def __init__(self):
        self._events: List[TimelineEvent] = []
        self._file_lock = threading.Lock()
        self._load()

    @classmethod
    def get_instance(cls) -> ActionTimeline:
        with cls._lock:
            if cls._instance is None:
                cls._instance = ActionTimeline()
            return cls._instance

    def _load(self) -> None:
        if TIMELINE_FILE.exists():
            try:
                data = json.loads(TIMELINE_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    loaded = []
                    for item in data[-MAX_MEMORY_EVENTS:]:
                        if isinstance(item, dict):
                            # Filter keys matching dataclass fields for safety
                            fields = TimelineEvent.__dataclass_fields__.keys()
                            filtered = {k: v for k, v in item.items() if k in fields}
                            loaded.append(TimelineEvent(**filtered))
                    self._events = loaded
            except Exception:
                self._events = []

    def _persist(self) -> None:
        with self._file_lock:
            try:
                TIMELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
                raw = [asdict(ev) for ev in self._events[-MAX_MEMORY_EVENTS:]]
                TIMELINE_FILE.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass

    def record(
        self,
        event_type: str,
        title: str,
        details: str = "",
        status: str = "SUCCESS",
        source: str = "ALEX Core",
        latency_ms: Optional[float] = None,
        user_request: str = "",
        action_taken: str = "",
        tool_used: str = "",
        permission_decision: str = "SAFE",
        result: str = "",
        verification_status: str = "VERIFIED",
        errors: Optional[List[str]] = None,
        recovery_attempts: int = 0
    ) -> TimelineEvent:
        """
        Record a new event with automatic secret redaction.
        """
        now = time.localtime()
        ts_full = time.strftime("%Y-%m-%d %H:%M:%S", now)
        ts_short = time.strftime("%H:%M:%S", now)

        # Redact secrets
        try:
            from core.security import security_manager
            safe_title = security_manager.redact_secrets(title)
            safe_details = security_manager.redact_secrets(details)
            safe_req = security_manager.redact_secrets(user_request)
            safe_action = security_manager.redact_secrets(action_taken or title)
            safe_res = security_manager.redact_secrets(result)
            safe_errors = [security_manager.redact_secrets(err) for err in (errors or [])]
        except Exception:
            safe_title, safe_details = title, details
            safe_req = user_request
            safe_action = action_taken or title
            safe_res = result
            safe_errors = list(errors or [])

        ev = TimelineEvent(
            timestamp=ts_full,
            time_short=ts_short,
            event_type=event_type.upper(),
            title=safe_title,
            details=safe_details,
            status=status.upper(),
            source=source,
            latency_ms=latency_ms,
            user_request=safe_req,
            action_taken=safe_action,
            tool_used=tool_used,
            permission_decision=permission_decision.upper(),
            result=safe_res,
            verification_status=verification_status.upper(),
            errors=safe_errors,
            recovery_attempts=recovery_attempts
        )

        with self._lock:
            self._events.append(ev)
            if len(self._events) > MAX_MEMORY_EVENTS:
                self._events = self._events[-MAX_MEMORY_EVENTS:]

        threading.Thread(target=self._persist, daemon=True).start()
        return ev

    def search_events(
        self,
        query: Optional[str] = None,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[TimelineEvent]:
        """Search and filter timeline events."""
        with self._lock:
            results = list(self._events)

        if event_type:
            et = event_type.upper().strip()
            results = [e for e in results if e.event_type == et]

        if status:
            st = status.upper().strip()
            results = [e for e in results if e.status == st]

        if query:
            q = query.lower().strip()
            results = [
                e for e in results
                if q in e.title.lower() or q in e.details.lower()
                or q in e.action_taken.lower() or q in e.user_request.lower()
                or q in e.tool_used.lower()
            ]

        return results[-limit:]

    def get_recent(self, limit: int = 15) -> List[TimelineEvent]:
        """Return the most recent events."""
        with self._lock:
            return list(self._events[-limit:])

    def format_timeline(self, limit: int = 10) -> str:
        """Format recent timeline events for UI display or voice summary."""
        owner_addr = "Sir"
        try:
            from core.security import OWNER_ADDRESS
            owner_addr = OWNER_ADDRESS
        except Exception:
            pass

        events = self.get_recent(limit)
        if not events:
            return f"{owner_addr}, abhi tak koi recent timeline activity record nahi hui hai."

        lines = ["── ALEX 3.0 ACTION TIMELINE ──"]
        for ev in events:
            icon = "✓" if ev.status == "SUCCESS" else ("⚠" if ev.status == "WARNING" else ("✗" if ev.status in ("FAILED", "BLOCKED") else "ℹ"))
            tool_info = f" [{ev.tool_used}]" if ev.tool_used else ""
            lines.append(f"[{ev.time_short}] {icon} {ev.event_type}{tool_info}: {ev.title} — {ev.details}")
        return "\n".join(lines)

    def clear(self) -> None:
        """Clear timeline history."""
        with self._lock:
            self._events = []
        self._persist()

    def clear_history(self) -> str:
        """User-accessible clear method with confirmation response."""
        owner_addr = "Sir"
        try:
            from core.security import OWNER_ADDRESS
            owner_addr = OWNER_ADDRESS
        except Exception:
            pass
        self.clear()
        return f"{owner_addr}, Action Timeline history completely clear kar di gayi hai."


# Global accessor
timeline = ActionTimeline.get_instance()
