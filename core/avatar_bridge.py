"""
core/avatar_bridge.py — High-Performance Avatar Controller & Event Bridge.

Connects the Python backend (EventBus, audio threads, state machine)
with both the embedded Three.js WebGL avatar and the native 3D viewport.

Features:
  - 8 Assistant States: IDLE, LISTENING, THINKING, SPEAKING, EXECUTING, SUCCESS, ERROR, SLEEPING
  - Live Audio PCM amplitude forwarding for synchronized lip-sync
  - Viseme schedule dispatch
  - EventBus integration with 'assistant.*' event taxonomy
  - Thread-safe state dispatch
"""

from __future__ import annotations

import collections
import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("alex.avatar_bridge")

# Avatar valid states
AVATAR_STATES = {
    "IDLE",
    "LISTENING",
    "THINKING",
    "SPEAKING",
    "EXECUTING",
    "SUCCESS",
    "ERROR",
    "SLEEPING",
}


class AvatarBridge:
    _instance: Optional[AvatarBridge] = None
    _lock = threading.Lock()

    def __init__(self):
        self.state: str = "IDLE"
        self.speaking: bool = False
        self.audio_level: float = 0.0
        self.visemes: Optional[tuple] = None
        
        self._listeners: List[Callable[[dict], None]] = []
        self._listeners_lock = threading.Lock()
        
        # Subscribe to central EventBus
        try:
            from core.event_bus import EventBus
            eb = EventBus.get_instance()
            eb.subscribe("TASK_STARTED", self._on_task_started)
            eb.subscribe("TASK_COMPLETED", self._on_task_completed)
            eb.subscribe("TASK_VERIFIED", self._on_task_completed)
            eb.subscribe("THINKING_STARTED", self._on_thinking_started)
            eb.subscribe("TOOL_COMPLETED", self._on_tool_completed)
            eb.subscribe("SECURITY_BLOCKED", self._on_security_blocked)
        except Exception as e:
            logger.debug("EventBus integration skipped: %s", e)

    @classmethod
    def get_instance(cls) -> AvatarBridge:
        with cls._lock:
            if cls._instance is None:
                cls._instance = AvatarBridge()
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
        with self._listeners_lock:
            for l in list(self._listeners):
                try:
                    l(msg)
                except Exception:
                    pass

    def set_state(self, state: str) -> None:
        """Set avatar state with validation and backend event publication."""
        normalized = state.strip().upper()
        if normalized not in AVATAR_STATES:
            # Map legacy states
            if normalized in ("LOCAL MODE", "LOCKED", "INITIALISING"):
                normalized = "IDLE"
            elif normalized in ("PROCESSING",):
                normalized = "EXECUTING"
            else:
                normalized = "IDLE"

        if normalized != self.state:
            self.state = normalized
            self.speaking = (normalized == "SPEAKING")
            
            # Publish to EventBus
            try:
                from core.event_bus import EventBus
                EventBus.get_instance().publish(
                    f"assistant.{normalized.lower()}",
                    {"state": normalized, "timestamp": time.time()}
                )
            except Exception:
                pass
                
            self._broadcast({"type": "state", "state": normalized})

    def set_audio_level(self, level: float) -> None:
        """Thread-safe update for live audio PCM RMS level (0.0 - 1.0)."""
        self.audio_level = max(0.0, min(1.0, float(level)))
        self._broadcast({"type": "audio_level", "level": self.audio_level})

    def push_visemes(self, frames, hop: float, at: float) -> None:
        """Thread-safe batch of phoneme/viseme articulatory frames."""
        self.visemes = (frames, hop, at)
        self._broadcast({"type": "visemes", "frames": frames, "hop": hop, "at": at})

    # EventBus Callbacks
    def _on_task_started(self, event) -> None:
        self.set_state("EXECUTING")

    def _on_task_completed(self, event) -> None:
        self.set_state("SUCCESS")

    def _on_thinking_started(self, event) -> None:
        self.set_state("THINKING")

    def _on_tool_completed(self, event) -> None:
        self.set_state("SUCCESS")

    def _on_security_blocked(self, event) -> None:
        self.set_state("ERROR")


# Global singleton
avatar_bridge = AvatarBridge.get_instance()
