"""
actions/automation_engine.py — Smart Automation, Scheduled Routines & Morning Briefing for ALEX 3.0.

Capabilities:
  • Reusable multi-app workflows ("jab main college project open karun to VS Code aur browser open karna")
  • Morning briefing generator (Weather, Projects, System Health, Tasks)
  • Scheduled routine status

Owner: Aditya Rajak
Salutation: Sir
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from core.action_timeline import timeline
from core.project_manager import project_manager
from core.security import security_manager, OWNER_ADDRESS

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
ROUTINES_FILE = CONFIG_DIR / "automation_routines.json"


def _load_routines() -> dict:
    if ROUTINES_FILE.exists():
        try:
            return json.loads(ROUTINES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "dev_setup": {
            "name": "Developer Environment",
            "apps": ["code", "chrome"],
            "description": "Opens VS Code and Chrome simultaneously"
        },
        "study_mode": {
            "name": "Study Setup",
            "apps": ["notepad", "calc"],
            "description": "Opens Notepad and Calculator"
        }
    }


def execute_routine(routine_name: str) -> str:
    """Executes a configured automation workflow routine."""
    routines = _load_routines()
    r = routines.get(routine_name.lower().strip())
    if not r:
        available = ", ".join(routines.keys())
        return f"{OWNER_ADDRESS}, routine '{routine_name}' not found. Available routines: {available}"

    timeline.record("AUTOMATION", f"Routine Triggered: {r['name']}", f"Apps: {', '.join(r['apps'])}")
    
    from actions.open_app import open_app
    results = []
    for app in r.get("apps", []):
        res = open_app(app)
        results.append(f"• {app}: {res}")

    return f"{OWNER_ADDRESS}, automation routine '{r['name']}' execute ho gayi:\n" + "\n".join(results)


def get_morning_briefing(length: str = "normal") -> str:
    """Generates an executive morning briefing for Sir."""
    from core.startup_manager import startup_manager
    b = startup_manager.generate_full_briefing(is_startup=False)

    today_str = b["date"]
    cur_project_name = b["tasks"]["project"]
    pending_tasks = b["tasks"]["items"]
    weather = b["weather"]
    system = b["system"]

    lines = []
    lines.append(f"{b['greeting']}")
    lines.append("")
    lines.append(f"📅 Today is {today_str} ({b['time']}).")
    if weather["available"]:
        lines.append(f"⛅ Weather: {weather['temp']} ({weather['condition']}) in {weather['location']}")
    else:
        lines.append("⛅ Weather: Information currently unavailable (Offline mode)")
    lines.append(f"💼 Active Workspace: {cur_project_name} ({b['tasks'].get('project_health', 'HEALTHY')})")
    lines.append(f"📋 Pending Tasks ({b['tasks']['pending_count']}):")
    if pending_tasks:
        for t in pending_tasks:
            lines.append(f"   • {t}")
    else:
        lines.append("   • All primary tasks completed.")

    if b.get("reminders"):
        lines.append("\n⏰ Today's Reminders:")
        for r in b["reminders"]:
            lines.append(f"   • {r}")

    if b.get("tasks", {}).get("previous_results"):
        lines.append("\n✅ Previous Task Results:")
        for pr in b["tasks"]["previous_results"]:
            lines.append(f"   • {pr}")

    lines.append("")
    lines.append(f"⚡ System Status: CPU {system['cpu']} | RAM {system['ram']} ({system['status']})")
    if system.get("errors"):
        lines.append(f"⚠ Attention Required: {system['errors'][0]}")
    
    if b.get("news"):
        lines.append("\n📰 Today's Important News:")
        for it in b["news"][:4]:
            lines.append(f"   • [{it['category']}] {it['headline']} ({it['source']})")

    lines.append("\nALEX 3.0 is ready for your commands.")
    return "\n".join(lines)


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "automation_engine",
    "description": "Executes predefined automation workflows (e.g. dev_setup, study_mode) or generates Sir's morning briefing.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action: 'execute_routine' or 'morning_briefing'"
            },
            "routine_name": {
                "type": "STRING",
                "description": "Name of the routine (e.g. 'dev_setup')"
            }
        },
        "required": ["action"]
    },
    "handler": lambda action="morning_briefing", routine_name="": (
        get_morning_briefing() if action == "morning_briefing" else execute_routine(routine_name)
    ),
}
