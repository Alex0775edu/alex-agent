"""
plugins/sample_text_toolkit.py — Reference Plugin Demonstrating ALEX SDK & BaseAlexSkill.

Demonstrates:
  • SkillManifest declaration with Category, Permissions, Input/Output Schemas
  • BaseAlexSkill inheritance and action registration
  • Input validation and execution lifecycle
  • Safe sandboxed string manipulation tools
  • Outcome verification and diagnostics

Owner: Aditya Rajak
Salutation: Aditya Sir / Sir
Assistant: ALEX
"""

from __future__ import annotations

import codecs
from typing import Any, Dict, Optional

from skills.sdk import (
    BaseAlexSkill, ExecutionStatus, SkillCategory, SkillContext, SkillManifest,
    SkillResult
)


class SampleTextToolkit(BaseAlexSkill):
    """Reference text transformation toolkit for ALEX workstation."""

    def __init__(self):
        manifest = SkillManifest(
            skill_id="sample_text_toolkit",
            name="Sample Text Toolkit",
            description="Provides utilities for text metrics, ROT13 encryption, casing, and string reversal.",
            version="1.0.0",
            author="Aditya Sir",
            category=SkillCategory.DEVELOPMENT,
            required_permissions=2,  # Normal permission
            dependencies=[],
            tags=["text", "metrics", "rot13", "formatting"],
            input_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["word_count", "reverse", "rot13", "change_case"]},
                    "text": {"type": "string"}
                },
                "required": ["text"]
            }
        )
        super().__init__(manifest)

        # Register distinct actions
        self.register_action("word_count", self.word_count)
        self.register_action("reverse", self.reverse_text)
        self.register_action("rot13", self.rot13)
        self.register_action("change_case", self.change_case)

    def word_count(self, text: str, **kwargs) -> Dict[str, Any]:
        """Calculates line, word, and character metrics."""
        return {
            "characters": len(text),
            "words": len(text.split()),
            "lines": len(text.splitlines()) if text else 0
        }

    def reverse_text(self, text: str, **kwargs) -> str:
        """Reverses the provided text sequence."""
        return text[::-1]

    def rot13(self, text: str, **kwargs) -> str:
        """Applies Caesar cipher ROT13 to text."""
        return codecs.encode(text, "rot_13")

    def change_case(self, text: str, mode: str = "upper", **kwargs) -> str:
        """Changes casing of text (upper, lower, title, capitalize)."""
        mode_lower = mode.lower()
        if mode_lower == "upper":
            return text.upper()
        elif mode_lower == "lower":
            return text.lower()
        elif mode_lower == "title":
            return text.title()
        elif mode_lower == "capitalize":
            return text.capitalize()
        return text

    def run(self, parameters: Dict[str, Any], ctx: Optional[SkillContext] = None) -> Any:
        """Unified entrypoint dispatching action or default word_count."""
        action = parameters.get("action", "word_count")
        text = parameters.get("text", "")
        if action == "word_count":
            return self.word_count(text)
        elif action == "reverse":
            return self.reverse_text(text)
        elif action == "rot13":
            return self.rot13(text)
        elif action == "change_case":
            mode = parameters.get("mode", "upper")
            return self.change_case(text, mode=mode)
        else:
            return f"Unknown action '{action}'. Available: word_count, reverse, rot13, change_case."


# Instance & Manifest exports for ALEX Skills Engine & Plugin Loader
SKILL = SampleTextToolkit()
MANIFEST = SKILL.manifest


def run(parameters: Dict[str, Any], player=None, session_memory=None) -> str:
    """Standard fallback entrypoint for legacy plugin runner."""
    text = parameters.get("text", "")
    action = parameters.get("action", "word_count")
    res = SKILL.run(parameters)
    return f"Text Toolkit Result ({action}): {res}"

