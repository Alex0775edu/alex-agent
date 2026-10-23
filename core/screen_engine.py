"""
core/screen_engine.py — Real-Time Screen Understanding & Visual Intelligence Engine for ALEX.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX

Capabilities:
  • Authorized Screen Capture with privacy masking and sensitive window blocking.
  • Foreground & Open Windows Inspection (PID, process name, geometry, responsiveness).
  • UI Elements Semantic Detection (buttons, menus, dialogs, forms, edit boxes).
  • Error Dialog & Crash Message Recognition.
  • Perceptual & Structural Before/After Screen Comparison for Closed-Loop Verification.
  • Genuine truthfulness: NEVER hallucinates screen contents when capture is disabled or unavailable.
"""

from __future__ import annotations

import io
import math
import os
import platform
import re
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from core.privacy_manager import privacy_manager

_IS_WINDOWS = platform.system() == "Windows"

# Optional Windows API imports
try:
    import win32gui
    import win32process
    import win32con
    import ctypes
    _WIN32 = True
except ImportError:
    _WIN32 = False

try:
    import mss
    import mss.tools
    _MSS = True
except ImportError:
    _MSS = False

try:
    import pywinauto
    _PYWINAUTO = True
except ImportError:
    _PYWINAUTO = False


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    process_name: str
    pid: int
    rect: Tuple[int, int, int, int]  # (left, top, right, bottom)
    width: int
    height: int
    is_foreground: bool
    is_responsive: bool
    is_sensitive: bool


@dataclass
class UIElement:
    element_type: str    # "button", "edit", "dialog", "menu", "static", "window"
    title: str
    rect: Tuple[int, int, int, int]
    enabled: bool = True
    visible: bool = True
    automation_id: str = ""


@dataclass
class ScreenComparisonResult:
    has_changed: bool
    difference_score: float   # 0.0 (identical) to 1.0 (completely different)
    summary: str
    before_window: str
    after_window: str


@dataclass
class ErrorDialogInfo:
    is_error_present: bool
    title: str
    message: str
    severity: str             # "CRITICAL", "WARNING", "INFO"
    suggested_action: str


class ScreenEngine:
    """Thread-safe Screen Understanding & Visual Verification Engine."""

    _instance: Optional[ScreenEngine] = None
    _lock = threading.RLock()

    def __init__(self):
        self._last_capture_time: float = 0.0
        self._min_capture_interval: float = 0.2  # Bounded capture rate (max 5 FPS)
        self._last_screenshot: Optional[Image.Image] = None
        self._last_window: Optional[WindowInfo] = None

    @classmethod
    def get_instance(cls) -> ScreenEngine:
        with cls._lock:
            if cls._instance is None:
                cls._instance = ScreenEngine()
            return cls._instance

    # ── Screen Capture & Privacy ─────────────────────────────────────────────

    def capture_screen(
        self,
        max_width: int = 1280,
        max_height: int = 720,
        enforce_privacy: bool = True
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Captures the primary monitor screen as JPEG bytes.
        Returns: (image_bytes, error_message)
        """
        if enforce_privacy:
            if not privacy_manager.is_screen_capture_allowed():
                return None, "Screen capture is disabled by Privacy Settings or paused by Sir."

            # Check if active foreground window is sensitive
            fg = self.get_active_window()
            if fg and privacy_manager.is_window_sensitive(fg.title):
                return None, f"Capture blocked: Active window '{fg.title}' is classified as sensitive."

        # Bounded rate limiting
        now = time.monotonic()
        if now - self._last_capture_time < self._min_capture_interval:
            time.sleep(self._min_capture_interval - (now - self._last_capture_time))
        self._last_capture_time = time.monotonic()

        if not _MSS:
            return None, "Screen capture library (mss) is unavailable on this system."

        try:
            with mss.mss() as sct:
                monitors = sct.monitors
                target = monitors[1] if len(monitors) > 1 else monitors[0]
                shot = sct.grab(target)
                img = Image.frombytes("RGB", shot.size, shot.rgb)

                # Resize if exceeding bounds
                img.thumbnail((max_width, max_height), Image.Resampling.BILINEAR)
                self._last_screenshot = img

                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=80)
                return buf.getvalue(), None
        except Exception as e:
            return None, f"Screen capture failed: {e}"

    # ── Active & Open Windows Telemetry ──────────────────────────────────────

    def get_active_window(self) -> Optional[WindowInfo]:
        """Inspects the current foreground window on Windows with live responsiveness check."""
        if not _IS_WINDOWS or not _WIN32:
            return None

        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None
            return self._inspect_hwnd(hwnd, is_foreground=True)
        except Exception:
            return None

    def enumerate_open_windows(self, include_empty: bool = False) -> List[WindowInfo]:
        """Enumerates all top-level, visible windows on the desktop."""
        if not _IS_WINDOWS or not _WIN32:
            return []

        results: List[WindowInfo] = []
        fg_hwnd = win32gui.GetForegroundWindow() if _WIN32 else 0

        def enum_callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).strip()
                if title or include_empty:
                    rect = win32gui.GetWindowRect(hwnd)
                    width = rect[2] - rect[0]
                    height = rect[3] - rect[1]
                    # Filter out zero-sized hidden utility windows
                    if width > 10 and height > 10:
                        info = self._inspect_hwnd(hwnd, is_foreground=(hwnd == fg_hwnd))
                        if info:
                            results.append(info)
            return True

        try:
            win32gui.EnumWindows(enum_callback, None)
        except Exception:
            pass

        return results

    def _inspect_hwnd(self, hwnd: int, is_foreground: bool = False) -> Optional[WindowInfo]:
        try:
            title = win32gui.GetWindowText(hwnd).strip()
            rect = win32gui.GetWindowRect(hwnd)
            width = max(0, rect[2] - rect[0])
            height = max(0, rect[3] - rect[1])

            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc_name = "unknown"
            try:
                import psutil
                p = psutil.Process(pid)
                proc_name = p.name()
            except Exception:
                pass

            # Check responsiveness via IsHungAppWindow
            is_responsive = True
            try:
                if ctypes.windll.user32.IsHungAppWindow(hwnd):
                    is_responsive = False
            except Exception:
                pass

            is_sens = privacy_manager.is_window_sensitive(title)

            return WindowInfo(
                hwnd=hwnd,
                title=title or "Untitled Window",
                process_name=proc_name,
                pid=pid,
                rect=rect,
                width=width,
                height=height,
                is_foreground=is_foreground,
                is_responsive=is_responsive,
                is_sensitive=is_sens
            )
        except Exception:
            return None

    # ── UI Elements Semantic Identification ──────────────────────────────────

    def detect_ui_elements(self, hwnd: Optional[int] = None) -> List[UIElement]:
        """
        Extracts semantic UI elements (buttons, inputs, menus, text)
        from the specified window or foreground window.
        """
        if not _IS_WINDOWS or not _PYWINAUTO:
            return []

        target_hwnd = hwnd or (win32gui.GetForegroundWindow() if _WIN32 else 0)
        if not target_hwnd:
            return []

        elements: List[UIElement] = []
        try:
            app = pywinauto.Application(backend="uia").connect(handle=target_hwnd, timeout=1.5)
            win = app.window(handle=target_hwnd)
            for ctrl in win.descendants():
                try:
                    c_type = ctrl.friendly_class_name().lower()
                    c_title = ctrl.window_text().strip()
                    c_rect = ctrl.rectangle()
                    rect_tup = (c_rect.left, c_rect.top, c_rect.right, c_rect.bottom)
                    is_vis = ctrl.is_visible()
                    is_en = ctrl.is_enabled()
                    auto_id = getattr(ctrl.element_info, "automation_id", "") or ""

                    # Only keep visible, meaningful controls
                    if is_vis and (c_title or c_type in ("button", "edit", "combobox", "checkbox")):
                        elements.append(UIElement(
                            element_type=c_type,
                            title=c_title,
                            rect=rect_tup,
                            enabled=is_en,
                            visible=is_vis,
                            automation_id=auto_id
                        ))
                except Exception:
                    continue
        except Exception:
            # Fallback to win32 standard child enumeration
            if _WIN32:
                def enum_child(child_hwnd, _):
                    if win32gui.IsWindowVisible(child_hwnd):
                        txt = win32gui.GetWindowText(child_hwnd).strip()
                        cls_name = win32gui.GetClassName(child_hwnd).lower()
                        rect = win32gui.GetWindowRect(child_hwnd)
                        elements.append(UIElement(
                            element_type=cls_name,
                            title=txt,
                            rect=rect,
                            enabled=bool(win32gui.IsWindowEnabled(child_hwnd)),
                            visible=True
                        ))
                    return True
                try:
                    win32gui.EnumChildWindows(target_hwnd, enum_child, None)
                except Exception:
                    pass

        return elements[:50]  # Cap to most relevant 50 controls

    # ── Error Dialog & Alert Recognition ─────────────────────────────────────

    def detect_error_dialog(self) -> ErrorDialogInfo:
        """
        Inspects top-level dialogs for system crashes, error dialogs,
        and unhandled exception alerts.
        """
        windows = self.enumerate_open_windows()
        error_keywords = [
            "error", "exception", "failed", "crash", "not responding",
            "warning", "fatal", "problem", "cannot open", "alert"
        ]

        for w in windows:
            title_lower = w.title.lower()
            if any(k in title_lower for k in error_keywords) or not w.is_responsive:
                # Gather details from window elements
                elements = self.detect_ui_elements(w.hwnd)
                messages = [e.title for e in elements if e.title and len(e.title) > 3 and e.title != w.title]
                msg_body = " | ".join(messages[:3]) if messages else "Dialog appeared indicating an error or warning."

                severity = "CRITICAL" if ("crash" in title_lower or "fatal" in title_lower or not w.is_responsive) else "WARNING"
                suggestion = "Safe close or recover application process." if not w.is_responsive else "Acknowledge dialog or retry with alternative parameters."

                return ErrorDialogInfo(
                    is_error_present=True,
                    title=w.title,
                    message=msg_body,
                    severity=severity,
                    suggested_action=suggestion
                )

        return ErrorDialogInfo(
            is_error_present=False,
            title="",
            message="No visible error dialogs or unresponsive windows detected.",
            severity="INFO",
            suggested_action="Proceed normally."
        )

    # ── Screen Comparison & Closed-Loop Verification ─────────────────────────

    def compare_images(
        self,
        img_before_bytes: bytes,
        img_after_bytes: bytes,
        threshold: float = 0.02
    ) -> ScreenComparisonResult:
        """
        Calculates pixel and perceptual difference between two screenshots.
        Returns difference score (0.0 to 1.0) and whether state changed.
        """
        try:
            im1 = Image.open(io.BytesIO(img_before_bytes)).convert("L")
            im2 = Image.open(io.BytesIO(img_after_bytes)).convert("L")

            # Resize to identical normalized dimensions for fast matrix comparison
            norm_size = (320, 180)
            im1_thumb = np.array(im1.resize(norm_size), dtype=np.float32)
            im2_thumb = np.array(im2.resize(norm_size), dtype=np.float32)

            # Mean Absolute Normalized Pixel Difference
            diff = np.abs(im1_thumb - im2_thumb)
            score = float(np.mean(diff) / 255.0)

            has_changed = score >= threshold
            summary = f"Screen change detected: difference magnitude {score:.3f}" if has_changed else f"Screen remained static (diff: {score:.3f})"

            return ScreenComparisonResult(
                has_changed=has_changed,
                difference_score=round(score, 4),
                summary=summary,
                before_window="Observed initial state",
                after_window="Observed updated state"
            )
        except Exception as e:
            return ScreenComparisonResult(
                has_changed=False,
                difference_score=0.0,
                summary=f"Comparison failed: {e}",
                before_window="Error",
                after_window="Error"
            )

    def verify_action_effect(
        self,
        before_shot: Optional[bytes],
        after_shot: Optional[bytes],
        expected_change: bool = True
    ) -> Tuple[bool, str]:
        """
        Validates whether a computer control action produced a measurable change on screen.
        """
        if not before_shot or not after_shot:
            return True, "One or both screenshots unavailable; visual verification bypassed."

        res = self.compare_images(before_shot, after_shot)
        if expected_change and res.has_changed:
            return True, f"Action verified: Screen state changed successfully (diff={res.difference_score:.3f})."
        elif expected_change and not res.has_changed:
            return False, f"Action verification failed: No visual change detected on screen (diff={res.difference_score:.3f})."
        else:
            return True, f"Visual state verified (diff={res.difference_score:.3f})."


screen_engine = ScreenEngine.get_instance()

