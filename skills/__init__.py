"""
skills — ALEX Modular Skill System & Unified Skills Engine (Phase 7).

Exports core classes, registries, and SDK components.
"""

from skills.base_skill import BaseSkill, SkillMetadata
from skills.engine import SkillsEngine, skills_engine
from skills.plugin_installer import PluginInstaller, plugin_installer
from skills.registry import SkillRegistry, skill_registry
from skills.sandbox import ExecutionSandbox, sandbox
from skills.sdk import (
    BaseAlexSkill, ExecutionStatus, SkillCategory, SkillContext, SkillManifest,
    SkillResult, SkillStatus
)

__all__ = [
    "BaseSkill",
    "SkillMetadata",
    "SkillRegistry",
    "skill_registry",
    "SkillsEngine",
    "skills_engine",
    "BaseAlexSkill",
    "SkillManifest",
    "SkillResult",
    "SkillContext",
    "SkillStatus",
    "ExecutionStatus",
    "SkillCategory",
    "PluginInstaller",
    "plugin_installer",
    "ExecutionSandbox",
    "sandbox"
]
