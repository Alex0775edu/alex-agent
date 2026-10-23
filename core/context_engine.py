"""
core/context_engine.py — Multi-Layered Context Engine & Reference Resolver for ALEX 3.0.

Owner: Aditya Rajak
Salutation: Aditya Sir

Layers:
  1. Immediate Context: Current turn and immediate user utterance.
  2. Task Context: Active task goal, current step, and parameters.
  3. Session Context: Conversation history, active topics, referenced files/URLs.
  4. Project Context: Active workspace (SkillSum, E-Baal Seva, EMS, Personal).
  5. User Context: Owner identity, preferences, authorization clearance.
  6. Environmental Context: OS, active window, clipboard, network, system telemetry.

Features:
  • Reference Resolution: Resolves pronouns ("isse", "isko", "ye", "this", "it")
    to the active file, clipboard content, or recent subject.
"""

from __future__ import annotations

import os
import platform
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil
from core.project_manager import project_manager
from core.security import OWNER_ADDRESS, OWNER_NAME, security_manager


@dataclass
class EnvironmentalContext:
    os_name: str
    active_window: str
    clipboard_preview: str
    network_state: str   # "ONLINE", "LIMITED", "OFFLINE"
    cpu_percent: float
    ram_percent: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class ContextSnapshot:
    immediate_query: str
    resolved_query: str
    active_project: str
    last_referenced_file: Optional[str]
    last_referenced_url: Optional[str]
    last_topic: Optional[str]
    auth_level: int
    environment: EnvironmentalContext


class ContextEngine:
    _instance: Optional[ContextEngine] = None
    _lock = threading.Lock()

    def __init__(self):
        self._history: List[Dict[str, Any]] = []
        self._last_referenced_file: Optional[str] = None
        self._last_referenced_url: Optional[str] = None
        self._last_topic: Optional[str] = None
        self._last_image_file: Optional[str] = None
        self._last_presentation_file: Optional[str] = None
        self._last_code_file: Optional[str] = None
        self._last_output_dir: Optional[str] = str(Path(__file__).resolve().parent.parent / "memory" / "artifacts")
        self._last_bug: Optional[Dict[str, Any]] = None
        self._recent_entities: List[str] = []

    @classmethod
    def get_instance(cls) -> ContextEngine:
        with cls._lock:
            if cls._instance is None:
                cls._instance = ContextEngine()
            return cls._instance

    def record_turn(self, speaker: str, text: str, meta: Optional[Dict[str, Any]] = None) -> None:
        """Stores turn and extracts referenced files, urls, and entities."""
        entry = {
            "speaker": speaker,
            "text": text,
            "meta": meta or {},
            "timestamp": time.time()
        }
        self._history.append(entry)
        if len(self._history) > 50:
            self._history.pop(0)

        # Detect files / extensions in text
        words = text.split()
        for w in words:
            clean = w.strip(" '\".,;:()")
            lower = clean.lower()
            if any(lower.endswith(ext) for ext in (".pdf", ".docx", ".py", ".html", ".txt", ".png", ".jpg", ".jpeg", ".csv", ".pptx")):
                self.set_last_file(clean)
            elif clean.startswith("http://") or clean.startswith("https://"):
                self._last_referenced_url = clean

    def set_last_file(self, file_path: str) -> None:
        self._last_referenced_file = file_path
        lower = file_path.lower()
        if lower.endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp")):
            self._last_image_file = file_path
        elif lower.endswith(".pptx"):
            self._last_presentation_file = file_path
        elif lower.endswith((".py", ".js", ".ts", ".html", ".css", ".java", ".cpp")):
            self._last_code_file = file_path

        p = Path(file_path)
        if p.parent.exists():
            self._last_output_dir = str(p.parent)

    def set_last_image(self, img_path: str) -> None:
        self._last_image_file = img_path
        self.set_last_file(img_path)

    def set_last_presentation(self, pptx_path: str) -> None:
        self._last_presentation_file = pptx_path
        self.set_last_file(pptx_path)

    def set_last_bug(self, bug_info: Dict[str, Any]) -> None:
        self._last_bug = bug_info

    def set_last_output_dir(self, dir_path: str) -> None:
        self._last_output_dir = dir_path

    def set_last_url(self, url: str) -> None:
        self._last_referenced_url = url

    def set_last_topic(self, topic: str) -> None:
        self._last_topic = topic

    def get_active_window_title(self) -> str:
        """Captures title of foreground window on Windows with zero external dlls."""
        if platform.system() != "Windows":
            return "Desktop"
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            return buff.value or "Desktop"
        except Exception:
            return "Windows Desktop"

    def get_clipboard_text(self) -> str:
        """Safely inspects clipboard without blocking."""
        try:
            import win32clipboard  # type: ignore
            win32clipboard.OpenClipboard()
            data = ""
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            return str(data).strip()
        except Exception:
            pass
        return ""

    def get_environmental_context(self) -> EnvironmentalContext:
        """Collects current local system telemetry and context."""
        net = "ONLINE"
        try:
            import socket
            s = socket.create_connection(("8.8.8.8", 53), timeout=1.0)
            s.close()
        except Exception:
            net = "OFFLINE"

        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        clip = self.get_clipboard_text()
        clip_preview = (clip[:80] + "...") if len(clip) > 80 else clip
        win_title = self.get_active_window_title()

        return EnvironmentalContext(
            os_name=platform.platform(),
            active_window=win_title,
            clipboard_preview=clip_preview,
            network_state=net,
            cpu_percent=cpu,
            ram_percent=ram
        )

    def resolve_references(self, query: str) -> Tuple[str, Dict[str, Any]]:
        """Resolves anaphoric expressions and context-aware follow-up commands.

        Handles:
          • 'Isko aur professional banao'
          • 'Ab PDF bhi bana do'
          • 'Pichhle design ka background change karo'
          • 'Jo bug mila tha, use fix karo'
          • 'Usi project ko run karo'
          • 'Last output folder kholo'
        """
        q = query.strip()
        q_lower = q.lower()
        resolved = q
        meta: Dict[str, Any] = {}

        # ── 1. Specialized Follow-Up Command Handlers ─────────────────────────
        if "aur professional banao" in q_lower or "professional bana" in q_lower:
            target = self._last_presentation_file or self._last_referenced_file or self._last_code_file
            meta["follow_up_action"] = "ENHANCE_QUALITY"
            meta["resolved_target"] = target
            meta["target_type"] = "document" if target and target.endswith((".pptx", ".docx")) else "code"
            resolved = f"Enhance and make professional: {target or 'active project'}"
            return resolved, meta

        if "pdf bhi bana" in q_lower or "pdf bana do" in q_lower:
            target = self._last_presentation_file or self._last_referenced_file
            meta["follow_up_action"] = "CONVERT_TO_PDF"
            meta["resolved_target"] = target
            meta["target_type"] = "presentation" if target and target.endswith(".pptx") else "document"
            resolved = f"Convert {target or 'last document'} to PDF"
            return resolved, meta

        if "design ka background" in q_lower or "background change" in q_lower:
            target = self._last_image_file or self._last_referenced_file
            meta["follow_up_action"] = "CHANGE_BACKGROUND"
            meta["resolved_target"] = target
            meta["target_type"] = "image"
            resolved = f"Change background of image: {target or 'last design'}"
            return resolved, meta

        if "jo bug mila tha" in q_lower or ("bug" in q_lower and ("fix karo" in q_lower or "theek karo" in q_lower)):
            target = self._last_bug or {"description": "Recent project bug", "project": project_manager.get_active_project()}
            meta["follow_up_action"] = "FIX_BUG"
            meta["resolved_target"] = target
            meta["target_type"] = "bug"
            resolved = f"Fix identified bug in project {project_manager.get_active_project()}"
            return resolved, meta

        if "usi project ko run karo" in q_lower or ("project run karo" in q_lower and ("usi" in q_lower or "wahi" in q_lower)):
            active_p = project_manager.get_active_project()
            meta["follow_up_action"] = "RUN_PROJECT"
            meta["resolved_target"] = active_p
            meta["target_type"] = "project"
            resolved = f"Run active project {active_p}"
            return resolved, meta

        if "last output folder" in q_lower or "output folder kholo" in q_lower or "artifacts folder" in q_lower:
            out_d = self._last_output_dir or str(Path(__file__).resolve().parent.parent / "memory" / "artifacts")
            meta["follow_up_action"] = "OPEN_FOLDER"
            meta["resolved_target"] = out_d
            meta["target_type"] = "directory"
            resolved = f"Open output folder: {out_d}"
            return resolved, meta

        # ── 2. General Pronoun Reference Resolution ───────────────────────────
        pronoun_triggers = [
            "isse", "iska", "iski", "iske", "isko", "ye", "yeh",
            "this", "it", "that", "these", "file"
        ]

        needs_resolution = any(
            f" {p} " in f" {q.lower()} " or q.lower().startswith(f"{p} ")
            for p in pronoun_triggers
        )

        if needs_resolution:
            # 1. Check if user is referencing a recent file
            if self._last_referenced_file:
                target = self._last_referenced_file
                meta["resolved_target"] = target
                meta["target_type"] = "file"
                # If command asks for summary or open without explicit name
                for p in ["iska summary", "isko explain", "isse open karo", "isko open karo", "isse kholo", "isko kholo"]:
                    if p in q.lower():
                        resolved = q.lower().replace("iska", target).replace("isko", target).replace("isse", target)
                        break

            # 2. Check if referencing clipboard
            elif "clipboard" in q.lower() or "jo copy kiya" in q.lower():
                clip = self.get_clipboard_text()
                if clip:
                    meta["resolved_target"] = clip
                    meta["target_type"] = "clipboard"

            # 3. Check active window title
            else:
                win = self.get_active_window_title()
                meta["active_window"] = win

        return resolved, meta

    def clarify_if_ambiguous(self, candidates: List[str], entity_type: str = "item") -> Tuple[bool, Optional[str]]:
        """
        Generates a concise clarification question if multiple plausible targets exist.
        """
        if len(candidates) > 1:
            opts = " ya ".join([f"'{c}'" for c in candidates[:2]])
            return True, f"Sir, kya aap {opts} ke bare mein baat kar rahe hain?"
        return False, None

    def get_snapshot(self, current_query: str = "") -> ContextSnapshot:
        resolved, meta = self.resolve_references(current_query)
        env = self.get_environmental_context()
        active_proj = project_manager.get_active_project()
        auth = security_manager.get_auth_level()

        return ContextSnapshot(
            immediate_query=current_query,
            resolved_query=resolved,
            active_project=active_proj,
            last_referenced_file=self._last_referenced_file,
            last_referenced_url=self._last_referenced_url,
            last_topic=self._last_topic,
            auth_level=auth,
            environment=env
        )


context_engine = ContextEngine.get_instance()

