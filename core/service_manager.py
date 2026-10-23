"""
core/service_manager.py — Central Subsystem Coordinator & Watchdog for ALEX 3.0.

Owner: Aditya Rajak
Salutation: Sir

Coordinates:
  • ALEX Core Engine
  • Voice Pipeline (STT, TTS, Wake Word)
  • Memory & Workspace Service
  • Task & Planning Service
  • Security & Permission Firewall
  • Computer & Browser Service
  • Remote Dashboard Server
  • Hardware & System Watchdog (Lightweight monitoring without high CPU)
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

import psutil
from core.action_timeline import timeline
from core.event_bus import event_bus


@dataclass
class ServiceStatus:
    name: str
    is_running: bool
    healthy: bool
    last_heartbeat: float = field(default_factory=time.time)
    restart_count: int = 0
    details: str = "Operational"


class ServiceManager:
    _instance: Optional[ServiceManager] = None
    _lock = threading.Lock()

    def __init__(self):
        self._services: Dict[str, ServiceStatus] = {}
        self._watchdog_active = False
        self._watchdog_thread: Optional[threading.Thread] = None
        self._init_default_services()

    @classmethod
    def get_instance(cls) -> ServiceManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = ServiceManager()
            return cls._instance

    def _init_default_services(self) -> None:
        default_names = [
            "alex_core", "voice_pipeline", "memory_service", "task_planner",
            "security_firewall", "computer_control", "browser_agent", "dashboard_server"
        ]
        for name in default_names:
            self._services[name] = ServiceStatus(name=name, is_running=True, healthy=True)

    def heartbeat(self, service_name: str, healthy: bool = True, details: str = "Nominal") -> None:
        """Records a heartbeat from a worker or background loop."""
        if service_name in self._services:
            st = self._services[service_name]
            st.last_heartbeat = time.time()
            st.healthy = healthy
            st.details = details
        else:
            self._services[service_name] = ServiceStatus(
                name=service_name, is_running=True, healthy=healthy, details=details
            )

    def mark_service_status(self, service_name: str, running: bool, healthy: bool, details: str) -> None:
        if service_name in self._services:
            st = self._services[service_name]
            st.is_running = running
            st.healthy = healthy
            st.details = details
            event_bus.publish("SERVICE_STATUS_CHANGED", {"service": service_name, "running": running, "healthy": healthy})
            if not healthy or not running:
                try:
                    from core.proactive_intelligence import proactive_engine
                    proactive_engine.notify_service_down(service_name, details)
                except Exception:
                    pass

    def get_all_services(self) -> Dict[str, Dict[str, Any]]:
        return {k: asdict(v) for k, v in self._services.items()}

    def start_watchdog(self) -> None:
        """Launches lightweight watchdog monitor thread (evaluates every 15 seconds)."""
        if self._watchdog_active:
            return
        self._watchdog_active = True

        def _watchdog_loop():
            while self._watchdog_active:
                time.sleep(15)
                now = time.time()
                for name, st in list(self._services.items()):
                    # If no heartbeat for > 90 seconds on critical service
                    if st.is_running and (now - st.last_heartbeat > 90):
                        st.healthy = False
                        st.details = "Heartbeat timeout — watchdog monitoring"
                        event_bus.publish("WATCHDOG_ALERT", {"service": name, "alert": "heartbeat_timeout"})
                        try:
                            from core.proactive_intelligence import proactive_engine
                            proactive_engine.notify_service_down(name, "Heartbeat timeout (>90s)")
                        except Exception:
                            pass

        self._watchdog_thread = threading.Thread(target=_watchdog_loop, daemon=True, name="alex_watchdog")
        self._watchdog_thread.start()

    def stop_watchdog(self) -> None:
        self._watchdog_active = False


service_manager = ServiceManager.get_instance()

