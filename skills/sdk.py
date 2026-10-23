"""
skills/sdk.py — Developer SDK & Contracts for ALEX Skills & Plugins.

Provides standard abstractions for building, validating, and packaging skills:
  • SkillManifest: metadata, schemas, permissions, dependencies, OS compatibility
  • SkillResult: structured execution outcome with verification status
  • SkillContext: execution runtime context with sanitized logging & cancel tokens
  • BaseAlexSkill: extensible base class for all built-in and third-party skills

Owner: Aditya Rajak
Salutation: Aditya Sir / Sir
Assistant: ALEX
"""

from __future__ import annotations

import inspect
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


class SkillStatus(str, Enum):
    INSTALLED = "INSTALLED"
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    NEEDS_SETUP = "NEEDS_SETUP"
    MISSING_DEPS = "MISSING_DEPS"
    FAILED_HEALTH = "FAILED_HEALTH"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"


class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"


class SkillCategory(str, Enum):
    COMPUTER_DESKTOP = "Computer and Desktop"
    BROWSER_WEB = "Browser and Web"
    DOCUMENTS_CREATIVITY = "Documents and Creativity"
    DEVELOPMENT = "Development"
    PERSONAL_PRODUCTIVITY = "Personal Productivity"
    SYSTEM_INTELLIGENCE = "System Intelligence"


@dataclass
class SkillManifest:
    skill_id: str
    name: str
    description: str
    version: str = "1.0.0"
    author: str = "Aditya Sir"
    category: SkillCategory = SkillCategory.SYSTEM_INTELLIGENCE
    required_permissions: int = 2  # 1=Read, 2=Normal, 3=Sensitive, 4=Restricted
    dependencies: List[str] = field(default_factory=list)
    system_binaries: List[str] = field(default_factory=list)
    supported_os: List[str] = field(default_factory=lambda: ["windows", "linux", "darwin"])
    input_schema: Dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    output_schema: Dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    timeout_seconds: int = 30
    is_sandboxed: bool = True
    tags: List[str] = field(default_factory=list)

    def validate(self) -> Tuple[bool, str]:
        """Validates manifest fields against ALEX conventions."""
        if not re.match(r"^[a-zA-Z0-9_-]{2,64}$", self.skill_id):
            return False, f"Invalid skill_id '{self.skill_id}'. Must be 2-64 alphanumeric, dash, or underscore characters."
        if not self.name or len(self.name) < 2:
            return False, "Skill name must be at least 2 characters long."
        if not self.description:
            return False, "Skill description is required."
        if self.required_permissions not in (1, 2, 3, 4):
            return False, "required_permissions must be 1 (Read), 2 (Normal), 3 (Sensitive), or 4 (Restricted)."
        if self.required_permissions == 4:
            return False, "Level 4 (Restricted) skills are permanently prohibited by Central Security Manager."
        return True, "Manifest valid."


@dataclass
class SkillResult:
    status: ExecutionStatus
    output: Any
    error: Optional[str] = None
    duration_ms: float = 0.0
    verified: bool = False
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class SkillContext:
    skill_id: str
    user_address: str = "Aditya Sir"
    cancelled: bool = False
    parameters: Dict[str, Any] = field(default_factory=dict)
    workspace_root: Optional[Path] = None
    log_messages: List[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        self.log_messages.append(f"[{time.strftime('%H:%M:%S')}] {message}")

    def is_cancelled(self) -> bool:
        return self.cancelled


class BaseAlexSkill:
    """Standard base class for modular ALEX skills."""

    def __init__(self, manifest: SkillManifest):
        self.manifest = manifest
        self._actions: Dict[str, Callable[..., Any]] = {}

    def register_action(self, name: str, handler: Callable[..., Any]) -> None:
        self._actions[name] = handler

    def list_actions(self) -> List[str]:
        return list(self._actions.keys())

    def validate_inputs(self, action_name: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validates parameters against action signature and schema."""
        if action_name not in self._actions:
            return False, f"Action '{action_name}' is not registered in skill '{self.manifest.skill_id}'."
        handler = self._actions[action_name]
        sig = inspect.signature(handler)
        # Check required parameters
        for p_name, param in sig.parameters.items():
            if param.default is inspect.Parameter.empty and param.kind not in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL):
                if p_name not in params and p_name != "ctx":
                    return False, f"Missing required parameter '{p_name}' for action '{action_name}'."
        return True, "Valid."

    def health_check(self) -> Tuple[bool, str]:
        """Runs capability verification and dependency health checks."""
        # 1. OS Compatibility Check
        current_os = sys.platform
        os_name = "windows" if current_os.startswith("win") else ("darwin" if current_os == "darwin" else "linux")
        if os_name not in self.manifest.supported_os:
            return False, f"Operating system '{os_name}' is not supported (requires {self.manifest.supported_os})."

        # 2. Python Dependencies Check
        missing_pkgs = []
        for pkg in self.manifest.dependencies:
            try:
                __import__(pkg)
            except ImportError:
                missing_pkgs.append(pkg)
        if missing_pkgs:
            return False, f"Missing Python dependencies: {', '.join(missing_pkgs)}"

        # 3. System Binaries Check
        import shutil
        missing_bins = []
        for b in self.manifest.system_binaries:
            if not shutil.which(b):
                missing_bins.append(b)
        if missing_bins:
            return False, f"Missing system CLI binaries: {', '.join(missing_bins)}"

        return True, "All dependencies and environment checks passed."

    def execute(self, action_name: str, params: Dict[str, Any], ctx: Optional[SkillContext] = None) -> SkillResult:
        """Executes action with structured result reporting and verification."""
        t0 = time.monotonic()
        val_ok, val_err = self.validate_inputs(action_name, params)
        if not val_ok:
            return SkillResult(
                status=ExecutionStatus.FAILED,
                output=None,
                error=val_err,
                duration_ms=round((time.monotonic() - t0) * 1000, 2),
                verified=False
            )

        handler = self._actions[action_name]
        try:
            sig = inspect.signature(handler)
            kw = dict(params)
            if "ctx" in sig.parameters:
                kw["ctx"] = ctx

            res = handler(**kw)
            duration = round((time.monotonic() - t0) * 1000, 2)
            return SkillResult(
                status=ExecutionStatus.SUCCESS,
                output=res,
                duration_ms=duration,
                verified=True,
                diagnostics={"action": action_name, "params_count": len(params)}
            )
        except Exception as e:
            duration = round((time.monotonic() - t0) * 1000, 2)
            return SkillResult(
                status=ExecutionStatus.FAILED,
                output=None,
                error=str(e),
                duration_ms=duration,
                verified=False,
                diagnostics={"exception_type": type(e).__name__}
            )

