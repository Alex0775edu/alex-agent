"""
core/skill_router.py — Intelligent Tool & Skill Dispatcher for ALEX 3.0.

Owner: Aditya Rajak
Salutation: Aditya Sir

Selects the smallest, fastest, most secure capability:
  • Local OS / Hardware -> Direct sub-50ms native API
  • Files & Documents   -> Base filesystem / PDF / universal parsing
  • Research & Search   -> DuckDuckGo / Google RSS / Gemini Search
  • Complex Reasoning   -> Gemini Model Ladder (FAST -> SMART)
  • Coding & Syntax     -> Local AST / syntax validator
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from core.event_bus import event_bus
from core.security import security_manager
from skills.registry import skill_registry


@dataclass
class RoutedSkill:
    skill_name: str
    tool_name: str
    target_engine: str  # "LOCAL", "SKILL", "LLM", "BROWSER"
    risk_level: str     # "SAFE", "PRIVILEGED", "CRITICAL"
    estimated_latency_ms: int


class SkillRouter:
    _instance: Optional[SkillRouter] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> SkillRouter:
        with cls._lock:
            if cls._instance is None:
                cls._instance = SkillRouter()
            return cls._instance

    def route_query(self, query: str) -> RoutedSkill:
        """Determines optimal skill, engine, and safety risk level for query."""
        q = query.lower().strip()

        # 1. Local Hardware & Computer Control (Sub-20ms)
        if any(w in q for w in ("volume", "awaz", "sound", "mute", "unmute")):
            return RoutedSkill("computer", "volume_control", "LOCAL", "PRIVILEGED", 10)
        if any(w in q for w in ("ram", "cpu", "specs", "disk", "hardware")):
            return RoutedSkill("system", "resource_monitor", "LOCAL", "SAFE", 15)
        if any(w in q for w in ("open", "kholo", "launch", "start")) and any(app in q for app in ("chrome", "notepad", "calculator", "calc", "vscode", "code")):
            return RoutedSkill("computer", "open_application", "LOCAL", "PRIVILEGED", 35)

        # 2. Office & Document Creation
        if any(w in q for w in ("ppt", "presentation", "powerpoint", "slides")):
            return RoutedSkill("documents", "powerpoint_skill", "LOCAL", "PRIVILEGED", 50)
        if any(w in q for w in ("excel", "sheet", "spreadsheet", "workbook", "csv")):
            return RoutedSkill("documents", "excel_skill", "LOCAL", "PRIVILEGED", 50)
        if any(w in q for w in ("word", "docx", "report", "document")) and any(v in q for v in ("banao", "create", "likho", "write", "edit", "make")):
            return RoutedSkill("documents", "word_skill", "LOCAL", "PRIVILEGED", 50)
        if any(w in q for w in ("pdf", "docx", "file", "document", "folder", "download")):
            return RoutedSkill("files", "file_processor", "LOCAL", "PRIVILEGED", 40)

        # 3. 3D Creation & Blender
        if any(w in q for w in ("blender", "3d", "render", "low-poly", "model", "scene", "mesh")):
            return RoutedSkill("creativity", "blender_skill", "LOCAL", "PRIVILEGED", 120)

        # 4. Email & Communication
        if any(w in q for w in ("email", "mail", "draft", "outlook", "khat")):
            return RoutedSkill("communication", "email_skill", "LOCAL", "PRIVILEGED", 60)

        # 5. Vision & Screen
        if any(w in q for w in ("screen", "dekho", "look", "display", "monitor", "camera")):
            return RoutedSkill("vision", "screen_ocr", "LOCAL", "SAFE", 150)

        # 6. Coding & Syntax
        if any(w in q for w in ("python", "code", "syntax", "error", "bug", "fix code", "test", "vscode")):
            return RoutedSkill("coding", "code_verifier", "LOCAL", "PRIVILEGED", 80)

        # 7. News & Weather
        if "news" in q or "samachar" in q:
            return RoutedSkill("research", "news_engine", "LOCAL", "SAFE", 120)
        if "weather" in q or "mausam" in q:
            return RoutedSkill("research", "weather_engine", "LOCAL", "SAFE", 100)

        # 8. Web Search & Research
        if any(w in q for w in ("search", "dhundo", "google", "web", "find")):
            return RoutedSkill("research", "web_search", "LOCAL", "SAFE", 250)

        # 9. Complex General Reasoning -> LLM Cloud Ladder
        return RoutedSkill("system", "gemini_model_ladder", "LLM", "SAFE", 800)


    def find_best_skill(self, goal_or_query: str) -> Optional[Dict[str, Any]]:
        """Finds matching skill from unified SkillsEngine registry based on intent and tags."""
        from skills.engine import skills_engine
        q = goal_or_query.lower().strip()
        skills = skills_engine.list_skills(status="ENABLED")
        for s in skills:
            if s["skill_id"] in q or any(t.lower() in q for t in s.get("tags", [])):
                return s
        for s in skills:
            if any(word in q for word in s["name"].lower().split() if len(word) > 3):
                return s
        return None


skill_router = SkillRouter.get_instance()

