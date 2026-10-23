"""
core/proactive_intelligence.py — Proactive Intelligence, Reminders & Anti-Interruption Manager for ALEX 3.0.

Provides configurable assistance without spamming the owner:
  • Event Notifications: Long-running task finish, Test failure, Build failure,
    Requested file ready, Due reminders, Monitored service unavailability, Morning briefing available.
  • Anti-Interruption Controls:
    1. Do Not Disturb (DND) toggle
    2. Configurable Quiet Hours (e.g. 22:00 - 07:00)
    3. Category cooldowns (prevents alert floods)
    4. Notification Priorities (CRITICAL, HIGH, MEDIUM, LOW)
  • Integrated Reminders & Calendar scheduling with genuine timestamps.

Owner: Aditya Rajak
Salutation: Sir
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.security import OWNER_ADDRESS, security_manager

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
MEMORY_DIR = BASE_DIR / "memory"

NOTIFICATIONS_FILE = MEMORY_DIR / "notifications.json"
REMINDERS_FILE = MEMORY_DIR / "reminders.json"
PROACTIVE_CONFIG_FILE = CONFIG_DIR / "proactive_config.json"


class NotificationPriority:
    CRITICAL = "CRITICAL"  # System halts, security alarms, bypasses quiet hours
    HIGH     = "HIGH"      # Task completion, test failures, due reminders
    MEDIUM   = "MEDIUM"    # Service warnings, files ready
    LOW      = "LOW"       # Minor status notes, background updates


@dataclass
class NotificationItem:
    id: str
    category: str          # TASK, TEST, BUILD, FILE, REMINDER, SERVICE, BRIEFING, SYSTEM
    title: str
    message: str
    priority: str
    timestamp: str
    spoken: bool = False
    read: bool = False
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReminderItem:
    id: str
    text: str
    due_timestamp: str     # e.g. "2026-10-10 14:00:00" or ISO
    created_at: str
    recurrence: Optional[str] = None  # None, "daily", "weekly"
    triggered: bool = False


@dataclass
class ProactiveSettings:
    enabled: bool = True
    dnd_mode: bool = False
    quiet_hours_enabled: bool = True
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"
    cooldown_seconds: float = 60.0
    min_spoken_priority: str = NotificationPriority.HIGH


class ProactiveIntelligence:
    """Thread-safe proactive assistance and notification coordinator for ALEX."""

    _instance: Optional[ProactiveIntelligence] = None
    _lock = threading.Lock()

    def __init__(self):
        self.settings = self._load_settings()
        self._notifications: List[NotificationItem] = []
        self._reminders: List[ReminderItem] = []
        self._last_alert_times: Dict[str, float] = {}  # category -> timestamp
        self._speak_callback = None
        self._load_data()

    @classmethod
    def get_instance(cls) -> ProactiveIntelligence:
        with cls._lock:
            if cls._instance is None:
                cls._instance = ProactiveIntelligence()
            return cls._instance

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_settings(self) -> ProactiveSettings:
        if PROACTIVE_CONFIG_FILE.exists():
            try:
                data = json.loads(PROACTIVE_CONFIG_FILE.read_text(encoding="utf-8"))
                return ProactiveSettings(**data)
            except Exception:
                pass
        return ProactiveSettings()

    def save_settings(self) -> None:
        try:
            PROACTIVE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            PROACTIVE_CONFIG_FILE.write_text(json.dumps(asdict(self.settings), indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_data(self) -> None:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        # Notifications
        if NOTIFICATIONS_FILE.exists():
            try:
                raw = json.loads(NOTIFICATIONS_FILE.read_text(encoding="utf-8"))
                self._notifications = [NotificationItem(**item) for item in raw[-100:]]
            except Exception:
                self._notifications = []
        # Reminders
        if REMINDERS_FILE.exists():
            try:
                raw = json.loads(REMINDERS_FILE.read_text(encoding="utf-8"))
                self._reminders = [ReminderItem(**item) for item in raw]
            except Exception:
                self._reminders = []

    def _persist_data(self) -> None:
        try:
            # Notifications
            n_raw = [asdict(n) for n in self._notifications[-100:]]
            NOTIFICATIONS_FILE.write_text(json.dumps(n_raw, indent=2, ensure_ascii=False), encoding="utf-8")
            # Reminders
            r_raw = [asdict(r) for r in self._reminders]
            REMINDERS_FILE.write_text(json.dumps(r_raw, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def set_speak_callback(self, cb) -> None:
        """Connects voice generation pipe if speech alert is warranted."""
        self._speak_callback = cb

    # ── Anti-Interruption Gates ───────────────────────────────────────────────

    def is_quiet_hours(self) -> bool:
        if not self.settings.quiet_hours_enabled:
            return False
        now_hm = datetime.now().strftime("%H:%M")
        start = self.settings.quiet_hours_start
        end = self.settings.quiet_hours_end
        if start <= end:
            return start <= now_hm <= end
        else:
            # Crosses midnight (e.g. 22:00 to 07:00)
            return now_hm >= start or now_hm <= end

    def can_notify(self, category: str, priority: str = NotificationPriority.MEDIUM) -> Tuple[bool, str]:
        """
        Determines whether a proactive notification should be presented/spoken.
        CRITICAL priorities always pass through.
        """
        if not self.settings.enabled:
            return False, "Proactive notifications disabled"

        p_up = priority.upper()
        if p_up == NotificationPriority.CRITICAL:
            return True, "Critical priority bypass"

        if self.settings.dnd_mode:
            return False, "Do Not Disturb (DND) active"

        if self.is_quiet_hours():
            return False, "Quiet hours active"

        # Cooldown check
        now = time.monotonic()
        cat_key = category.upper()
        last_t = self._last_alert_times.get(cat_key, 0.0)
        if (now - last_t) < self.settings.cooldown_seconds:
            return False, f"Category '{category}' in cooldown ({int(self.settings.cooldown_seconds - (now - last_t))}s left)"

        return True, "Eligible"

    # ── Notification Dispatch ─────────────────────────────────────────────────

    def notify(
        self,
        category: str,
        title: str,
        message: str,
        priority: str = NotificationPriority.MEDIUM,
        spoken: bool = True,
        data: Optional[Dict[str, Any]] = None
    ) -> Optional[NotificationItem]:
        """
        Dispatches a proactive notification with full audit and safety checks.
        """
        eligible, reason = self.can_notify(category, priority)

        safe_title = security_manager.redact_secrets(title)
        safe_msg = security_manager.redact_secrets(message)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        n_id = f"notif_{uuid.uuid4().hex[:8]}"

        should_speak = spoken and eligible and (
            priority.upper() in (NotificationPriority.CRITICAL, NotificationPriority.HIGH)
        )

        item = NotificationItem(
            id=n_id,
            category=category.upper(),
            title=safe_title,
            message=safe_msg,
            priority=priority.upper(),
            timestamp=now_str,
            spoken=should_speak,
            read=False,
            data=data or {}
        )

        with self._lock:
            self._notifications.append(item)
            if eligible:
                self._last_alert_times[category.upper()] = time.monotonic()
            self._persist_data()

        # Trigger speech callback if appropriate
        if should_speak and self._speak_callback:
            try:
                self._speak_callback(f"{OWNER_ADDRESS}, {safe_title}. {safe_msg}")
            except Exception:
                pass

        return item

    # ── Convenience Triggers ──────────────────────────────────────────────────

    def notify_task_finished(self, task_goal: str, elapsed_seconds: float, success: bool, result_summary: str = "") -> None:
        status_txt = "safal ho gaya hai" if success else "asafal (failed) raha"
        title = f"Task {status_txt}"
        msg = f"Goal '{task_goal}' {elapsed_seconds}s me complete hua. {result_summary}".strip()
        prio = NotificationPriority.HIGH if success else NotificationPriority.CRITICAL
        self.notify("TASK", title, msg, priority=prio)

    def notify_test_failed(self, test_name: str, error_detail: str) -> None:
        title = "Test Failure Detected"
        msg = f"Test '{test_name}' fail ho gaya: {error_detail}"
        self.notify("TEST", title, msg, priority=NotificationPriority.HIGH)

    def notify_build_failed(self, project_name: str, error_detail: str) -> None:
        title = f"Project Build Failed: {project_name}"
        msg = f"Build verification fail ho gayi: {error_detail}"
        self.notify("BUILD", title, msg, priority=NotificationPriority.HIGH)

    def notify_file_ready(self, file_name: str, file_path: str) -> None:
        title = "File Creation Complete"
        msg = f"Aapki requested file '{file_name}' taiyar ho chuki hai."
        self.notify("FILE", title, msg, priority=NotificationPriority.MEDIUM, data={"path": file_path})

    def notify_service_down(self, service_name: str, details: str) -> None:
        title = f"Service Alert: {service_name}"
        msg = f"Subsystem '{service_name}' uncontactable hai: {details}"
        self.notify("SERVICE", title, msg, priority=NotificationPriority.CRITICAL)

    # ── Reminders & Calendar ──────────────────────────────────────────────────

    def add_reminder(self, text: str, due_time_str: str, recurrence: Optional[str] = None) -> ReminderItem:
        r_id = f"rem_{uuid.uuid4().hex[:8]}"
        item = ReminderItem(
            id=r_id,
            text=security_manager.redact_secrets(text),
            due_timestamp=due_time_str,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            recurrence=recurrence,
            triggered=False
        )
        with self._lock:
            self._reminders.append(item)
            self._persist_data()
        return item

    def check_due_reminders(self) -> List[ReminderItem]:
        """Scans and triggers any reminders whose time has arrived."""
        now = datetime.now()
        due: List[ReminderItem] = []
        with self._lock:
            for r in self._reminders:
                if not r.triggered:
                    try:
                        # Attempt to parse ISO or standard format
                        dt = datetime.fromisoformat(r.due_timestamp) if "T" in r.due_timestamp else datetime.strptime(r.due_timestamp, "%Y-%m-%d %H:%M:%S")
                        if now >= dt:
                            r.triggered = True
                            due.append(r)
                    except Exception:
                        pass
            if due:
                self._persist_data()

        for d in due:
            self.notify("REMINDER", "Scheduled Reminder", d.text, priority=NotificationPriority.HIGH)
        return due

    def get_todays_reminders(self) -> List[ReminderItem]:
        today_str = datetime.now().strftime("%Y-%m-%d")
        with self._lock:
            return [r for r in self._reminders if r.due_timestamp.startswith(today_str)]

    # ── Controls & Summary ────────────────────────────────────────────────────

    def toggle_dnd(self, enabled: Optional[bool] = None) -> str:
        with self._lock:
            if enabled is None:
                self.settings.dnd_mode = not self.settings.dnd_mode
            else:
                self.settings.dnd_mode = enabled
            self.save_settings()
        status = "ENABLED (Silent)" if self.settings.dnd_mode else "DISABLED"
        return f"{OWNER_ADDRESS}, Do Not Disturb (DND) mode is now {status}."

    def get_unread_notifications(self) -> List[NotificationItem]:
        with self._lock:
            return [n for n in self._notifications if not n.read]

    def mark_all_read(self) -> None:
        with self._lock:
            for n in self._notifications:
                n.read = True
            self._persist_data()

    def format_proactive_summary(self) -> str:
        unread = self.get_unread_notifications()
        reminders = self.get_todays_reminders()
        dnd = "ON" if self.settings.dnd_mode else "OFF"
        quiet = "ACTIVE" if self.is_quiet_hours() else "INACTIVE"

        lines = [
            f"── ALEX PROACTIVE INTELLIGENCE (DND: {dnd} | Quiet Hours: {quiet}) ──",
            f"Unread Notifications: {len(unread)} | Today's Reminders: {len(reminders)}"
        ]
        if unread:
            lines.append("Recent Notifications:")
            for u in unread[-5:]:
                lines.append(f"  • [{u.priority}] {u.title}: {u.message}")
        if reminders:
            lines.append("Today's Reminders:")
            for r in reminders:
                st = "✓ Done" if r.triggered else "⏳ Pending"
                lines.append(f"  • {r.due_timestamp.split(' ')[-1]} — {r.text} ({st})")
        return "\n".join(lines)


# Singleton
proactive_engine = ProactiveIntelligence.get_instance()

