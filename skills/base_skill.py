"""
skills/base_skill.py — Base class and interface for ALEX Modular Skill System.

Every skill provides:
  • metadata: name, version, description, risk_level
  • permissions: required security clearance
  • actions: mapping of action names to callable methods
  • validate: parameter & precondition check
  • execute: runs action with verification & error handling

Owner: Aditya Rajak
Salutation: Aditya Sir
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple


@dataclass
class SkillMetadata:
    name: str
    version: str
    description: str
    risk_level: str  # SAFE, CONFIRM, CRITICAL
    category: str


class BaseSkill:
    """Abstract base class for all ALEX skills."""

    def __init__(self, metadata: SkillMetadata):
        self.metadata = metadata
        self._actions: Dict[str, Callable[..., Any]] = {}

    def register_action(self, name: str, fn: Callable[..., Any]) -> None:
        self._actions[name] = fn

    def list_actions(self) -> Dict[str, str]:
        return {name: (fn.__doc__ or "").strip().split("\n")[0] for name, fn in self._actions.items()}

    def validate(self, action_name: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        if action_name not in self._actions:
            return False, f"Action '{action_name}' not found in skill '{self.metadata.name}'."
        return True, "Valid"

    def execute(self, action_name: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Any:
        valid, msg = self.validate(action_name, params)
        if not valid:
            return f"Validation error: {msg}"
        try:
            fn = self._actions[action_name]
            return fn(**params)
        except Exception as e:
            return f"Error executing {self.metadata.name}.{action_name}: {e}"
