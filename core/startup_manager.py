"""
core/startup_manager.py — Smart Windows Startup, Greeting & Briefing Coordinator for ALEX 3.0.

Owner: Aditya Rajak
Salutation: Sir

Responsibilities:
  1. Windows Startup Automation (Startup folder / HKCU Run registry with zero admin elevation).
  2. First-Startup-Of-The-Day tracking vs Repeated-Restart suppression.
  3. Natural, time-aware greeting variations (Morning, Afternoon, Evening, Night).
  4. Audio safety checks (detect audio output before speaking, fallback to UI visual).
  5. Silent startup mode & configurable briefing settings.
  6. Comprehensive Morning Briefing aggregation (Greeting, Date, Weather, News, Projects, Health, Services).
  7. Fast non-blocking startup: local services load immediately, cloud/news loads asynchronously.
"""

from __future__ import annotations

import json
import os
import platform
import random
import sys
import time
import winreg
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.news_engine import news_intelligence
from core.weather_engine import weather_engine
from core.action_timeline import timeline
from core.project_manager import project_manager
from core.security import security_manager, OWNER_NAME, OWNER_ADDRESS

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
STARTUP_CONFIG = CONFIG_DIR / "startup_config.json"
SESSION_STATE_FILE = CONFIG_DIR / "last_session_state.json"

APP_NAME = "ALEX_AI_Assistant"


@dataclass
class StartupSettings:
    windows_startup_enabled: bool = True
    greet_on_startup: bool = True
    morning_briefing_enabled: bool = True
    news_briefing_enabled: bool = True
    weather_enabled: bool = True
    system_health_enabled: bool = True
    task_summary_enabled: bool = True
    briefing_length: str = "normal"  # "short", "normal", "detailed"
    startup_voice_enabled: bool = True
    silent_mode: bool = False  # If True, show briefing visually without audio output
    launch_minimized: bool = False  # If True, starts minimized in background with clap wake armed


class StartupManager:
    _instance: Optional[StartupManager] = None

    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.settings = self._load_settings()

    @classmethod
    def get_instance(cls) -> StartupManager:
        if cls._instance is None:
            cls._instance = StartupManager()
        return cls._instance

    # ── Configuration Persistence ──────────────────────────────────────────

    def _load_settings(self) -> StartupSettings:
        if STARTUP_CONFIG.exists():
            try:
                data = json.loads(STARTUP_CONFIG.read_text(encoding="utf-8"))
                return StartupSettings(**data)
            except Exception:
                pass
        return StartupSettings()

    def save_settings(self, settings: StartupSettings) -> None:
        self.settings = settings
        STARTUP_CONFIG.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")

    def update_settings(self, **kwargs) -> None:
        cur = asdict(self.settings)
        cur.update(kwargs)
        self.save_settings(StartupSettings(**cur))

    # ── Windows Startup Registry & Folder Management ───────────────────────

    def get_startup_executable(self, minimized: Optional[bool] = None) -> str:
        """Determines best python / pythonw launch command for Windows startup."""
        py_dir = Path(sys.executable).parent
        pyw = py_dir / "pythonw.exe"
        exe = str(pyw) if pyw.exists() else sys.executable
        main_script = str(BASE_DIR / "main.py")
        is_min = self.settings.launch_minimized if minimized is None else minimized
        extra = " --minimized" if is_min else ""
        return f'"{exe}" "{main_script}"{extra}'

    def is_windows_startup_enabled(self) -> bool:
        """Checks if ALEX is registered in Windows startup registry."""
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ
            ) as key:
                val, _ = winreg.QueryValueEx(key, APP_NAME)
                return bool(val)
        except Exception:
            return False

    def enable_windows_startup(self, minimized: Optional[bool] = None) -> Tuple[bool, str]:
        """Registers ALEX in Windows HKCU Startup (Safe, no admin elevation required)."""
        if minimized is not None:
            self.update_settings(launch_minimized=minimized)
        cmd = self.get_startup_executable()
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_WRITE
            ) as key:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
            self.update_settings(windows_startup_enabled=True)
            return True, "ALEX successfully registered to launch on Windows startup."
        except Exception as e:
            return False, f"Could not enable Windows startup: {e}"

    def disable_windows_startup(self) -> Tuple[bool, str]:
        """Unregisters ALEX from Windows startup."""
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_WRITE
            ) as key:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
            self.update_settings(windows_startup_enabled=False)
            return True, "ALEX removed from Windows startup."
        except Exception as e:
            return False, f"Could not disable Windows startup: {e}"

    # ── Session & Day Tracking ("First Startup of Day" vs "Restart") ────────

    def check_first_startup_of_day(self) -> Tuple[bool, Optional[str]]:
        """Returns (is_first_today, last_startup_time_str). Updates current session."""
        now = datetime.now()
        today_date_str = now.strftime("%Y-%m-%d")
        now_iso = now.isoformat()

        is_first = True
        last_time_str = None

        if SESSION_STATE_FILE.exists():
            try:
                state = json.loads(SESSION_STATE_FILE.read_text(encoding="utf-8"))
                last_date = state.get("last_date", "")
                last_time_str = state.get("last_timestamp", "")
                if last_date == today_date_str:
                    is_first = False
            except Exception:
                pass

        # Update session state file
        try:
            SESSION_STATE_FILE.write_text(json.dumps({
                "last_date": today_date_str,
                "last_timestamp": now_iso,
                "startup_count_today": (1 if is_first else state.get("startup_count_today", 1) + 1)
            }, indent=2), encoding="utf-8")
        except Exception:
            pass

        return is_first, last_time_str

    # ── Time-Aware Greeting Generation ──────────────────────────────────────

    def get_time_period(self) -> str:
        """Determines time of day: morning (04-12), afternoon (12-17), evening (17-21), night (21-04)."""
        hr = datetime.now().hour
        if 4 <= hr < 12:
            return "morning"
        elif 12 <= hr < 17:
            return "afternoon"
        elif 17 <= hr < 21:
            return "evening"
        else:
            return "night"

    def generate_greeting(self, is_first_today: bool = True, lang: str = "hinglish") -> str:
        period = self.get_time_period()
        addr = OWNER_ADDRESS

        morning_variants = [
            f"Good morning, {addr}. ALEX is online. Aapka system fully operational hai.",
            f"Good morning, {addr}. All core subsystems active hain aur system ready hai.",
            f"Good morning, {addr}. ALEX initialised. Ready for today's agenda."
        ]
        afternoon_variants = [
            f"Good afternoon, {addr}. ALEX is online and ready for your commands.",
            f"Good afternoon, {addr}. Workstation active hai, I am ready to assist you."
        ]
        evening_variants = [
            f"Good evening, {addr}. ALEX is online. Hope you had a productive day.",
            f"Good evening, {addr}. System is running smoothly and ready."
        ]
        night_variants = [
            f"Good evening, {addr}. ALEX is online and standing by.",
            f"Hello {addr}. ALEX is operational in night shift mode."
        ]

        if not is_first_today:
            short_variants = [
                f"{addr}, ALEX reconnected and standing by.",
                f"ALEX online, {addr}. Ready.",
                f"Welcome back, {addr}."
            ]
            return random.choice(short_variants)

        if period == "morning":
            return random.choice(morning_variants)
        elif period == "afternoon":
            return random.choice(afternoon_variants)
        elif period == "evening":
            return random.choice(evening_variants)
        else:
            return random.choice(night_variants)

    # ── Audio Safety Check ──────────────────────────────────────────────────

    def has_audio_output(self) -> bool:
        """Verifies whether a working audio output device is present."""
        try:
            import sounddevice as sd
            devs = sd.query_devices()
            for d in devs:
                if d.get("max_output_channels", 0) > 0:
                    return True
        except Exception:
            pass
        return False

    # ── Complete Morning Briefing Aggregator ────────────────────────────────

    def generate_full_briefing(self, is_startup: bool = False) -> Dict[str, Any]:
        """Builds structured data for both Speech (<60s) and Dashboard/UI presentation."""
        is_first_today, _ = self.check_first_startup_of_day() if is_startup else (False, None)
        greeting = self.generate_greeting(is_first_today=is_first_today)
        period = self.get_time_period()

        # 1. Date & Day
        date_str = datetime.now().strftime("%A, %d %B %Y")
        time_str = datetime.now().strftime("%I:%M %p")

        # 2. Weather
        weather_info = weather_engine.get_weather()
        weather_spoken = weather_engine.format_weather_summary(lang="hinglish") if weather_info.available else ""

        # 3. Tasks & Projects
        cur_project_name = project_manager.get_active_project()
        cur_project = project_manager.get_project_context(cur_project_name)
        p_tasks = cur_project.get("tasks", []) if isinstance(cur_project, dict) else []
        pending_tasks = [t for t in p_tasks if not t.get("done", False)]
        task_count = len(pending_tasks)
        proj_health = cur_project.get("health_status", "HEALTHY")

        # 3b. Previous Task Results from Task Center
        from core.task_center import task_center
        recent_completed = [
            t for t in task_center.list_tasks_by_status("COMPLETED")[-2:]
        ]
        prev_results_summary = [f"{t.goal} ({t.verification})" for t in recent_completed]

        # 3c. Today's Reminders from Proactive Intelligence
        from core.proactive_intelligence import proactive_engine
        today_reminders = proactive_engine.get_todays_reminders()
        reminders_text = [r.text for r in today_reminders[:3]]

        # 4. System Health & Critical Errors
        import psutil
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent

        from core.service_manager import service_manager
        degraded_services = [
            s for s in service_manager.get_all_services().values()
            if not s.get("healthy") or not s.get("is_running")
        ]
        important_errors = [f"{s['name']}: {s['details']}" for s in degraded_services]

        # 5. News Headlines (with authentic sources)
        news_items = news_intelligence.fetch_top_news(max_per_cat=2)
        news_spoken = news_intelligence.format_news_for_briefing(max_items=3) if news_items else ""

        # 6. Compose Concise Speech (under 60s)
        speech_parts = [greeting]
        if self.settings.weather_enabled and weather_spoken:
            speech_parts.append(weather_spoken)
        if self.settings.task_summary_enabled:
            if task_count > 0:
                speech_parts.append(f"{cur_project_name} project ({proj_health}) mein {task_count} pending tasks hain.")
            else:
                speech_parts.append(f"{cur_project_name} project tasks up to date hain.")
        recovery_info = task_center.recover_unfinished_tasks()
        if recovery_info.get("count", 0) > 0:
            speech_parts.append(f"Notice: {recovery_info['count']} unfinished task(s) checkpoint verified and ready to continue.")
        if reminders_text:
            speech_parts.append(f"Aaj ke liye {len(reminders_text)} reminders scheduled hain: {', '.join(reminders_text)}.")
        if important_errors:
            speech_parts.append(f"Attention required: {important_errors[0]}.")
        elif self.settings.system_health_enabled:
            speech_parts.append(f"System healthy hai, RAM usage {ram:.0f}% hai.")
        if self.settings.news_briefing_enabled and news_spoken and is_first_today:
            speech_parts.append(news_spoken)
        speech_parts.append(f"Full details aapke ALEX command center par present kar di gayi hain.")

        spoken_text = " ".join(speech_parts)

        # 7. Structured Dashboard Payload
        structured = {
            "greeting": greeting,
            "period": period,
            "time": time_str,
            "date": date_str,
            "owner": OWNER_NAME,
            "owner_address": OWNER_ADDRESS,
            "weather": {
                "available": weather_info.available,
                "temp": f"{weather_info.temperature_c}°C" if weather_info.available else "N/A",
                "condition": weather_info.condition if weather_info.available else "Offline",
                "location": weather_info.location if weather_info.available else "Local"
            },
            "system": {
                "cpu": f"{cpu:.0f}%",
                "ram": f"{ram:.0f}%",
                "status": "Degraded" if important_errors else "Optimal",
                "errors": important_errors
            },
            "tasks": {
                "project": cur_project_name,
                "project_health": proj_health,
                "pending_count": task_count,
                "items": [t.get("task") for t in pending_tasks[:5]],
                "previous_results": prev_results_summary
            },
            "reminders": reminders_text,
            "news": [asdict(it) for it in news_items[:8]],
            "spoken_summary": spoken_text
        }

        timeline.record("BRIEFING", "Morning Briefing Built", f"Prepared briefing for {OWNER_ADDRESS}.")
        return structured


startup_manager = StartupManager.get_instance()

