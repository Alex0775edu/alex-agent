"""
core/app_adapters.py — Desktop Application Intelligence & Adapters for ALEX.

Owner: Aditya Rajak
Salutation: Aditya Sir / Sir
Assistant: ALEX

Provides structured, API, CLI, and COM-driven interaction with desktop applications:
  • Microsoft PowerPoint (Native App, Presentation Builder, COM export to PDF)
  • Microsoft Word (Native App, Document Generation, COM export to PDF)
  • Microsoft Excel (Native App, Spreadsheet Studio, Formula/Data Analysis)
  • Microsoft Outlook (Native App, COM automation, Email Composer)
  • OneNote & Microsoft Access (Native App detection and launcher)
  • Blender 3D (Native App, Headless Scripting, 3D Mesh & Rendering)
  • Visual Studio Code (CLI / Native Editor / Workspace Integration)
  • Google Chrome & Microsoft Edge (Web Browsers)
  • Windows File Explorer & Terminal
  • VLC Media Player & System Notepad
  • Image Editors (Photoshop, Paint, GIMP)
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil

_IS_WINDOWS = platform.system() == "Windows"

if _IS_WINDOWS:
    try:
        import winreg
    except ImportError:
        winreg = None
else:
    winreg = None


def find_windows_app_path(binary_name: str) -> Optional[str]:
    """
    Robustly discovers application path on Windows via:
    1. shutil.which (PATH lookup)
    2. Windows Registry App Paths (HKLM, HKCU, WOW6432Node)
    3. Standard Program Files and LocalAppData directories
    """
    found = shutil.which(binary_name)
    if found:
        return found

    if not _IS_WINDOWS or winreg is None:
        return None

    clean_name = binary_name if binary_name.lower().endswith(".exe") else f"{binary_name}.exe"
    reg_roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\\" + clean_name),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\\" + clean_name),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\\" + clean_name),
    ]
    for root_key, sub_key in reg_roots:
        try:
            with winreg.OpenKey(root_key, sub_key) as key:
                val, _ = winreg.QueryValueEx(key, "")
                if val:
                    val_str = str(val).strip('"')
                    if Path(val_str).exists():
                        return val_str
        except Exception:
            pass

    # Standard well-known directories fallback
    prog_roots = [
        os.environ.get("PROGRAMFILES", "C:\\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    for root in prog_roots:
        if not root or not Path(root).exists():
            continue
        direct_target = Path(root) / clean_name
        if direct_target.exists():
            return str(direct_target)

    return None


@dataclass
class AppStatus:
    name: str
    installed: bool
    running: bool
    path: Optional[str] = None
    pid: Optional[int] = None
    is_responsive: bool = True
    details: str = ""
    capabilities: List[str] = field(default_factory=list)
    integration_level: str = "Launch & Scripting"


class BaseAppAdapter(ABC):
    """Abstract base class for all desktop application adapters."""

    def __init__(self, name: str, binary_names: List[str], capabilities: Optional[List[str]] = None):
        self.name = name
        self.binary_names = binary_names
        self.capabilities = capabilities or ["launch", "process_monitoring"]

    def get_binary_path(self) -> Optional[str]:
        """Locates the application binary via PATH, registry, or standard installation dirs."""
        for b in self.binary_names:
            p = find_windows_app_path(b)
            if p:
                return p
        return None

    def is_installed(self) -> bool:
        return self.get_binary_path() is not None

    def get_running_process(self) -> Optional[psutil.Process]:
        base_targets = {Path(b).name.lower() for b in self.binary_names}
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pname = (proc.info["name"] or "").lower()
                if pname in base_targets or any(t.replace(".exe", "") == pname.replace(".exe", "") for t in base_targets):
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def is_running(self) -> bool:
        return self.get_running_process() is not None

    def is_responsive(self) -> bool:
        proc = self.get_running_process()
        if not proc:
            return False
        try:
            status = proc.status()
            return status not in (psutil.STATUS_STOPPED, psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD)
        except Exception:
            return False

    def get_status(self) -> AppStatus:
        installed = self.is_installed()
        bin_path = self.get_binary_path()
        proc = self.get_running_process()
        running = proc is not None
        pid = proc.pid if proc else None
        responsive = self.is_responsive() if running else True

        details = "Ready" if installed else "Not installed or not registered in Windows App Paths."
        if running:
            details = f"Running (PID: {pid})" if responsive else "Running (Unresponsive)"

        return AppStatus(
            name=self.name,
            installed=installed,
            running=running,
            path=bin_path,
            pid=pid,
            is_responsive=responsive,
            details=details,
            capabilities=self.capabilities,
            integration_level="Task & Automation" if installed else "Unavailable"
        )

    @abstractmethod
    def launch(self, target: Optional[str] = None) -> Tuple[bool, str]:
        """Launches the application with an optional target (file, URL, directory)."""
        pass

    def close(self) -> Tuple[bool, str]:
        proc = self.get_running_process()
        if not proc:
            return True, f"{self.name} is not currently running."
        try:
            proc.terminate()
            return True, f"{self.name} terminated successfully."
        except Exception as e:
            return False, f"Failed to terminate {self.name}: {e}"


# ── Office Adapters ──────────────────────────────────────────────────────────

class PowerPointAdapter(BaseAppAdapter):
    def __init__(self):
        super().__init__(
            "Microsoft PowerPoint",
            ["powerpnt.exe", "powerpnt"],
            capabilities=["create_presentation", "view_presentation", "export_pdf", "com_automation"]
        )

    def launch(self, target: Optional[str] = None) -> Tuple[bool, str]:
        bin_path = self.get_binary_path()
        if bin_path:
            cmd = [bin_path]
            if target:
                cmd.append(str(Path(target).resolve()))
            try:
                subprocess.Popen(cmd)
                return True, f"Microsoft PowerPoint launched successfully{' with file: ' + target if target else ''}."
            except Exception as e:
                return False, f"Could not launch PowerPoint via binary: {e}"

        # Fallback to os.startfile on Windows
        if target and Path(target).exists() and _IS_WINDOWS:
            try:
                os.startfile(str(Path(target).resolve()))
                return True, f"Opened presentation '{target}' with default viewer."
            except Exception as e:
                return False, f"Could not open presentation: {e}"

        return False, "Microsoft PowerPoint is not installed on this system."

    def export_to_pdf(self, pptx_path: str, output_pdf_path: Optional[str] = None) -> Tuple[bool, str]:
        """Exports a .pptx file to .pdf using native PowerPoint COM automation."""
        p_in = Path(pptx_path).resolve()
        if not p_in.exists():
            return False, f"Presentation file not found: {pptx_path}"

        p_out = Path(output_pdf_path).resolve() if output_pdf_path else p_in.with_suffix(".pdf")

        try:
            import win32com.client
            ppt = win32com.client.Dispatch("PowerPoint.Application")
            ppt.Visible = 1
            deck = ppt.Presentations.Open(str(p_in), WithWindow=False)
            deck.SaveAs(str(p_out), 32)  # 32 = ppSaveAsPDF
            deck.Close()
            ppt.Quit()
            if p_out.exists() and p_out.stat().st_size > 0:
                return True, f"Exported presentation to PDF: {p_out}"
            return False, "PowerPoint COM export completed but output PDF was not found."
        except Exception as e:
            return False, f"PowerPoint COM PDF export error: {e}"


class WordAdapter(BaseAppAdapter):
    def __init__(self):
        super().__init__(
            "Microsoft Word",
            ["winword.exe", "winword"],
            capabilities=["create_document", "edit_document", "export_pdf", "com_automation"]
        )

    def launch(self, target: Optional[str] = None) -> Tuple[bool, str]:
        bin_path = self.get_binary_path()
        if bin_path:
            cmd = [bin_path]
            if target:
                cmd.append(str(Path(target).resolve()))
            try:
                subprocess.Popen(cmd)
                return True, f"Microsoft Word launched successfully{' with file: ' + target if target else ''}."
            except Exception as e:
                return False, f"Could not launch Word via binary: {e}"

        if target and Path(target).exists() and _IS_WINDOWS:
            try:
                os.startfile(str(Path(target).resolve()))
                return True, f"Opened document '{target}' with default word processor."
            except Exception as e:
                return False, f"Could not open document: {e}"

        return False, "Microsoft Word is not installed on this system."

    def export_to_pdf(self, docx_path: str, output_pdf_path: Optional[str] = None) -> Tuple[bool, str]:
        """Exports a .docx file to .pdf using native Word COM automation."""
        p_in = Path(docx_path).resolve()
        if not p_in.exists():
            return False, f"Word document not found: {docx_path}"

        p_out = Path(output_pdf_path).resolve() if output_pdf_path else p_in.with_suffix(".pdf")

        try:
            import win32com.client
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            doc = word.Documents.Open(str(p_in))
            doc.ExportAsFixedFormat(str(p_out), 17)  # 17 = wdExportFormatPDF
            doc.Close(False)
            word.Quit()
            if p_out.exists() and p_out.stat().st_size > 0:
                return True, f"Exported Word document to PDF: {p_out}"
            return False, "Word COM export completed but output PDF was not found."
        except Exception as e:
            return False, f"Word COM PDF export error: {e}"


class ExcelAdapter(BaseAppAdapter):
    def __init__(self):
        super().__init__(
            "Microsoft Excel",
            ["excel.exe", "excel"],
            capabilities=["create_workbook", "formulas_and_charts", "data_cleaning", "com_automation"]
        )

    def launch(self, target: Optional[str] = None) -> Tuple[bool, str]:
        bin_path = self.get_binary_path()
        if bin_path:
            cmd = [bin_path]
            if target:
                cmd.append(str(Path(target).resolve()))
            try:
                subprocess.Popen(cmd)
                return True, f"Microsoft Excel launched successfully{' with file: ' + target if target else ''}."
            except Exception as e:
                return False, f"Could not launch Excel via binary: {e}"

        if target and Path(target).exists() and _IS_WINDOWS:
            try:
                os.startfile(str(Path(target).resolve()))
                return True, f"Opened workbook '{target}' with default spreadsheet viewer."
            except Exception as e:
                return False, f"Could not open workbook: {e}"

        return False, "Microsoft Excel is not installed on this system."


class OutlookAdapter(BaseAppAdapter):
    def __init__(self):
        super().__init__(
            "Microsoft Outlook",
            ["outlook.exe", "outlook"],
            capabilities=["compose_email", "send_email", "read_inbox", "com_automation"]
        )

    def launch(self, target: Optional[str] = None) -> Tuple[bool, str]:
        bin_path = self.get_binary_path()
        if bin_path:
            cmd = [bin_path]
            try:
                subprocess.Popen(cmd)
                return True, "Microsoft Outlook launched successfully."
            except Exception as e:
                return False, f"Could not launch Outlook: {e}"
        return False, "Microsoft Outlook is not installed on this system."


class OneNoteAdapter(BaseAppAdapter):
    def __init__(self):
        super().__init__(
            "Microsoft OneNote",
            ["onenote.exe", "onenote"],
            capabilities=["digital_notes", "notebooks"]
        )

    def launch(self, target: Optional[str] = None) -> Tuple[bool, str]:
        bin_path = self.get_binary_path()
        if bin_path:
            subprocess.Popen([bin_path])
            return True, "Microsoft OneNote launched."
        return False, "Microsoft OneNote is not installed."


# ── Creative, Dev, and System Adapters ────────────────────────────────────────

class BlenderAdapter(BaseAppAdapter):
    def __init__(self):
        super().__init__(
            "Blender 3D",
            ["blender.exe", "blender"],
            capabilities=["3d_scene_generation", "headless_rendering", "blend_projects", "mesh_export"]
        )

    def get_binary_path(self) -> Optional[str]:
        direct = super().get_binary_path()
        if direct:
            return direct

        # Deep search in Blender Foundation folder
        prog = os.environ.get("PROGRAMFILES", "C:\\Program Files")
        blender_root = Path(prog) / "Blender Foundation"
        if blender_root.exists():
            for sub in sorted(blender_root.iterdir(), reverse=True):
                cand = sub / "blender.exe"
                if cand.exists():
                    return str(cand)
        return None

    def launch(self, target: Optional[str] = None) -> Tuple[bool, str]:
        bin_path = self.get_binary_path()
        if not bin_path:
            return False, "Blender is not installed on this workstation."
        cmd = [bin_path]
        if target:
            cmd.append(str(Path(target).resolve()))
        try:
            subprocess.Popen(cmd)
            return True, f"Blender 3D launched with target: {target or 'New 3D Scene'}."
        except Exception as e:
            return False, f"Could not launch Blender: {e}"


class VSCodeAdapter(BaseAppAdapter):
    def __init__(self):
        super().__init__(
            "Visual Studio Code",
            ["code.cmd", "code.exe", "code"],
            capabilities=["code_editing", "terminal_integration", "git_integration", "project_workspace"]
        )

    def launch(self, target: Optional[str] = None) -> Tuple[bool, str]:
        bin_path = self.get_binary_path()
        if not bin_path:
            return False, "Visual Studio Code is not installed or 'code' CLI is not in PATH."

        cmd = [bin_path]
        if target:
            cmd.append(str(Path(target).resolve()))
        try:
            subprocess.Popen(cmd, shell=True)
            return True, f"VS Code opened at: {target or 'Workspace'}."
        except Exception as e:
            return False, f"Could not open VS Code: {e}"


class ChromeAdapter(BaseAppAdapter):
    def __init__(self):
        super().__init__(
            "Google Chrome",
            ["chrome.exe", "chrome"],
            capabilities=["web_browsing", "dom_automation", "research"]
        )

    def launch(self, target: Optional[str] = None) -> Tuple[bool, str]:
        bin_path = self.get_binary_path()
        if not bin_path:
            import webbrowser
            webbrowser.open(target or "https://www.google.com")
            return True, "Chrome binary not found; opened in default system browser."

        cmd = [bin_path]
        if target:
            cmd.append(target)
        try:
            subprocess.Popen(cmd)
            return True, f"Google Chrome launched with target: {target or 'New Tab'}."
        except Exception as e:
            return False, f"Could not launch Chrome: {e}"


class EdgeAdapter(BaseAppAdapter):
    def __init__(self):
        super().__init__(
            "Microsoft Edge",
            ["msedge.exe", "msedge"],
            capabilities=["web_browsing", "pdf_viewing"]
        )

    def launch(self, target: Optional[str] = None) -> Tuple[bool, str]:
        bin_path = self.get_binary_path() or "msedge.exe"
        cmd = [bin_path]
        if target:
            cmd.append(target)
        try:
            subprocess.Popen(cmd)
            return True, f"Microsoft Edge launched with target: {target or 'New Tab'}."
        except Exception as e:
            return False, f"Could not launch Edge: {e}"


class ExplorerAdapter(BaseAppAdapter):
    def __init__(self):
        super().__init__(
            "File Explorer",
            ["explorer.exe", "explorer"],
            capabilities=["file_browsing", "folder_navigation"]
        )

    def launch(self, target: Optional[str] = None) -> Tuple[bool, str]:
        path = str(Path(target).resolve()) if target else str(Path.home())
        try:
            if Path(path).is_file():
                subprocess.Popen(["explorer.exe", f"/select,{path}"])
            else:
                subprocess.Popen(["explorer.exe", path])
            return True, f"File Explorer opened at: {path}."
        except Exception as e:
            return False, f"Could not open File Explorer: {e}"


class NotepadAdapter(BaseAppAdapter):
    def __init__(self):
        super().__init__(
            "Notepad",
            ["notepad.exe", "notepad"],
            capabilities=["text_viewing", "quick_notes"]
        )

    def launch(self, target: Optional[str] = None) -> Tuple[bool, str]:
        bin_path = self.get_binary_path() or "notepad.exe"
        cmd = [bin_path]
        if target:
            cmd.append(str(Path(target).resolve()))
        try:
            subprocess.Popen(cmd)
            return True, f"Notepad opened with file: {target or 'New Document'}."
        except Exception as e:
            return False, f"Could not open Notepad: {e}"


class TerminalAdapter(BaseAppAdapter):
    def __init__(self):
        super().__init__(
            "Windows Terminal",
            ["wt.exe", "powershell.exe", "cmd.exe"],
            capabilities=["cli_execution", "scripts", "powershell"]
        )

    def launch(self, target: Optional[str] = None) -> Tuple[bool, str]:
        bin_path = self.get_binary_path() or "powershell.exe"
        cmd = [bin_path]
        if target:
            cmd.extend(["-NoExit", "-Command", f"Set-Location '{target}'"])
        try:
            subprocess.Popen(cmd)
            return True, f"Terminal opened at: {target or 'Home directory'}."
        except Exception as e:
            return False, f"Could not launch Terminal: {e}"


class VLCAdapter(BaseAppAdapter):
    def __init__(self):
        super().__init__(
            "VLC Media Player",
            ["vlc.exe", "vlc"],
            capabilities=["audio_playback", "video_playback"]
        )

    def launch(self, target: Optional[str] = None) -> Tuple[bool, str]:
        bin_path = self.get_binary_path()
        if not bin_path:
            return False, "VLC Media Player is not installed."
        cmd = [bin_path]
        if target:
            cmd.append(str(Path(target).resolve()))
        try:
            subprocess.Popen(cmd)
            return True, f"VLC Media Player opened{' with: ' + target if target else ''}."
        except Exception as e:
            return False, f"Could not launch VLC: {e}"


class ImageEditorAdapter(BaseAppAdapter):
    def __init__(self):
        super().__init__(
            "Image Editor",
            ["photoshop.exe", "mspaint.exe", "gimp.exe"],
            capabilities=["image_viewing", "graphic_editing"]
        )

    def launch(self, target: Optional[str] = None) -> Tuple[bool, str]:
        bin_path = self.get_binary_path()
        if bin_path and target:
            try:
                subprocess.Popen([bin_path, str(Path(target).resolve())])
                return True, f"Opened '{target}' in {self.name}."
            except Exception as e:
                return False, f"Could not open image in editor: {e}"

        if target and Path(target).exists() and _IS_WINDOWS:
            try:
                os.startfile(str(Path(target).resolve()))
                return True, f"Opened '{target}' with default viewer."
            except Exception as e:
                return False, f"Could not open image: {e}"

        return False, "No valid image target specified."


# ── Central App Registry ─────────────────────────────────────────────────────

class AppRegistry:
    """Registry managing all supported desktop application adapters."""

    def __init__(self):
        self._adapters: Dict[str, BaseAppAdapter] = {
            # Microsoft Office
            "powerpoint": PowerPointAdapter(),
            "ppt": PowerPointAdapter(),
            "powerpnt": PowerPointAdapter(),
            "word": WordAdapter(),
            "winword": WordAdapter(),
            "doc": WordAdapter(),
            "excel": ExcelAdapter(),
            "spreadsheet": ExcelAdapter(),
            "sheets": ExcelAdapter(),
            "outlook": OutlookAdapter(),
            "onenote": OneNoteAdapter(),

            # 3D Creation
            "blender": BlenderAdapter(),
            "blender 3d": BlenderAdapter(),

            # Development
            "vscode": VSCodeAdapter(),
            "code": VSCodeAdapter(),
            "visual studio code": VSCodeAdapter(),

            # Browsers
            "chrome": ChromeAdapter(),
            "google chrome": ChromeAdapter(),
            "edge": EdgeAdapter(),
            "microsoft edge": EdgeAdapter(),
            "browser": ChromeAdapter(),

            # System & Media
            "explorer": ExplorerAdapter(),
            "file explorer": ExplorerAdapter(),
            "notepad": NotepadAdapter(),
            "terminal": TerminalAdapter(),
            "powershell": TerminalAdapter(),
            "vlc": VLCAdapter(),
            "image_editor": ImageEditorAdapter(),
            "paint": ImageEditorAdapter(),
            "photoshop": ImageEditorAdapter(),
        }

    def register_adapter(self, alias: str, adapter: BaseAppAdapter) -> None:
        self._adapters[alias.lower().strip()] = adapter

    def get_adapter(self, app_name: str) -> Optional[BaseAppAdapter]:
        key = app_name.lower().strip()
        return self._adapters.get(key)

    def list_installed_apps(self) -> List[Dict[str, Any]]:
        seen = set()
        installed = []
        for name, adapter in self._adapters.items():
            if adapter.name in seen:
                continue
            seen.add(adapter.name)
            stat = adapter.get_status()
            installed.append({
                "name": stat.name,
                "installed": stat.installed,
                "running": stat.running,
                "path": stat.path,
                "responsive": stat.is_responsive,
                "details": stat.details,
                "capabilities": stat.capabilities,
                "integration_level": stat.integration_level,
            })
        return installed

    def launch_app(self, app_name: str, target: Optional[str] = None) -> Tuple[bool, str]:
        adapter = self.get_adapter(app_name)
        if not adapter:
            # Fallback: attempt direct generic launch
            bin_path = find_windows_app_path(app_name)
            if bin_path:
                try:
                    cmd = [bin_path]
                    if target:
                        cmd.append(target)
                    subprocess.Popen(cmd)
                    return True, f"Launched '{app_name}' from {bin_path}."
                except Exception as e:
                    return False, f"Could not launch '{app_name}': {e}"
            return False, f"No specialized adapter or binary found for application '{app_name}'."
        return adapter.launch(target)


app_registry = AppRegistry()
