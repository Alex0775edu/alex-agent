"""
skills/registry.py — Central Skill Registry and loader for ALEX.

Manages all 14 modular skills:
  1. browser
  2. computer
  3. files
  4. documents
  5. coding
  6. research
  7. vision
  8. memory
  9. system
  10. communication
  11. youtube
  12. automation
  13. meetings
  14. projects

Owner: Aditya Rajak
Salutation: Aditya Sir
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional
from skills.base_skill import BaseSkill, SkillMetadata


class SkillRegistry:
    """Central registry for all modular skills."""

    _instance: Optional[SkillRegistry] = None
    _lock = threading.Lock()

    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}
        self._init_skills()

    @classmethod
    def get_instance(cls) -> SkillRegistry:
        with cls._lock:
            if cls._instance is None:
                cls._instance = SkillRegistry()
            return cls._instance

    def register(self, skill: BaseSkill) -> None:
        self._skills[skill.metadata.name] = skill

    def get(self, name: str) -> Optional[BaseSkill]:
        return self._skills.get(name)

    def list_skills(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": s.metadata.name,
                "version": s.metadata.version,
                "description": s.metadata.description,
                "risk_level": s.metadata.risk_level,
                "actions": list(s.list_actions().keys()),
            }
            for s in self._skills.values()
        ]

    @property
    def engine(self):
        from skills.engine import skills_engine
        return skills_engine

    def execute_skill(self, skill_id: str, action_name: Optional[str] = None, parameters: Optional[Dict[str, Any]] = None, ctx: Optional[Any] = None) -> Any:
        from skills.engine import skills_engine
        return skills_engine.execute_skill(skill_id, action_name=action_name, parameters=parameters, ctx=ctx)

    def list_engine_skills(self, category: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        from skills.engine import skills_engine
        return skills_engine.list_skills(category=category, status=status)

    def _init_skills(self):
        # 1. Computer Skill
        from actions.open_app import open_app
        from actions.computer_settings import volume_up, volume_down, volume_mute
        comp = BaseSkill(SkillMetadata("computer", "3.0", "OS, apps, and computer control", "CONFIRM", "system"))
        comp.register_action("open_app", lambda app_name: open_app(app_name))
        comp.register_action("volume_up", lambda: volume_up())
        comp.register_action("volume_down", lambda: volume_down())
        comp.register_action("volume_mute", lambda: volume_mute())
        self.register(comp)

        # 2. Browser Skill
        from actions.browser_control import browser_control
        browser = BaseSkill(SkillMetadata("browser", "3.0", "Web navigation, search, and interaction", "CONFIRM", "web"))
        browser.register_action("control", lambda action, url="", query="", selector="", text="": browser_control(action, url, query, selector, text))
        self.register(browser)

        # 3. Files Skill
        from actions.file_processor import file_processor
        from actions.file_controller import file_controller
        files = BaseSkill(SkillMetadata("files", "3.0", "File organization, management, and conversions", "CONFIRM", "filesystem"))
        files.register_action(
            "process",
            lambda file_path, action="summarize", **kwargs: file_processor({"file_path": file_path, "action": action, **kwargs})
        )
        files.register_action("manage", lambda action="list", **kwargs: file_controller(action=action, **kwargs))
        self.register(files)

        # 4. Documents Skill
        from actions.document_agent import analyze_document
        docs = BaseSkill(SkillMetadata("documents", "3.0", "Universal document understanding (PDF, DOCX, XLSX, CSV)", "SAFE", "documents"))
        docs.register_action("analyze", lambda file_path, task="summarize", query="": analyze_document(file_path, task, query))
        self.register(docs)

        # 5. Coding Skill
        from actions.dev_agent import dev_agent
        coding = BaseSkill(SkillMetadata("coding", "3.0", "Full-stack coding, diagnostics, tests, and refactoring", "CONFIRM", "developer"))
        coding.register_action("agent", lambda instruction, project_path="", auto_commit=False: dev_agent(instruction, project_path, auto_commit))
        self.register(coding)

        # 6. Research Skill
        from actions.research_agent import deep_research
        res = BaseSkill(SkillMetadata("research", "3.0", "Deep multi-source research and factual synthesis", "SAFE", "research"))
        res.register_action("research", lambda topic, max_sources=3: deep_research(topic, max_sources))
        self.register(res)

        # 7. Vision Skill
        from actions.screen_processor import screen_processor
        vision = BaseSkill(SkillMetadata("vision", "3.0", "Screen capture, OCR, and visual error analysis", "SAFE", "vision"))
        vision.register_action("inspect_screen", lambda question="", angle="screen": screen_processor(question=question, angle=angle))
        self.register(vision)

        # 8. Memory Skill
        from memory.memory_manager import load_memory, save_memory, search_memory
        mem = BaseSkill(SkillMetadata("memory", "3.0", "Long-term and persistent contextual memory", "SAFE", "memory"))
        mem.register_action("load", lambda: load_memory())
        mem.register_action("search", lambda query: search_memory(query))
        self.register(mem)

        # 9. System Skill
        from actions.system_monitor import get_system_status
        from core.diagnostics import run_self_diagnostics
        sys_s = BaseSkill(SkillMetadata("system", "3.0", "System metrics, hardware audit, and diagnostics", "SAFE", "system"))
        sys_s.register_action("status", lambda: get_system_status())
        sys_s.register_action("diagnostics", lambda: run_self_diagnostics())
        self.register(sys_s)

        # 10. Communication Skill
        from actions.send_message import send_message
        comm = BaseSkill(SkillMetadata("communication", "3.0", "Drafting messages, notifications, and alerts", "CONFIRM", "communication"))
        comm.register_action("send_message", lambda recipient, message, channel="telegram": send_message(recipient, message, channel))
        self.register(comm)

        # 11. YouTube Skill
        from actions.youtube_video import youtube_video
        yt = BaseSkill(SkillMetadata("youtube", "3.0", "YouTube video lookup and direct playback", "SAFE", "media"))
        yt.register_action("play", lambda query: youtube_video(query))
        self.register(yt)

        # 12. Automation Skill
        from actions.automation_engine import execute_routine, get_morning_briefing
        auto = BaseSkill(SkillMetadata("automation", "3.0", "Workflow routines, scheduled tasks, and morning briefing", "CONFIRM", "automation"))
        auto.register_action("routine", lambda routine_name: execute_routine(routine_name))
        auto.register_action("briefing", lambda: get_morning_briefing())
        self.register(auto)

        # 13. Meetings Skill
        from actions.meeting_mode import process_meeting_notes
        meet = BaseSkill(SkillMetadata("meetings", "3.0", "Meeting transcription, decisions, and task extraction", "SAFE", "productivity"))
        meet.register_action("summarize", lambda transcript_text, title="Meeting": process_meeting_notes(transcript_text, title))
        self.register(meet)

        # 14. Projects Skill
        from core.project_manager import project_manager
        proj = BaseSkill(SkillMetadata("projects", "3.0", "Project workspace switching and state recovery", "SAFE", "projects"))
        proj.register_action("switch", lambda project_name: project_manager.set_active_project(project_name))
        proj.register_action("continue", lambda: project_manager.continue_where_left_off())
        self.register(proj)

        # 15. Email & Communication Engine Skill
        from core.email_engine import email_engine
        email_skill = BaseSkill(SkillMetadata("email", "3.0", "Authenticated email drafting, RFC822 EML export, and Outlook COM delivery", "CONFIRM", "communication"))
        email_skill.register_action("draft", lambda recipient, subject, body, attachments=None: email_engine.create_draft(recipient, subject, body, attachments=attachments))
        email_skill.register_action("send", lambda draft_id, authorized=False: email_engine.send_draft(draft_id, explicit_authorized=authorized))
        self.register(email_skill)

        # 16. 3D & Blender Creation Skill
        from creation_studio.blender_engine import blender_engine
        blender_skill = BaseSkill(SkillMetadata("blender", "3.0", "3D scene synthesis, bpy scripting, and headless Blender 5.2 rendering", "CONFIRM", "creativity"))
        blender_skill.register_action("create_scene", lambda scene_description, target_name=None, export_formats=None, render_preview=True: blender_engine.create_3d_scene(scene_description, target_name, export_formats, render_preview))
        self.register(blender_skill)



# Singleton accessor
skill_registry = SkillRegistry.get_instance()
