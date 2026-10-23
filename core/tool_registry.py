"""
core/tool_registry.py — Shared Tool Selection Intelligence & Capability Registry for ALEX.

Owner: Aditya Rajak
Salutation: Sir / Aditya Sir
Assistant: ALEX

Implements Phase 2 Requirement 5:
  • Declares a centralized catalog of all available tools and capabilities.
  • Exposes: name, purpose, input schema, required permissions, dependencies,
    timeout, output format, error handling strategy, verification method.
  • Performs strict availability pre-flight checks before tool selection.
  • Missing Dependency Honesty: If Blender, FFmpeg, Playwright, or an external model
    is missing, explicitly explains the limitation and provides a safe setup/installation
    path instead of pretending the capability exists.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass
class ToolDefinition:
    name: str
    purpose: str
    input_schema: Dict[str, Any]
    required_permissions: str  # SAFE, CONFIRM, CRITICAL
    dependencies: List[str]    # Python packages required
    system_binaries: List[str] # System executables required (e.g. ffmpeg, blender, git)
    timeout_seconds: int
    output_format: str
    error_handling: str        # RETRY, FALLBACK, ABORT, APPROVAL
    verification_method: str   # file_exists, exit_zero, syntax_check, process_running, none
    fallback_tool: Optional[str] = None
    install_guidance: Dict[str, str] = field(default_factory=dict)
    handler: Optional[Callable[..., Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("handler", None)
        return d


class ToolRegistry:
    """Shared registry of available tools with availability pre-flight verification."""

    _instance: Optional[ToolRegistry] = None

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_default_tools()

    @classmethod
    def get_instance(cls) -> ToolRegistry:
        if cls._instance is None:
            cls._instance = ToolRegistry()
        return cls._instance

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in self._tools.values()]

    def check_availability(self, tool_name: str) -> Tuple[bool, str, Optional[Dict[str, str]]]:
        """Validates that a tool's required dependencies and system binaries actually exist.

        Returns (is_available, status_message, install_guidance).
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return False, f"Tool '{tool_name}' is not registered in the tool catalog.", None

        missing_pkgs = []
        for pkg in tool.dependencies:
            try:
                importlib.import_module(pkg)
            except ImportError:
                missing_pkgs.append(pkg)

        missing_bins = []
        for b in tool.system_binaries:
            if not shutil.which(b):
                missing_bins.append(b)

        if missing_pkgs or missing_bins:
            reasons = []
            if missing_pkgs:
                reasons.append(f"Missing Python package(s): {', '.join(missing_pkgs)}")
            if missing_bins:
                reasons.append(f"Missing system binary(ies): {', '.join(missing_bins)}")
            
            detail = " | ".join(reasons)
            msg = (
                f"Tool '{tool_name}' is currently unavailable on this system ({detail}). "
                f"ALEX cannot execute this action until dependencies are installed."
            )
            return False, msg, tool.install_guidance

        return True, f"Tool '{tool_name}' is verified and ready for execution.", None

    def select_best_tool(self, intent: str, required_capability: str) -> Tuple[Optional[ToolDefinition], str]:
        """Selects the best available tool for an intent or resolves its fallback."""
        candidates = [t for t in self._tools.values() if required_capability.lower() in t.purpose.lower() or required_capability.lower() in t.name.lower()]
        if not candidates:
            return None, f"No registered tool matches capability '{required_capability}'."

        primary = candidates[0]
        avail, msg, guidance = self.check_availability(primary.name)
        if avail:
            return primary, msg

        # Attempt fallback tool if defined
        if primary.fallback_tool:
            fallback = self.get_tool(primary.fallback_tool)
            if fallback:
                fb_avail, fb_msg, _ = self.check_availability(fallback.name)
                if fb_avail:
                    return fallback, f"Primary tool '{primary.name}' unavailable ({msg}). Routed to fallback '{fallback.name}'."

        return None, msg

    def _register_default_tools(self) -> None:
        """Populates the comprehensive system tool catalog."""
        # 1. Python Syntax & AST Verifier
        self.register(ToolDefinition(
            name="python_syntax_verifier",
            purpose="Validates Python syntax and structure via AST parsing without execution.",
            input_schema={"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]},
            required_permissions="SAFE",
            dependencies=[],
            system_binaries=[],
            timeout_seconds=5,
            output_format="dict",
            error_handling="ABORT",
            verification_method="syntax_check"
        ))

        # 2. Automated Test Runner
        self.register(ToolDefinition(
            name="test_runner",
            purpose="Executes pytest or unittest test suites in authorized project directories.",
            input_schema={"type": "object", "properties": {"project_root": {"type": "string"}, "target_test": {"type": "string"}}},
            required_permissions="NORMAL",
            dependencies=[],
            system_binaries=["python"],
            timeout_seconds=60,
            output_format="dict",
            error_handling="RETRY",
            verification_method="exit_zero"
        ))

        # 3. Code Change & Bug Fixer
        self.register(ToolDefinition(
            name="safe_code_fixer",
            purpose="Applies surgical bug fixes with pre-execution checkpointing and auto-rollback.",
            input_schema={"type": "object", "properties": {"file_path": {"type": "string"}, "patch_content": {"type": "string"}}, "required": ["file_path"]},
            required_permissions="CONFIRM",
            dependencies=[],
            system_binaries=[],
            timeout_seconds=15,
            output_format="dict",
            error_handling="FALLBACK",
            verification_method="syntax_check"
        ))

        # 4. Universal Document Engine (DOCX / Markdown)
        self.register(ToolDefinition(
            name="document_engine",
            purpose="Generates professional formatted documents (DOCX, HTML, Markdown).",
            input_schema={"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}, "format": {"type": "string"}}, "required": ["title"]},
            required_permissions="SAFE",
            dependencies=["docx"],
            system_binaries=[],
            timeout_seconds=30,
            output_format="file_path",
            error_handling="FALLBACK",
            verification_method="file_exists",
            fallback_tool="markdown_document_writer",
            install_guidance={"pip": "pip install python-docx"}
        ))

        # 5. Markdown Fallback Writer
        self.register(ToolDefinition(
            name="markdown_document_writer",
            purpose="Creates clean Markdown documents when native DOCX libraries are absent.",
            input_schema={"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}}, "required": ["title"]},
            required_permissions="SAFE",
            dependencies=[],
            system_binaries=[],
            timeout_seconds=5,
            output_format="file_path",
            error_handling="ABORT",
            verification_method="file_exists"
        ))

        # 6. Presentation Builder (PPTX)
        self.register(ToolDefinition(
            name="presentation_builder",
            purpose="Creates widescreen slide presentations (PPTX).",
            input_schema={"type": "object", "properties": {"title": {"type": "string"}, "slides": {"type": "array"}}, "required": ["title"]},
            required_permissions="SAFE",
            dependencies=["pptx"],
            system_binaries=[],
            timeout_seconds=30,
            output_format="file_path",
            error_handling="ABORT",
            verification_method="file_exists",
            install_guidance={"pip": "pip install python-pptx"}
        ))

        # 7. Spreadsheet Studio (XLSX / CSV)
        self.register(ToolDefinition(
            name="spreadsheet_studio",
            purpose="Creates and audits Excel spreadsheets and CSV datasets with automated formulas.",
            input_schema={"type": "object", "properties": {"title": {"type": "string"}, "data": {"type": "array"}}, "required": ["title"]},
            required_permissions="SAFE",
            dependencies=["openpyxl"],
            system_binaries=[],
            timeout_seconds=30,
            output_format="file_path",
            error_handling="FALLBACK",
            verification_method="file_exists",
            fallback_tool="csv_data_writer",
            install_guidance={"pip": "pip install openpyxl"}
        ))

        # 8. CSV Data Writer (Fallback)
        self.register(ToolDefinition(
            name="csv_data_writer",
            purpose="Generates tabular CSV data when Excel libraries are absent.",
            input_schema={"type": "object", "properties": {"title": {"type": "string"}, "data": {"type": "array"}}, "required": ["title"]},
            required_permissions="SAFE",
            dependencies=[],
            system_binaries=[],
            timeout_seconds=5,
            output_format="file_path",
            error_handling="ABORT",
            verification_method="file_exists"
        ))

        # 9. 3D Studio (Universal Wavefront OBJ / STL)
        self.register(ToolDefinition(
            name="threed_studio",
            purpose="Generates 3D meshes (OBJ, STL) for product prototypes and visualization.",
            input_schema={"type": "object", "properties": {"model_name": {"type": "string"}, "primitive_type": {"type": "string"}}, "required": ["model_name"]},
            required_permissions="SAFE",
            dependencies=[],
            system_binaries=[],
            timeout_seconds=20,
            output_format="file_path",
            error_handling="ABORT",
            verification_method="file_exists"
        ))

        # 10. Advanced 3D Blender Modeler (Requires Blender Binary)
        self.register(ToolDefinition(
            name="blender_modeler",
            purpose="Renders photorealistic 3D assets and animations via Blender background script.",
            input_schema={"type": "object", "properties": {"script_path": {"type": "string"}}, "required": ["script_path"]},
            required_permissions="NORMAL",
            dependencies=[],
            system_binaries=["blender"],
            timeout_seconds=120,
            output_format="file_path",
            error_handling="FALLBACK",
            verification_method="file_exists",
            fallback_tool="threed_studio",
            install_guidance={
                "winget": "winget install BlenderFoundation.Blender",
                "manual": "Download from https://www.blender.org/download/"
            }
        ))

        # 11. Video Production Studio (Requires FFmpeg)
        self.register(ToolDefinition(
            name="video_processor",
            purpose="Transcodes, crops, and stitches video streams using FFmpeg.",
            input_schema={"type": "object", "properties": {"input_file": {"type": "string"}, "output_file": {"type": "string"}}, "required": ["input_file"]},
            required_permissions="NORMAL",
            dependencies=[],
            system_binaries=["ffmpeg"],
            timeout_seconds=180,
            output_format="file_path",
            error_handling="ABORT",
            verification_method="file_exists",
            install_guidance={
                "winget": "winget install Gyan.FFmpeg",
                "manual": "Download FFmpeg from https://ffmpeg.org/download.html and add to PATH."
            }
        ))

        # 12. Desktop UI & Computer Control
        self.register(ToolDefinition(
            name="computer_control",
            purpose="Executes verified desktop operations with closed-loop screen verification.",
            input_schema={"type": "object", "properties": {"action_type": {"type": "string"}, "target": {"type": "string"}}, "required": ["action_type"]},
            required_permissions="SAFE",
            dependencies=["pyautogui"],
            system_binaries=[],
            timeout_seconds=15,
            output_format="dict",
            error_handling="RETRY",
            verification_method="screen_verified"
        ))

        # 13. Web Browser Agent
        self.register(ToolDefinition(
            name="browser_agent",
            purpose="Navigates web pages, searches, and extracts research information.",
            input_schema={"type": "object", "properties": {"url": {"type": "string"}, "action": {"type": "string"}}, "required": ["url"]},
            required_permissions="SAFE",
            dependencies=[],
            system_binaries=[],
            timeout_seconds=30,
            output_format="dict",
            error_handling="RETRY",
            verification_method="none"
        ))


tool_registry = ToolRegistry.get_instance()

