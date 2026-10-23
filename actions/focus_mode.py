"""
actions/focus_mode.py — Focus Mode Engine for ALEX 3.0.

Commands:
  • "Alex, 2 hours Focus Mode."
  • "Alex, start 45 minutes focus."
  • "Check focus status."

Suppresses proactive notifications, starts a quiet countdown, and tracks task goal.
Owner: Aditya Rajak
Salutation: Aditya Sir
"""

from __future__ import annotations

import time
from typing import Optional
from core.action_timeline import timeline
from core.security import OWNER_ADDRESS


class FocusModeManager:
    _instance: Optional[FocusModeManager] = None

    def __init__(self):
        self._active: bool = False
        self._start_time: float = 0.0
        self._duration_seconds: float = 0.0
        self._goal: str = ""

    @classmethod
    def get_instance(cls) -> FocusModeManager:
        if cls._instance is None:
            cls._instance = FocusModeManager()
        return cls._instance

    def start_focus(self, minutes: int = 60, goal: str = "Deep Work") -> str:
        self._active = True
        self._duration_seconds = float(minutes * 60)
        self._start_time = time.monotonic()
        self._goal = goal or "Deep Work"

        timeline.record("FOCUS", f"Focus Mode Started: {minutes} mins", f"Goal: {self._goal}", status="SUCCESS")

        return (
            f"{OWNER_ADDRESS}, {minutes} minute ka Focus Mode activate kar diya hai. "
            f"Goal: '{self._goal}'. Main non-critical alerts suppress rakhunga taaki aap concentrate kar sakein."
        )

    def stop_focus(self) -> str:
        if not self._active:
            return f"{OWNER_ADDRESS}, koi active Focus Mode session running nahi hai."
        elapsed = round((time.monotonic() - self._start_time) / 60.0, 1)
        self._active = False
        timeline.record("FOCUS", "Focus Mode Ended", f"Completed {elapsed} mins.", status="SUCCESS")
        return f"{OWNER_ADDRESS}, Focus Mode session complete hua ({elapsed} minutes spent on '{self._goal}')."

    def get_status(self) -> str:
        if not self._active:
            return f"{OWNER_ADDRESS}, Focus Mode currently inactive hai."
        elapsed_sec = time.monotonic() - self._start_time
        remaining_sec = max(0.0, self._duration_seconds - elapsed_sec)
        rem_min = round(remaining_sec / 60.0, 1)
        return f"{OWNER_ADDRESS}, Focus Mode ACTIVE hai. Target: '{self._goal}'. Remaining time: {rem_min} minutes."


focus_manager = FocusModeManager.get_instance()


def manage_focus_mode(action: str = "start", duration_minutes: int = 60, goal: str = "Deep Work") -> str:
    act = action.lower().strip()
    if act == "stop":
        return focus_manager.stop_focus()
    elif act == "status":
        return focus_manager.get_status()
    else:
        return focus_manager.start_focus(minutes=duration_minutes, goal=goal)


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "focus_mode",
    "description": "Starts, stops, or checks Focus Mode sessions with quiet timers and goal tracking for Aditya Sir.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action: 'start', 'stop', or 'status' (default: 'start')"
            },
            "duration_minutes": {
                "type": "INTEGER",
                "description": "Focus duration in minutes (default: 60)"
            },
            "goal": {
                "type": "STRING",
                "description": "Task or study goal for this focus session"
            }
        },
        "required": []
    },
    "handler": manage_focus_mode,
}

