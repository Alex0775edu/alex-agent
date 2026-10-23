"""
core/privacy_manager.py — Screen Privacy, Sensitive Window Protection & Sensor Control for ALEX.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX

Core Principles:
  • Screen capture is strictly gated: NO secret background recording.
  • Sensitive windows (passwords, banks, private vaults) are blocked automatically.
  • Instant pause/stop controls available for all sensors.
  • Strict zero-leakage policy: Screenshots never transmitted externally without explicit authorization.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
PRIVACY_FILE = CONFIG_DIR / "privacy_settings.json"

DEFAULT_SENSITIVE_PATTERNS = [
    r"1password",
    r"bitwarden",
    r"keepass",
    r"lastpass",
    r"credential",
    r"authenticator",
    r"password manager",
    r"bank",
    r"banking",
    r"netbanking",
    r"paypal",
    r"credit card",
    r"incognito",
    r"inprivate",
    r"private browsing",
    r"private window",
    r"crypto",
    r"binance",
    r"metamask",
    r"ledger live",
    r"keychain"
]


@dataclass
class PrivacyState:
    screen_capture_allowed: bool = True
    camera_allowed: bool = True
    microphone_allowed: bool = True
    recording_allowed: bool = False
    remote_access_allowed: bool = False
    is_paused: bool = False
    screen_history_retention_minutes: int = 15
    sensitive_patterns: List[str] = field(default_factory=lambda: list(DEFAULT_SENSITIVE_PATTERNS))


class PrivacyManager:
    """Thread-safe Screen Privacy and Device Sensor Access Controller."""

    _instance: Optional[PrivacyManager] = None
    _lock = threading.RLock()

    def __init__(self):
        self._state = PrivacyState()
        self._compiled_patterns: List[re.Pattern] = []
        self._load()
        self._compile_patterns()

    @classmethod
    def get_instance(cls) -> PrivacyManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = PrivacyManager()
            return cls._instance

    def _compile_patterns(self) -> None:
        self._compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self._state.sensitive_patterns
        ]

    def _load(self) -> None:
        if PRIVACY_FILE.exists():
            try:
                data = json.loads(PRIVACY_FILE.read_text(encoding="utf-8"))
                self._state.screen_capture_allowed = data.get("screen", True)
                self._state.camera_allowed = data.get("camera", True)
                self._state.microphone_allowed = data.get("microphone", True)
                self._state.recording_allowed = data.get("recording", False)
                self._state.remote_access_allowed = data.get("remote_access", False)
                self._state.screen_history_retention_minutes = data.get("retention_minutes", 15)
                if "sensitive_patterns" in data:
                    self._state.sensitive_patterns = data["sensitive_patterns"]
            except Exception:
                pass

    def _persist(self) -> None:
        try:
            PRIVACY_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "screen": self._state.screen_capture_allowed,
                "camera": self._state.camera_allowed,
                "microphone": self._state.microphone_allowed,
                "recording": self._state.recording_allowed,
                "remote_access": self._state.remote_access_allowed,
                "retention_minutes": self._state.screen_history_retention_minutes,
                "sensitive_patterns": self._state.sensitive_patterns,
                "is_paused": self._state.is_paused,
                "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            PRIVACY_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ── Permission Queries ───────────────────────────────────────────────────

    def is_screen_capture_allowed(self) -> bool:
        with self._lock:
            return self._state.screen_capture_allowed and not self._state.is_paused

    def is_camera_allowed(self) -> bool:
        with self._lock:
            return self._state.camera_allowed and not self._state.is_paused

    def is_microphone_allowed(self) -> bool:
        with self._lock:
            return self._state.microphone_allowed and not self._state.is_paused

    def is_recording_allowed(self) -> bool:
        with self._lock:
            return self._state.recording_allowed and not self._state.is_paused

    def is_remote_access_allowed(self) -> bool:
        with self._lock:
            return self._state.remote_access_allowed and not self._state.is_paused

    def is_paused(self) -> bool:
        with self._lock:
            return self._state.is_paused

    def is_window_sensitive(self, window_title: str) -> bool:
        """Determines if an active window contains sensitive private info."""
        if not window_title:
            return False
        title_norm = window_title.strip()
        with self._lock:
            for pat in self._compiled_patterns:
                if pat.search(title_norm):
                    return True
        return False

    # ── Controls ─────────────────────────────────────────────────────────────

    def pause_vision(self) -> str:
        with self._lock:
            self._state.is_paused = True
            self._persist()
        return "Sir, screen capture aur computer vision temporarily pause kar diya gaya hai."

    def resume_vision(self) -> str:
        with self._lock:
            self._state.is_paused = False
            self._persist()
        return "Sir, screen capture aur computer vision resume ho gaya hai."

    def emergency_stop(self) -> str:
        """Instantly stops all vision, recording, and active automation."""
        with self._lock:
            self._state.is_paused = True
            self._state.recording_allowed = False
            self._state.remote_access_allowed = False
            self._persist()
        return "Sir, Emergency Stop triggered! Sabhi sensors aur active interaction freeze kar diye gaye hain."

    def set_screen_allowed(self, allowed: bool) -> None:
        with self._lock:
            self._state.screen_capture_allowed = allowed
            self._persist()

    def set_recording_allowed(self, allowed: bool) -> None:
        with self._lock:
            self._state.recording_allowed = allowed
            self._persist()

    def add_sensitive_pattern(self, pattern: str) -> None:
        with self._lock:
            if pattern not in self._state.sensitive_patterns:
                self._state.sensitive_patterns.append(pattern)
                self._compile_patterns()
                self._persist()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "screen_capture_allowed": self._state.screen_capture_allowed,
                "camera_allowed": self._state.camera_allowed,
                "microphone_allowed": self._state.microphone_allowed,
                "recording_allowed": self._state.recording_allowed,
                "remote_access_allowed": self._state.remote_access_allowed,
                "is_paused": self._state.is_paused,
                "retention_minutes": self._state.screen_history_retention_minutes,
                "sensitive_rules_count": len(self._state.sensitive_patterns),
                "privacy_guard_active": True
            }


privacy_manager = PrivacyManager.get_instance()

