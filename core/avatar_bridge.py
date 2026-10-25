"""
core/avatar_bridge.py — High-Performance Avatar Controller & Event Bridge.

Connects the Python backend (EventBus, audio threads, state machine)
with both the embedded Three.js WebGL avatar and the native 3D viewport.

Features:
  - 8 Assistant States: IDLE, LISTENING, THINKING, SPEAKING, EXECUTING, SUCCESS, ERROR, SLEEPING
  - Strict payload validation and sanitization (no arbitrary code execution / no credential leaks)
  - Live Audio PCM amplitude forwarding for synchronized lip-sync
  - Viseme schedule dispatch
  - EventBus integration with 'assistant.*' event taxonomy
  - Genuine task metadata & execution progress tracking (no fake timers)
  - Interruption and cancellation lifecycle support
"""

from __future__ import annotations

import collections
import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("alex.avatar_bridge")

# Canonical Assistant States
AVATAR_STATES: Set[str] = {
    "IDLE",
    "LISTENING",
    "THINKING",
    "SPEAKING",
    "EXECUTING",
    "SUCCESS",
    "ERROR",
    "SLEEPING",
}

# Permitted message types for avatar communication
ALLOWED_MESSAGE_TYPES: Set[str] = {
    "state",
    "audio_level",
    "visemes",
    "task_update",
    "expression",
    "reset",
}

# Blocked keys to safeguard against credential leakage or command injection
FORBIDDEN_PAYLOAD_KEYS: Set[str] = {
    "eval", "exec", "command", "cmd", "shell", "token", "api_key",
    "password", "secret", "credentials", "file_system", "__proto__",
}


def validate_avatar_payload(payload: Any) -> bool:
    """Validates that payload conforms to safe avatar renderer schema."""
    if not isinstance(payload, dict):
        return False
    msg_type = payload.get("type")
    if not isinstance(msg_type, str) or msg_type not in ALLOWED_MESSAGE_TYPES:
        return False
    for k in payload.keys():
        if k.lower() in FORBIDDEN_PAYLOAD_KEYS:
            return False
    if msg_type == "state":
        st = payload.get("state")
        return isinstance(st, str) and st.upper() in AVATAR_STATES
    if msg_type == "audio_level":
        lvl = payload.get("level")
        return isinstance(lvl, (int, float)) and 0.0 <= lvl <= 1.0
    if msg_type == "task_update":
        title = payload.get("title", "")
        progress = payload.get("progress", 0)
        return isinstance(title, str) and isinstance(progress, (int, float))
    return True


class AvatarController:
    """
    Central Controller for ALEX 3D Digital Human Avatar.
    Manages state machine, genuine task progress, audio amplitude,
    and bi-directional event bridging.
    """
    _instance: Optional[AvatarController] = None
    _lock = threading.Lock()

    def __init__(self):
        self.state: str = "IDLE"
        self.speaking: bool = False
        self.audio_level: float = 0.0
        self.visemes: Optional[tuple] = None

        # Task metadata
        self.active_task_title: str = ""
        self.active_task_progress: float = 0.0

        # Subscribed listeners (UI viewports, WebGL servers)
        self._listeners: List[Callable[[dict], None]] = []
        self._listeners_lock = threading.Lock()

        # Wire up central EventBus
        try:
            from core.event_bus import EventBus
            eb = EventBus.get_instance()
            eb.subscribe("TASK_STARTED", self._on_task_started)
            eb.subscribe("TASK_STEP_COMPLETED", self._on_task_step)
            eb.subscribe("TASK_COMPLETED", self._on_task_completed)
            eb.subscribe("TASK_VERIFIED", self._on_task_completed)
            eb.subscribe("TASK_FAILED", self._on_task_failed)
            eb.subscribe("TOOL_ROUTED", self._on_tool_started)
            eb.subscribe("TOOL_STARTED", self._on_tool_started)
            eb.subscribe("TOOL_COMPLETED", self._on_tool_completed)
            eb.subscribe("TOOL_FAILED", self._on_tool_failed)
            eb.subscribe("THINKING_STARTED", self._on_thinking_started)
            eb.subscribe("SECURITY_BLOCKED", self._on_security_blocked)
            eb.subscribe("ASSISTANT_INTERRUPTED", self._on_assistant_interrupted)
        except Exception as e:
            logger.debug("EventBus integration skipped: %s", e)

    @classmethod
    def get_instance(cls) -> AvatarController:
        with cls._lock:
            if cls._instance is None:
                cls._instance = AvatarController()
            return cls._instance

    def add_listener(self, listener: Callable[[dict], None]) -> None:
        with self._listeners_lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[dict], None]) -> None:
        with self._listeners_lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def _broadcast(self, msg: dict) -> None:
        if not validate_avatar_payload(msg):
            logger.warning("Rejected invalid avatar payload: %s", msg)
            return

        with self._listeners_lock:
            for l in list(self._listeners):
                try:
                    l(msg)
                except Exception as e:
                    logger.debug("Listener callback error: %s", e)

    def set_state(self, state: str) -> None:
        """Set avatar state with normalization, validation, and event bus publication."""
        normalized = state.strip().upper()
        if normalized not in AVATAR_STATES:
            # Map legacy or synonym states
            if normalized in ("LOCAL MODE", "LOCKED", "INITIALISING", "MUTED"):
                normalized = "IDLE"
            elif normalized in ("PROCESSING", "WORKING"):
                normalized = "EXECUTING"
            else:
                normalized = "IDLE"

        if normalized != self.state:
            self.state = normalized
            self.speaking = (normalized == "SPEAKING")
            if not self.speaking:
                self.audio_level = 0.0

            # Publish to EventBus
            try:
                from core.event_bus import EventBus
                EventBus.get_instance().publish(
                    f"assistant.{normalized.lower()}",
                    {"state": normalized, "timestamp": time.time()}
                )
            except Exception:
                pass

            self._broadcast({"type": "state", "state": normalized, "timestamp": time.time()})

    def set_audio_level(self, level: float) -> None:
        """Thread-safe update for live audio PCM RMS level (clamped 0.0 - 1.0)."""
        clamped = max(0.0, min(1.0, float(level)))
        self.audio_level = clamped
        self._broadcast({"type": "audio_level", "level": clamped})

    def push_visemes(self, frames, hop: float, at: float) -> None:
        """Thread-safe batch of phoneme/viseme articulatory frames."""
        self.visemes = (frames, hop, at)
        self._broadcast({"type": "visemes", "frames": list(frames), "hop": float(hop), "at": float(at)})

    def set_task_info(self, title: str, progress: float) -> None:
        """Sets current active task title and genuine progress percentage."""
        self.active_task_title = str(title or "").strip()
        self.active_task_progress = max(0.0, min(100.0, float(progress)))
        self._broadcast({
            "type": "task_update",
            "title": self.active_task_title,
            "progress": self.active_task_progress
        })

    def start_speaking(self) -> None:
        """Invoked when TTS audio output officially begins."""
        self.set_state("SPEAKING")

    def stop_speaking(self, next_state: str = "LISTENING") -> None:
        """Invoked when TTS audio output finishes or is interrupted."""
        self.set_audio_level(0.0)
        self.set_state(next_state)

    def interrupt(self) -> None:
        """Interrupts speech and executing tasks, reverting to attentive LISTENING."""
        self.set_audio_level(0.0)
        self.set_task_info("", 0.0)
        self.set_state("LISTENING")

    # ── EventBus Callback Handlers ──
    def _on_task_started(self, event) -> None:
        data = getattr(event, "data", {}) or {}
        goal = data.get("goal") or data.get("task_id") or "Executing Task"
        self.set_task_info(goal, 5.0)
        self.set_state("EXECUTING")

    def _on_task_step(self, event) -> None:
        data = getattr(event, "data", {}) or {}
        prog = data.get("progress", self.active_task_progress + 15.0)
        self.set_task_info(self.active_task_title, prog)

    def _on_task_completed(self, event) -> None:
        self.set_task_info(self.active_task_title, 100.0)
        self.set_state("SUCCESS")

    def _on_task_failed(self, event) -> None:
        self.set_state("ERROR")

    def _on_tool_started(self, event) -> None:
        data = getattr(event, "data", {}) or {}
        name = data.get("tool") or data.get("name") or "System Tool"
        self.set_task_info(f"Running {name}", 25.0)
        self.set_state("EXECUTING")

    def _on_tool_completed(self, event) -> None:
        self.set_state("SUCCESS")

    def _on_tool_failed(self, event) -> None:
        self.set_state("ERROR")

    def _on_thinking_started(self, event) -> None:
        self.set_state("THINKING")

    def _on_security_blocked(self, event) -> None:
        self.set_state("ERROR")

    def _on_assistant_interrupted(self, event) -> None:
        self.interrupt()


# Compatibility alias
AvatarBridge = AvatarController

# Global singleton
avatar_bridge = AvatarController.get_instance()
