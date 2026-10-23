"""
core/event_bus.py — Central Asynchronous / Synchronous Event Bus for ALEX 3.0.

Owner: Aditya Rajak
Salutation: Aditya Sir

Decouples internal modules and coordinates reactive state:
  • IDENTITY_VERIFIED, OWNER_AUTHENTICATED
  • TASK_CREATED, TASK_STARTED, TASK_STEP_COMPLETED, TASK_VERIFIED, TASK_FAILED
  • TOOL_ROUTED, TOOL_EXECUTED
  • SYSTEM_METRIC_UPDATE, NETWORK_STATE_CHANGED
  • RECOVERY_TRIGGERED, WATCHDOG_ALERT
"""

from __future__ import annotations

import collections
import inspect
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Event:
    event_type: str
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = "SYSTEM"
    timestamp: float = field(default_factory=time.time)


class EventBus:
    _instance: Optional[EventBus] = None
    _lock = threading.Lock()

    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Event], Any]]] = collections.defaultdict(list)
        self._event_history: collections.deque = collections.deque(maxlen=200)
        self._sub_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> EventBus:
        with cls._lock:
            if cls._instance is None:
                cls._instance = EventBus()
            return cls._instance

    def subscribe(self, event_type: str, handler: Callable[[Event], Any]) -> None:
        """Subscribe a callable to an event type or '*' for all events."""
        with self._sub_lock:
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable[[Event], Any]) -> None:
        with self._sub_lock:
            if handler in self._subscribers[event_type]:
                self._subscribers[event_type].remove(handler)

    def publish(self, event_type: str, data: Optional[Dict[str, Any]] = None, source: str = "CORE") -> Event:
        """Publishes an event to all registered listeners."""
        evt = Event(event_type=event_type, data=data or {}, source=source)
        self._event_history.append(evt)

        # Notify specific and wildcard subscribers safely
        handlers = []
        with self._sub_lock:
            handlers.extend(self._subscribers.get(event_type, []))
            handlers.extend(self._subscribers.get("*", []))

        for h in handlers:
            try:
                h(evt)
            except Exception as e:
                print(f"[EventBus] Handler error for {event_type}: {e}")

        return evt

    def get_history(self, limit: int = 50, filter_type: Optional[str] = None) -> List[Event]:
        events = list(self._event_history)
        if filter_type:
            events = [e for e in events if e.event_type == filter_type]
        return events[-limit:]


event_bus = EventBus.get_instance()

