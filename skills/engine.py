"""
skills/engine.py — Central Unified Skills Engine & Tool Orchestrator for ALEX 7.0.

Provides discovery, registration, validation, execution, and lifecycle management
across all 6 core skill categories:
  1. Computer and Desktop
  2. Browser and Web
  3. Documents and Creativity
  4. Development
  5. Personal Productivity
  6. System Intelligence

Enforces the Standard Skill Execution Contract:
  Validate -> Check Clearance -> Verify Environment -> Plan Consequential Actions
  -> Execute in Sandbox -> Verify Outcome ("No False Success") -> Record Diagnostics

Owner: Aditya Rajak
Salutation: Aditya Sir / Sir
Assistant: ALEX
"""

from __future__ import annotations

import importlib
import inspect
import json
import os
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.security import PERM_LEVEL_1_READ, PERM_LEVEL_2_NORMAL, PERM_LEVEL_3_SENSITIVE, security_manager
from skills.sandbox import sandbox
from skills.sdk import (
    BaseAlexSkill, ExecutionStatus, SkillCategory, SkillContext, SkillManifest,
    SkillResult, SkillStatus
)

BASE_DIR = Path(__file__).resolve().parent.parent
ACTIONS_DIR = BASE_DIR / "actions"
PLUGINS_DIR = BASE_DIR / "plugins"
CONFIG_FILE = BASE_DIR / "config" / "skills_config.json"


@dataclass
class SkillEntry:
    manifest: SkillManifest
    skill_instance: Optional[BaseAlexSkill] = None
    status: SkillStatus = SkillStatus.ENABLED
    handler: Optional[Callable] = None
    file_path: Optional[str] = None
    last_health_check: Optional[Dict[str, Any]] = None
    execution_count: int = 0
    failure_count: int = 0
    recent_errors: List[str] = field(default_factory=list)


class SkillsEngine:
    """Central engine managing all modular skills, built-in actions, and third-party plugins."""

    _instance: Optional[SkillsEngine] = None
    _lock = threading.RLock()

    def __init__(self):
        self._skills: Dict[str, SkillEntry] = {}
        self._disabled_skills: set[str] = set()
        self._load_config()
        self._discover_and_register_all()

    @classmethod
    def get_instance(cls) -> SkillsEngine:
        with cls._lock:
            if cls._instance is None:
                cls._instance = SkillsEngine()
            return cls._instance

    def _load_config(self) -> None:
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                self._disabled_skills = set(data.get("disabled_skills", []))
            except Exception:
                pass

    def _save_config(self) -> None:
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "disabled_skills": list(self._disabled_skills),
                "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            CONFIG_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    # ── Discovery & Registration ──────────────────────────────────────────────

    def _discover_and_register_all(self) -> None:
        """Discovers built-in actions, plugins, and modular skill classes."""
        # 1. Register Core Built-in Skills across the 6 Categories
        self._register_builtin_skills()

        # 2. Discover Plugins from plugins/
        self._discover_plugins()

    def _register_builtin_skills(self) -> None:
        """Registers all built-in ALEX capabilities under the 6 official categories."""
        # --- Category 1: Computer and Desktop ---
        self._register_skill(
            SkillManifest(
                skill_id="desktop_control",
                name="Desktop & Window Management",
                description="Window positioning, minimizing, app focus, and screen coordinate operations.",
                category=SkillCategory.COMPUTER_DESKTOP,
                required_permissions=PERM_LEVEL_2_NORMAL,
                dependencies=["pyautogui"],
                tags=["desktop", "gui", "windows"]
            ),
            handler=self._load_action_handler("actions.desktop", "desktop_control")
        )
        self._register_skill(
            SkillManifest(
                skill_id="open_application",
                name="Application Launcher",
                description="Launches installed Windows desktop software and system utilities.",
                category=SkillCategory.COMPUTER_DESKTOP,
                required_permissions=PERM_LEVEL_2_NORMAL,
                tags=["launch", "apps", "os"]
            ),
            handler=self._load_action_handler("actions.open_app", "open_app")
        )
        self._register_skill(
            SkillManifest(
                skill_id="screen_vision",
                name="Screen Inspection & OCR",
                description="Captures active display, identifies UI elements, errors, and reads visible text.",
                category=SkillCategory.COMPUTER_DESKTOP,
                required_permissions=PERM_LEVEL_1_READ,
                dependencies=["PIL"],
                tags=["vision", "ocr", "screen"]
            ),
            handler=self._load_action_handler("actions.screen_processor", "screen_process")
        )
        self._register_skill(
            SkillManifest(
                skill_id="clipboard_manager",
                name="Clipboard Assistant",
                description="Reads, formats, and updates system clipboard contents.",
                category=SkillCategory.COMPUTER_DESKTOP,
                required_permissions=PERM_LEVEL_2_NORMAL,
                dependencies=["pyperclip"],
                tags=["clipboard", "text"]
            ),
            handler=self._load_action_handler("actions.clipboard_mode", "clipboard_mode")
        )

        # --- Category 2: Browser and Web ---
        self._register_skill(
            SkillManifest(
                skill_id="browser_automation",
                name="Browser Controller",
                description="Automates navigation, page extraction, form filling, and web interactions.",
                category=SkillCategory.BROWSER_WEB,
                required_permissions=PERM_LEVEL_2_NORMAL,
                dependencies=["playwright"],
                tags=["browser", "web", "automation"]
            ),
            handler=self._load_action_handler("actions.browser_control", "browser_control")
        )
        self._register_skill(
            SkillManifest(
                skill_id="web_research",
                name="Web Research & Discovery",
                description="Searches the live web, extracts citations, and synthesizes answers.",
                category=SkillCategory.BROWSER_WEB,
                required_permissions=PERM_LEVEL_1_READ,
                tags=["search", "google", "research"]
            ),
            handler=self._load_action_handler("actions.web_search", "web_search")
        )
        self._register_skill(
            SkillManifest(
                skill_id="deep_research",
                name="Multi-Source Deep Research Agent",
                description="Autonomous multi-step topic exploration across web sources with factual citations.",
                category=SkillCategory.BROWSER_WEB,
                required_permissions=PERM_LEVEL_1_READ,
                tags=["research", "synthesis", "agent"]
            ),
            handler=self._load_action_handler("actions.research_agent", "deep_research")
        )

        # --- Category 3: Documents and Creativity ---
        self._register_skill(
            SkillManifest(
                skill_id="file_processor",
                name="Universal File & Media Processor",
                description="Processes, converts, and analyzes PDF, DOCX, XLSX, CSV, images, and audio/video.",
                category=SkillCategory.DOCUMENTS_CREATIVITY,
                required_permissions=PERM_LEVEL_2_NORMAL,
                dependencies=["openpyxl", "docx", "PIL"],
                tags=["files", "pdf", "docx", "media"]
            ),
            handler=self._load_action_handler("actions.file_processor", "file_processor")
        )
        self._register_skill(
            SkillManifest(
                skill_id="document_creator",
                name="Document & Presentation Generator",
                description="Generates professional Word docs, PDF summaries, and PowerPoint presentation decks.",
                category=SkillCategory.DOCUMENTS_CREATIVITY,
                required_permissions=PERM_LEVEL_2_NORMAL,
                dependencies=["docx", "pptx"],
                tags=["creator", "pptx", "word", "pdf"]
            ),
            handler=self._load_action_handler("actions.creation_engine", "create_document")
        )

        # --- Category 4: Development ---
        self._register_skill(
            SkillManifest(
                skill_id="dev_agent",
                name="Autonomous Developer Agent",
                description="Inspects project workspaces, writes code, fixes bugs, and runs test suites.",
                category=SkillCategory.DEVELOPMENT,
                required_permissions=PERM_LEVEL_2_NORMAL,
                tags=["coding", "git", "python", "developer"]
            ),
            handler=self._load_action_handler("actions.dev_agent", "dev_agent")
        )
        self._register_skill(
            SkillManifest(
                skill_id="code_helper",
                name="Code Syntax & Refactoring Helper",
                description="Fast AST verification, linting, syntax audits, and code explanation.",
                category=SkillCategory.DEVELOPMENT,
                required_permissions=PERM_LEVEL_1_READ,
                tags=["lint", "syntax", "refactor"]
            ),
            handler=self._load_action_handler("actions.code_helper", "code_helper")
        )

        # --- Category 5: Personal Productivity ---
        self._register_skill(
            SkillManifest(
                skill_id="reminder_manager",
                name="Reminders & Scheduler",
                description="Manages time-based alerts, follow-ups, and calendar schedules for Aditya Sir.",
                category=SkillCategory.PERSONAL_PRODUCTIVITY,
                required_permissions=PERM_LEVEL_2_NORMAL,
                tags=["reminders", "time", "productivity"]
            ),
            handler=self._load_action_handler("actions.reminder", "reminder")
        )
        self._register_skill(
            SkillManifest(
                skill_id="automation_engine",
                name="Workstation Routines & Briefings",
                description="Executes morning briefings, focus mode routines, and system maintenance tasks.",
                category=SkillCategory.PERSONAL_PRODUCTIVITY,
                required_permissions=PERM_LEVEL_2_NORMAL,
                tags=["routines", "briefing", "automation"]
            ),
            handler=self._load_action_handler("actions.automation_engine", "automation_engine")
        )
        self._register_skill(
            SkillManifest(
                skill_id="knowledge_brain",
                name="Personal Knowledge Brain & Memory",
                description="Queries multi-layer memory, indexes documents, and stores project decisions.",
                category=SkillCategory.PERSONAL_PRODUCTIVITY,
                required_permissions=PERM_LEVEL_1_READ,
                dependencies=["sqlite3"],
                tags=["memory", "knowledge", "fts5"]
            ),
            handler=self._load_action_handler("actions.knowledge_brain", "knowledge_brain")
        )

        # --- Category 6: System Intelligence ---
        self._register_skill(
            SkillManifest(
                skill_id="system_monitor",
                name="Hardware & Resource Monitor",
                description="Inspects CPU, RAM, disk space, GPU utilization, and background processes.",
                category=SkillCategory.SYSTEM_INTELLIGENCE,
                required_permissions=PERM_LEVEL_1_READ,
                dependencies=["psutil"],
                tags=["hardware", "cpu", "ram", "telemetry"]
            ),
            handler=self._load_action_handler("actions.system_monitor", "get_system_status")
        )
        self._register_skill(
            SkillManifest(
                skill_id="computer_settings",
                name="Computer Settings & Audio Control",
                description="Adjusts master volume, display settings, and system power states.",
                category=SkillCategory.SYSTEM_INTELLIGENCE,
                required_permissions=PERM_LEVEL_2_NORMAL,
                tags=["settings", "audio", "volume"]
            ),
            handler=self._load_action_handler("actions.computer_settings", "computer_settings")
        )

    def _load_action_handler(self, module_str: str, function_name: str) -> Optional[Callable]:
        try:
            mod = importlib.import_module(module_str)
            # Try module-level TOOL handler first if present
            tool_dict = getattr(mod, "TOOL", None)
            if isinstance(tool_dict, dict) and "handler" in tool_dict:
                return tool_dict["handler"]
            return getattr(mod, function_name, None)
        except Exception:
            return None

    def _discover_plugins(self) -> None:
        """Discovers custom plugins located in plugins/ directory."""
        if not PLUGINS_DIR.exists():
            return

        for p_file in PLUGINS_DIR.glob("*.py"):
            if p_file.name.startswith(("_", ".")):
                continue
            skill_id = p_file.stem
            try:
                spec = importlib.util.spec_from_file_location(f"plugins.{skill_id}", p_file)
                if not spec or not spec.loader:
                    continue
                mod = importlib.util.module_from_spec(spec)
                sys.modules[f"plugins.{skill_id}"] = mod
                spec.loader.exec_module(mod)

                # Check for BaseAlexSkill instance, MANIFEST, or TOOL/PLUGIN dict
                skill_inst = getattr(mod, "SKILL", getattr(mod, "SKILL_INSTANCE", None))
                manifest = getattr(mod, "MANIFEST", None)
                handler = getattr(mod, "run", getattr(mod, "handler", None))
                tool_dict = getattr(mod, "TOOL", getattr(mod, "PLUGIN", None))

                if skill_inst and isinstance(skill_inst, BaseAlexSkill):
                    manifest = skill_inst.manifest
                    self._register_skill(manifest, handler=handler or getattr(skill_inst, "run", None), skill_instance=skill_inst, file_path=str(p_file))
                    continue

                if isinstance(tool_dict, dict):
                    manifest = SkillManifest(
                        skill_id=tool_dict.get("name", skill_id),
                        name=tool_dict.get("name", skill_id).replace("_", " ").title(),
                        description=tool_dict.get("description", "Custom plugin"),
                        category=SkillCategory.DEVELOPMENT,
                        required_permissions=PERM_LEVEL_2_NORMAL
                    )
                    handler = tool_dict.get("handler", handler)

                if manifest and isinstance(manifest, SkillManifest):
                    self._register_skill(manifest, handler=handler, file_path=str(p_file))
            except Exception as e:
                # Log but do not crash host
                print(f"[SkillsEngine] Notice loading plugin {p_file.name}: {e}")

    def _register_skill(
        self,
        manifest: SkillManifest,
        handler: Optional[Callable] = None,
        skill_instance: Optional[BaseAlexSkill] = None,
        file_path: Optional[str] = None
    ) -> None:
        status = SkillStatus.DISABLED if manifest.skill_id in self._disabled_skills else SkillStatus.ENABLED
        entry = SkillEntry(
            manifest=manifest,
            skill_instance=skill_instance,
            status=status,
            handler=handler,
            file_path=file_path
        )
        # Run initial dependency health audit
        if status == SkillStatus.ENABLED:
            ok, msg = self.check_skill_health(manifest.skill_id, entry)
            if not ok and "Missing Python dependencies" in msg:
                entry.status = SkillStatus.MISSING_DEPS

        self._skills[manifest.skill_id] = entry

    # ── Skill Management Operations ───────────────────────────────────────────

    def get_skill(self, skill_id: str) -> Optional[SkillEntry]:
        with self._lock:
            return self._skills.get(skill_id)

    def list_skills(
        self,
        category: Optional[str] = None,
        status: Optional[str] = None,
        search_query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        with self._lock:
            out = []
            for s_id, entry in self._skills.items():
                m = entry.manifest
                if category and m.category.value.lower() != category.lower():
                    continue
                if status and entry.status.value.lower() != status.lower():
                    continue
                if search_query:
                    q = search_query.lower()
                    if q not in m.name.lower() and q not in m.description.lower() and q not in s_id.lower():
                        continue

                out.append({
                    "skill_id": s_id,
                    "name": m.name,
                    "description": m.description,
                    "version": m.version,
                    "author": m.author,
                    "category": m.category.value,
                    "status": entry.status.value,
                    "required_permissions": m.required_permissions,
                    "dependencies": m.dependencies,
                    "tags": m.tags,
                    "executions": entry.execution_count,
                    "failures": entry.failure_count,
                    "is_sandboxed": m.is_sandboxed
                })
            return out

    def enable_skill(self, skill_id: str) -> Tuple[bool, str]:
        with self._lock:
            entry = self._skills.get(skill_id)
            if not entry:
                return False, f"Skill '{skill_id}' not found."
            self._disabled_skills.discard(skill_id)
            entry.status = SkillStatus.ENABLED
            self._save_config()
            return True, f"Skill '{entry.manifest.name}' enabled successfully."

    def disable_skill(self, skill_id: str) -> Tuple[bool, str]:
        with self._lock:
            entry = self._skills.get(skill_id)
            if not entry:
                return False, f"Skill '{skill_id}' not found."
            self._disabled_skills.add(skill_id)
            entry.status = SkillStatus.DISABLED
            self._save_config()
            return True, f"Skill '{entry.manifest.name}' disabled."

    def check_skill_health(self, skill_id: str, entry: Optional[SkillEntry] = None) -> Tuple[bool, str]:
        """Runs live environment, dependencies, and handler health inspection."""
        entry = entry or self._skills.get(skill_id)
        if not entry:
            return False, f"Skill '{skill_id}' not found."

        m = entry.manifest
        t0 = time.monotonic()

        # 1. Dependency checks
        missing = []
        for dep in m.dependencies:
            try:
                __import__(dep)
            except ImportError:
                missing.append(dep)

        if missing:
            res_msg = f"Missing Python dependencies: {', '.join(missing)}"
            entry.last_health_check = {"healthy": False, "details": res_msg, "duration_ms": 1.0}
            entry.status = SkillStatus.MISSING_DEPS
            return False, res_msg

        # 2. Handler availability check
        if not entry.handler and not entry.skill_instance:
            res_msg = "No operational execution handler or skill instance bound."
            entry.last_health_check = {"healthy": False, "details": res_msg, "duration_ms": 1.0}
            entry.status = SkillStatus.NEEDS_SETUP
            return False, res_msg

        duration = round((time.monotonic() - t0) * 1000, 2)
        res_msg = "Operational: All dependencies and handlers verified."
        entry.last_health_check = {"healthy": True, "details": res_msg, "duration_ms": duration}
        return True, res_msg

    # ── Standard Skill Execution Contract ─────────────────────────────────────

    def execute_skill(
        self,
        skill_id: str,
        action_name: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        ctx: Optional[SkillContext] = None
    ) -> SkillResult:
        """
        Executes a skill strictly via the 9-step contract:
          1. Validate inputs
          2. Check permissions via Central Security Manager
          3. Verify dependencies & environment
          4. Consequential action planning / disclosure
          5. Sandbox execution with timeout & cancellation
          6. Capture structured output
          7. Outcome verification
          8. Record diagnostics
        """
        t0 = time.monotonic()
        parameters = parameters or {}
        ctx = ctx or SkillContext(skill_id=skill_id, parameters=parameters)

        with self._lock:
            entry = self._skills.get(skill_id)
            if not entry:
                return SkillResult(
                    status=ExecutionStatus.FAILED,
                    output=None,
                    error=f"Skill '{skill_id}' does not exist in registry.",
                    duration_ms=round((time.monotonic() - t0) * 1000, 2)
                )

            if entry.status == SkillStatus.DISABLED:
                return SkillResult(
                    status=ExecutionStatus.FAILED,
                    output=None,
                    error=f"Skill '{entry.manifest.name}' is currently disabled by owner.",
                    duration_ms=round((time.monotonic() - t0) * 1000, 2)
                )

        m = entry.manifest

        # Step 2: Central Security Manager Authorization
        allowed, perm_reason, perm_level = security_manager.authorize_action(skill_id, parameters)
        if not allowed:
            entry.failure_count += 1
            return SkillResult(
                status=ExecutionStatus.FAILED,
                output=None,
                error=f"Blocked by Central Security Manager: {perm_reason}",
                duration_ms=round((time.monotonic() - t0) * 1000, 2),
                diagnostics={"security_level": perm_level, "reason": perm_reason}
            )

        # Step 3: Dependencies & Environment verification
        health_ok, health_msg = self.check_skill_health(skill_id, entry)
        if not health_ok:
            entry.failure_count += 1
            return SkillResult(
                status=ExecutionStatus.DEPENDENCY_UNAVAILABLE,
                output=None,
                error=health_msg,
                duration_ms=round((time.monotonic() - t0) * 1000, 2)
            )

        # Step 4: Consequential Action Guard (Level 3 Requires explicit approval)
        if perm_level == PERM_LEVEL_3_SENSITIVE and not parameters.get("__confirmed__"):
            return SkillResult(
                status=ExecutionStatus.REQUIRES_APPROVAL,
                output=None,
                error=f"Consequential action requires confirmation: {m.name}",
                duration_ms=round((time.monotonic() - t0) * 1000, 2),
                diagnostics={"risk_level": "SENSITIVE", "skill": skill_id}
            )

        # Step 5 & 6: Sandboxed Execution with Timeout
        action_name = action_name or parameters.get("action")
        handler = entry.handler
        if entry.skill_instance and action_name and action_name in entry.skill_instance.list_actions():
            handler = lambda **kw: entry.skill_instance.execute(action_name, kw, ctx=ctx)
        elif entry.skill_instance and hasattr(entry.skill_instance, "run") and not handler:
            handler = lambda **kw: entry.skill_instance.run(kw, ctx=ctx)

        if not handler:
            return SkillResult(
                status=ExecutionStatus.FAILED,
                output=None,
                error=f"No callable handler for skill '{skill_id}'.",
                duration_ms=round((time.monotonic() - t0) * 1000, 2)
            )

        entry.execution_count += 1

        try:
            # Execute within Sandbox
            res = sandbox.run_isolated(
                func=handler,
                kwargs={"parameters": parameters} if "parameters" in inspect.signature(handler).parameters else parameters,
                timeout_seconds=m.timeout_seconds,
                ctx=ctx
            )

            # Step 7: Outcome Verification ("No False Success")
            if res.status == ExecutionStatus.SUCCESS:
                # If handler returned error string or empty failure, mark appropriately
                out_str = str(res.output or "")
                if out_str.lower().startswith(("error:", "failed:", "exception:")):
                    res.status = ExecutionStatus.FAILED
                    res.error = out_str
                    res.verified = False
                    entry.failure_count += 1
                else:
                    res.verified = True
            else:
                entry.failure_count += 1
                if res.error:
                    entry.recent_errors.append(f"[{time.strftime('%H:%M:%S')}] {res.error[:120]}")
                    entry.recent_errors = entry.recent_errors[-10:]

            return res

        except Exception as e:
            entry.failure_count += 1
            return SkillResult(
                status=ExecutionStatus.FAILED,
                output=None,
                error=f"Skill crashed during execution: {e}",
                duration_ms=round((time.monotonic() - t0) * 1000, 2),
                diagnostics={"exception": str(e)}
            )


# Singleton Instance
skills_engine = SkillsEngine.get_instance()
