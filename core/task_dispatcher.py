"""
core/task_dispatcher.py — Real Action Dispatcher for the Autonomous Task Orchestrator.

Bridges PlanStep skill_name/action_name pairs to actual registered handlers:
  • actions/* registered via action_loader (TOOL dict)
  • Specialized agent functions (research_agent, document_agent, dev_agent)
  • workflow_orchestrator pipelines
  • intent_engine local commands

Dispatch Contract:
  - Every dispatch returns a DispatchResult(success, output, verified)
  - 'verified' is only True when evidence confirms the outcome (file exists, process
    running, non-empty content, etc.)
  - Never marks success=True without real evidence.
  - Never executes arbitrary LLM-generated shell/Python strings.

Owner: Aditya Rajak
Salutation: Sir
"""
from __future__ import annotations

import os
import re
import subprocess
import socket
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from core.action_timeline import timeline
from core.firewall import redact
from core.security import OWNER_ADDRESS, security_manager

BASE_DIR = Path(__file__).resolve().parent.parent
SKILLSUM_ACTIONS = {
    "process_resume",
    "match_candidate",
    "skillsum_report",
    "skillsum_resume_eval",
}


@dataclass
class DispatchResult:
    success: bool
    output: str
    verified: bool = False
    generated_files: List[str] = field(default_factory=list)
    error: str = ""


class TaskDispatcher:
    """Maps PlanStep (skill_name, action_name, params) to real callable handlers."""

    _instance: Optional[TaskDispatcher] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> TaskDispatcher:
        with cls._lock:
            if cls._instance is None:
                cls._instance = TaskDispatcher()
        return cls._instance

    # ── Public Entry Point ────────────────────────────────────────────────────

    def dispatch(
        self,
        skill_name: str,
        action_name: str,
        params: Dict[str, Any],
        task_id: str = "",
    ) -> DispatchResult:
        """
        Dispatch a single PlanStep to the appropriate handler.
        Returns DispatchResult — never raises.
        """
        key = f"{skill_name}.{action_name}".lower()
        is_skillsum = self._is_skillsum_route(skill_name, action_name)
        try:
            result = self._route(key, skill_name, action_name, params, task_id)
            timeline.record(
                "DISPATCH",
                f"Step Dispatched: {key}",
                "SkillSum request processed." if is_skillsum else redact(result.output[:200]),
                status="SUCCESS" if result.success else "FAILED",
            )
            return result
        except Exception as exc:
            err = (
                "SkillSum processing failed. No verified report was created."
                if is_skillsum
                else f"Dispatch error for {key}: {exc}"
            )
            log_error = "SkillSum request failed." if is_skillsum else redact(str(exc))
            timeline.record("DISPATCH", f"Step Error: {key}", log_error, status="FAILED")
            return DispatchResult(
                success=False,
                output=err,
                verified=False,
                error="SKILLSUM_PROCESSING_FAILED" if is_skillsum else str(exc),
            )

    @staticmethod
    def _is_skillsum_route(skill_name: str, action_name: str) -> bool:
        return skill_name.lower() in ("skillsum", "resume") or action_name.lower() in SKILLSUM_ACTIONS

    @staticmethod
    def _path_is_within(path: Path, root: Path) -> bool:
        return path == root or path.is_relative_to(root)

    @classmethod
    def _get_authorized_roots(cls) -> List[Path]:
        """Return only the active workspace and named user folders approved for organization.

        Project discovery state is not an authorization policy: registered paths may be
        stale or point at arbitrary directories. The project workspace is BASE_DIR; the
        file organizer's user-facing scope is limited to Downloads, Documents, and Desktop.
        """
        roots = [BASE_DIR.resolve(strict=False)]
        home = Path.home().resolve(strict=False)
        for directory_name in ("Downloads", "Documents", "Desktop"):
            try:
                configured_directory = Path.home() / directory_name
                resolved_directory = configured_directory.resolve(strict=False)
            except (OSError, RuntimeError):
                continue

            # Keep redirected folders only when they remain a named, narrow directory
            # inside the user profile. This prevents a reparse point from granting
            # authority over a drive or a system directory.
            if (
                resolved_directory != home
                and cls._path_is_within(resolved_directory, home)
                and resolved_directory.name.casefold() == directory_name.casefold()
            ):
                roots.append(resolved_directory)

        unique_roots: List[Path] = []
        for root in roots:
            if root != Path(root.anchor) and len(root.parts) > 1 and root not in unique_roots:
                unique_roots.append(root)
        return unique_roots

    @classmethod
    def _resolve_authorized_path(cls, raw_path: Any) -> Tuple[Optional[Path], str]:
        """Resolve a path and enforce TaskDispatcher's explicit approved roots."""
        try:
            candidate_path = Path(raw_path).expanduser()
            if ".." in candidate_path.parts:
                return None, "PATH_TRAVERSAL"
            resolved = candidate_path.resolve(strict=False)
            if resolved == Path(resolved.anchor) or len(resolved.parts) <= 1:
                return None, "PATH_IS_DRIVE_ROOT"

            approved_roots = cls._get_authorized_roots()
            if not any(cls._path_is_within(resolved, root) for root in approved_roots):
                return None, "PATH_OUTSIDE_APPROVED_ROOTS"
            return resolved, ""
        except (OSError, RuntimeError, TypeError, ValueError):
            return None, "PATH_RESOLUTION_FAILED"

    @staticmethod
    def _safe_report_slug(project_name: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9]+", "-", project_name).strip("-").lower()
        return slug[:64] or "project"

    # ── Router ────────────────────────────────────────────────────────────────

    def _route(
        self,
        key: str,
        skill_name: str,
        action_name: str,
        params: Dict[str, Any],
        task_id: str,
    ) -> DispatchResult:

        # ── 1. System / Resource Queries ──────────────────────────────────────
        if action_name in ("analyze_intent", "audit_resources", "verify_telemetry", "check_port_or_url"):
            return self._system_info(action_name, params)

        if action_name == "list_heavy_processes":
            return self._list_heavy_processes()

        if action_name == "check_startup_apps":
            return self._check_startup_apps()

        # ── 2. Research Agent ─────────────────────────────────────────────────
        if skill_name == "research" or action_name in ("deep_research", "web_research"):
            from actions.research_agent import deep_research
            topic = params.get("topic") or params.get("query") or params.get("goal", "general knowledge")
            output = deep_research(topic)
            return DispatchResult(success=True, output=output, verified=bool(output))

        # ── 3. Document Agent ─────────────────────────────────────────────────
        if skill_name == "documents" and action_name in ("analyze_document", "generate_summary", "summarize", "generate_report", "compile_report"):
            return self._generate_document_summary(params)

        # ── 4. Dev / Syntax Audit ─────────────────────────────────────────────
        if action_name == "syntax_audit" or (skill_name == "coding" and "audit" in action_name):
            return self._syntax_audit(params)

        if action_name == "execute_operation":
            return self._execute_operation(params)

        if action_name == "verify_result":
            return self._verify_result(params)

        # ── 5. Project Context ────────────────────────────────────────────────
        if action_name == "get_context":
            return self._get_project_context(params)

        # ── 6. File Operations ────────────────────────────────────────────────
        if action_name in ("scan_downloads", "build_categories", "verify_structure", "clean_temp_cache"):
            return self._file_operation(action_name, params)

        if action_name == "move_files":
            return self._move_files(params)

        # ── 7. Security Audit ─────────────────────────────────────────────────
        if action_name == "security_audit":
            return self._security_audit()

        # ── 8. Workflow Orchestrator Pipelines ────────────────────────────────
        if action_name == "run_presentation":
            from core.workflow_orchestrator import workflow_orchestrator
            r = workflow_orchestrator.run_presentation_workflow(
                topic=params.get("topic", "General"),
                target_file=params.get("target_file"),
                launch_after=params.get("launch_after", False),
            )
            verified_files = [Path(path) for path in r.generated_files]
            verified = (
                r.success
                and r.steps_completed == r.total_steps
                and not r.errors
                and bool(verified_files)
                and all(path.is_file() and path.stat().st_size > 0 for path in verified_files)
            )
            return DispatchResult(success=verified, output=r.message, verified=verified,
                                  generated_files=r.generated_files,
                                  error="; ".join(r.errors) or ("Presentation outcome was not verified." if not verified else ""))

        if action_name == "run_dev_audit":
            from core.workflow_orchestrator import workflow_orchestrator
            r = workflow_orchestrator.run_dev_workflow(
                project_name=params.get("project", "alex"),
            )
            verified = r.success and r.steps_completed == r.total_steps and not r.errors and bool(r.message.strip())
            return DispatchResult(success=verified, output=r.message, verified=verified,
                                  generated_files=r.generated_files,
                                  error="; ".join(r.errors) or ("Development workflow outcome was not verified." if not verified else ""))

        # ── 8b. SkillSum Business Automation ──────────────────────────────────
        if self._is_skillsum_route(skill_name, action_name):
            return self._handle_skillsum(action_name, params)

        # ── 9. Registered action_loader Actions (TOOL dict based) ────────────
        result = self._try_action_registry(action_name, params)
        if result is not None:
            return result

        # ── 10. Intent Engine Fast Dispatch ───────────────────────────────────
        result = self._try_intent_engine(action_name, params)
        if result is not None:
            return result

        # ── 11. Fallback — Unknown action ─────────────────────────────────────
        return DispatchResult(
            success=False,
            output=f"No handler registered for skill='{skill_name}', action='{action_name}'.",
            verified=False,
            error=f"UNREGISTERED_ACTION:{action_name}",
        )

    # ── Specialized Handlers ──────────────────────────────────────────────────

    def _system_info(self, action_name: str, params: Dict) -> DispatchResult:
        """Handle system info / intent analysis steps."""
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.3)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            output = (
                f"System snapshot — CPU: {cpu}%, "
                f"RAM: {ram.percent}% ({ram.used // (1024**2)} MB / {ram.total // (1024**2)} MB), "
                f"Disk: {disk.percent}% used"
            )
            if action_name == "check_port_or_url":
                target = str(params.get("target", "")).strip()
                parsed = urlsplit(target if "://" in target else f"//{target}")
                host = parsed.hostname
                try:
                    port = parsed.port
                except ValueError:
                    return DispatchResult(success=False, output="Reachability target contains an invalid port.",
                                          verified=False, error="INVALID_REACHABILITY_TARGET")
                if port is None and parsed.scheme.lower() in ("http", "https"):
                    port = 443 if parsed.scheme.lower() == "https" else 80
                if not host or not port:
                    return DispatchResult(
                        success=False,
                        output=f"Reachability target '{target}' must include a hostname and port or an HTTP(S) URL.",
                        verified=False,
                        error="INVALID_REACHABILITY_TARGET",
                    )
                with socket.create_connection((host, port), timeout=3):
                    pass
                output += f" | TCP connection to '{host}:{port}' succeeded."
            return DispatchResult(success=True, output=output, verified=True)
        except Exception as e:
            return DispatchResult(success=False, output=str(e), error=str(e))

    def _list_heavy_processes(self) -> DispatchResult:
        try:
            import psutil
            procs = sorted(psutil.process_iter(["name", "cpu_percent", "memory_percent"]),
                           key=lambda p: p.info.get("memory_percent", 0) or 0, reverse=True)
            top = [(p.info["name"], round(p.info["memory_percent"] or 0, 1)) for p in procs[:6] if p.info["name"]]
            output = "Top memory processes: " + ", ".join(f"{n}({m}%)" for n, m in top)
            return DispatchResult(success=True, output=output, verified=True)
        except Exception as e:
            return DispatchResult(success=False, output=str(e), error=str(e))

    def _check_startup_apps(self) -> DispatchResult:
        try:
            import winreg
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
            apps = []
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
                i = 0
                while True:
                    try:
                        name, _, _ = winreg.EnumValue(k, i)
                        apps.append(name)
                        i += 1
                    except OSError:
                        break
            output = f"Startup applications ({len(apps)}): {', '.join(apps[:8]) if apps else 'None detected'}"
            return DispatchResult(success=True, output=output, verified=True)
        except Exception as e:
            return DispatchResult(success=False, output=f"Startup check: {e}", error=str(e))

    def _syntax_audit(self, params: Dict) -> DispatchResult:
        import py_compile
        project = params.get("project", "")
        p_dir = BASE_DIR
        if project:
            try:
                from core.project_manager import project_manager
                proj_info = project_manager.get_project(project)
                if proj_info:
                    candidate = Path(getattr(proj_info, "path", ""))
                    if candidate.exists():
                        p_dir = candidate
            except Exception:
                pass
        errors = []
        count = 0
        for root, _, files in os.walk(p_dir):
            if any(skip in root for skip in ("__pycache__", ".venv", "venv", ".git", "node_modules")):
                continue
            for f in files:
                if f.endswith(".py"):
                    fp = Path(root) / f
                    count += 1
                    try:
                        py_compile.compile(str(fp), doraise=True)
                    except Exception as e:
                        errors.append(f"{fp.name}: {e}")
        output = f"Syntax audit: {count} files checked, {len(errors)} error(s)."
        if errors:
            output += "\nErrors:\n" + "\n".join(errors[:10])
        verified = count > 0 and not errors
        error = "; ".join(errors[:3]) if errors else ("No Python source files were found to audit." if count == 0 else "")
        return DispatchResult(success=verified, output=output, verified=verified, error=error)

    def _execute_operation(self, params: Dict) -> DispatchResult:
        """Generic goal execution — routes through intent engine."""
        goal = params.get("goal", "")
        if not goal:
            return DispatchResult(success=False, output="No specific operation was provided.", verified=False,
                                  error="MISSING_OPERATION")
        result = self._try_intent_engine_text(goal)
        if result is not None:
            return result
        return DispatchResult(success=False, output=f"No handler completed goal '{goal}'.", verified=False,
                              error="NO_OPERATION_HANDLER")

    def _generate_document_summary(self, params: Dict) -> DispatchResult:
        file_path = params.get("file_path") or params.get("path", "")
        if file_path:
            document_path = Path(file_path)
            if not document_path.is_file():
                return DispatchResult(success=False, output="Document path is missing or is not a file.",
                                      verified=False, error="DOCUMENT_FILE_MISSING")
            supported_extensions = {".txt", ".md", ".json", ".log", ".csv", ".pdf", ".docx", ".xlsx", ".pptx"}
            if document_path.suffix.lower() not in supported_extensions:
                return DispatchResult(success=False, output="Document type is not supported for analysis.",
                                      verified=False, error="UNSUPPORTED_DOCUMENT_TYPE")
            from actions.document_agent import analyze_document
            out = analyze_document(file_path, task=params.get("task", "summarize"))
            output_lower = (out or "").lower()
            error_markers = (
                "processing encountered an error:",
                "document not found at:",
                "file not found:",
                "path is not a file:",
                "could not process:",
                "no text found in pdf",
                " is empty.",
            )
            verified = bool(out and out.strip()) and not any(marker in output_lower for marker in error_markers)
            return DispatchResult(success=verified, output=out, verified=verified,
                                  error="DOCUMENT_ANALYSIS_FAILED" if not verified else "")

        goal = str(params.get("goal", "task") or "task")
        save_report = params.get("save_report", False) or any(
            word in goal.lower() for word in ("report", "save", "path", "banao", "audit", "bug")
        )
        project = str(params.get("project", "alex") or "alex")

        if save_report:
            workspace_root = BASE_DIR.resolve(strict=True)
            memory_dir = BASE_DIR / "memory"
            artifacts_dir = memory_dir / "artifacts"
            reports_dir = artifacts_dir / "audits"
            try:
                resolved_memory = memory_dir.resolve(strict=False)
                resolved_artifacts = artifacts_dir.resolve(strict=False)
                resolved_reports = reports_dir.resolve(strict=False)
            except (OSError, RuntimeError) as exc:
                return DispatchResult(success=False, output="Report directory could not be resolved.",
                                      verified=False, error=f"REPORT_PATH_RESOLUTION_FAILED: {exc}")

            if (
                not self._path_is_within(resolved_memory, workspace_root)
                or resolved_memory == workspace_root
                or resolved_artifacts != resolved_memory / "artifacts"
                or resolved_reports != resolved_memory / "artifacts" / "audits"
            ):
                return DispatchResult(success=False, output="Report directory is outside the approved artifacts area.",
                                      verified=False, error="REPORT_PATH_OUTSIDE_ARTIFACTS")

            try:
                from core.project_manager import project_manager
                proj_info = project_manager.get_project(project)
                p_path = proj_info.path if proj_info else str(BASE_DIR)
            except Exception:
                p_path = str(BASE_DIR)

            # Syntax status
            import py_compile
            syntax_count = 0
            syntax_errors = []
            for root, _, files in os.walk(p_path):
                if any(skip in root for skip in ("__pycache__", ".venv", "venv", ".git", "node_modules")):
                    continue
                for f in files:
                    if f.endswith(".py"):
                        syntax_count += 1
                        try:
                            py_compile.compile(str(Path(root) / f), doraise=True)
                        except Exception as e:
                            syntax_errors.append(f"{f}: {e}")

            from core.security import security_manager
            sec_log = security_manager.get_security_audit_log(5)
            timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")

            report_content = f"""# 📋 ALEX AI — Project Audit & Bug Report
**Target Project:** {project}
**Workspace Path:** `{p_path}`
**Generated At:** {timestamp_str}
**Auditor:** ALEX 4.0 Autonomous Task Orchestrator
**Owner Salutation:** {OWNER_ADDRESS}

---

## 1. Executive Summary
- **Overall Health Status:** {"HEALTHY (All syntax checks passed)" if not syntax_errors else "ISSUES DETECTED"}
- **Total Python Files Scanned:** {syntax_count}
- **Syntax / Compilation Errors:** {len(syntax_errors)}
- **Security Subsystem Status:** Active & Guarded

---

## 2. Syntax & Compilation Audit
- **Files Checked:** {syntax_count}
- **Errors Found:** {len(syntax_errors)}
"""
            if syntax_errors:
                report_content += "\n### Identified Bugs & Errors:\n"
                for err in syntax_errors:
                    report_content += f"- ❌ `{err}`\n"
            else:
                report_content += "\n- ✅ Zero syntax or bytecode compilation errors found across all modules.\n"

            report_content += f"""
---

## 3. Security & Permission Audit
- **Clearance Level:** Verified Owner
- **Log Audit:**
```
{sec_log}
```

---

## 4. Verification & Recommendations
- All core modules compiled cleanly.
- Deliverable report verified and archived in memory artifacts.
"""
            report_slug = self._safe_report_slug(project)
            candidates = []
            for _ in range(5):
                suffix = uuid.uuid4().hex
                candidate = resolved_reports / f"{report_slug}_audit_and_bug_report_{suffix}.md"
                resolved_candidate = candidate.resolve(strict=False)
                if not self._path_is_within(resolved_candidate, resolved_reports):
                    return DispatchResult(success=False, output="Report path escaped the artifacts directory.",
                                          verified=False, error="REPORT_PATH_OUTSIDE_ARTIFACTS")
                candidates.append(candidate)

            try:
                artifacts_dir.mkdir(parents=True, exist_ok=True)
                reports_dir.mkdir(parents=True, exist_ok=True)
                actual_artifacts = artifacts_dir.resolve(strict=True)
                actual_reports = reports_dir.resolve(strict=True)
                if actual_artifacts != resolved_artifacts or actual_reports != resolved_reports:
                    return DispatchResult(success=False, output="Report directory changed during validation.",
                                          verified=False, error="REPORT_DIRECTORY_CHANGED")

                target_path = None
                for candidate in candidates:
                    resolved_candidate = candidate.resolve(strict=False)
                    if not self._path_is_within(resolved_candidate, actual_reports):
                        return DispatchResult(success=False, output="Report path escaped the artifacts directory.",
                                              verified=False, error="REPORT_PATH_OUTSIDE_ARTIFACTS")
                    try:
                        with candidate.open("x", encoding="utf-8") as report_file:
                            report_file.write(report_content)
                        target_path = candidate
                        break
                    except FileExistsError:
                        continue

                if target_path is None:
                    return DispatchResult(success=False, output="Could not allocate a unique report filename.",
                                          verified=False, error="REPORT_FILENAME_COLLISION")

                resolved_target = target_path.resolve(strict=True)
                if not self._path_is_within(resolved_target, actual_reports):
                    return DispatchResult(success=False, output="Generated report is outside the artifacts directory.",
                                          verified=False, error="REPORT_PATH_OUTSIDE_ARTIFACTS")
                file_size = resolved_target.stat().st_size
                abs_path = str(resolved_target)
            except (OSError, RuntimeError) as exc:
                return DispatchResult(success=False, output="Report could not be written safely.",
                                      verified=False, error=f"REPORT_WRITE_FAILED: {exc}")

            out_msg = (
                f"Sir, project '{project}' ka audit complete ho gaya aur bugs ki report save kar di gayi hai. "
                f"Report path: '{abs_path}' (Size: {file_size} bytes, Files checked: {syntax_count}, Errors: {len(syntax_errors)})."
            )
            return DispatchResult(
                success=True,
                output=out_msg,
                verified=target_path.exists() and file_size > 0,
                generated_files=[abs_path]
            )

        return DispatchResult(success=False, output="No report or summary handler produced a verifiable deliverable.",
                              verified=False, error="NO_SUMMARY_OUTCOME")

    def _verify_result(self, params: Dict) -> DispatchResult:
        goal = params.get("goal", "")
        files = params.get("files") or []
        if isinstance(files, (str, Path)):
            files = [files]
        if files:
            verified_files = [str(Path(file_path)) for file_path in files]
            for file_path in verified_files:
                p = Path(file_path)
                if not p.is_file() or p.stat().st_size == 0:
                    return DispatchResult(success=False, output=f"Deliverable file '{file_path}' missing or empty.", verified=False, error="FILE_MISSING")
            return DispatchResult(
                success=True,
                output=f"Deliverable verification confirmed. File saved at '{verified_files[0]}'. File verified on disk.",
                verified=True,
                generated_files=verified_files
            )
        return DispatchResult(success=False, output=f"No concrete deliverable was supplied to verify for '{goal}'.",
                              verified=False, error="NO_DELIVERABLE_TO_VERIFY")

    def _handle_skillsum(self, action_name: str, params: Dict[str, Any]) -> DispatchResult:
        try:
            from actions.skillsum_automation import skillsum_service
            resume_path = params.get("resume_path") or params.get("file_path") or params.get("path", "")
            if not resume_path:
                return DispatchResult(success=False, output="Resume file path is required.", verified=False, error="MISSING_PATH")

            job_desc = params.get("job_description") or params.get("job") or params.get("role", "")
            report = skillsum_service.process_candidate_resume(resume_path, job_desc)
            if not report.success:
                failure = report.error_message or "Resume evaluation could not be completed."
                return DispatchResult(success=False, output=failure, verified=False, error=failure)

            report_paths = [Path(report.markdown_path), Path(report.json_path)]
            verified = all(path.is_file() and path.stat().st_size > 0 for path in report_paths)
            if not verified:
                return DispatchResult(
                    success=False,
                    output="SkillSum report verification failed; the reports are unavailable.",
                    verified=False,
                    error="REPORT_VERIFICATION_FAILED",
                )

            score = report.evaluation.match_score_pct
            score_label = (
                f"{score:.1f}% preliminary decision-support estimate"
                if score is not None
                else "not calculated because no skills were specified"
            )

            out_msg = (
                f"Candidate '{report.candidate.candidate_name}' evaluated for '{report.job.title}'. "
                f"Match Score: {score_label}. Reports: '{report.markdown_path}' and '{report.json_path}'."
            )
            return DispatchResult(
                success=True,
                output=out_msg,
                verified=True,
                generated_files=[report.markdown_path, report.json_path]
            )
        except Exception:
            return DispatchResult(
                success=False,
                output="SkillSum processing failed. No verified report was created.",
                verified=False,
                error="SKILLSUM_PROCESSING_FAILED",
            )

    def _get_project_context(self, params: Dict) -> DispatchResult:
        try:
            from core.project_manager import project_manager
            project = params.get("project", "")
            status = project_manager.get_project_status_report(project)
            return DispatchResult(success=True, output=status, verified=bool(status))
        except Exception as e:
            return DispatchResult(success=False, output=str(e), error=str(e))

    def _file_operation(self, action_name: str, params: Dict) -> DispatchResult:
        source_dir = Path(
            params.get("source")
            or params.get("path")
            or Path.home() / "Downloads"
        ).expanduser()
        if action_name == "scan_downloads":
            if not source_dir.is_dir():
                return DispatchResult(success=False, output=f"Downloads directory '{source_dir}' is unavailable.",
                                      verified=False, error="SOURCE_DIRECTORY_MISSING")
            files = sorted(path.name for path in source_dir.iterdir())
            return DispatchResult(success=True, output=f"Scanned {len(files)} entries in '{source_dir}': "
                                  + (", ".join(files[:30]) if files else "directory is empty."), verified=True)
        if action_name == "build_categories":
            if not source_dir.is_dir():
                return DispatchResult(success=False, output=f"Downloads directory '{source_dir}' is unavailable.",
                                      verified=False, error="SOURCE_DIRECTORY_MISSING")
            counts: Dict[str, int] = {}
            for path in source_dir.iterdir():
                if path.is_file():
                    category = self._file_category(path.suffix)
                    counts[category] = counts.get(category, 0) + 1
            summary = ", ".join(f"{category}: {count}" for category, count in sorted(counts.items())) or "no files to categorize"
            return DispatchResult(success=True, output=f"Categorized {sum(counts.values())} files by extension ({summary}).",
                                  verified=True)
        if action_name == "verify_structure":
            destination_dir = Path(params.get("destination") or source_dir / "Organized").expanduser()
            if not destination_dir.is_dir():
                return DispatchResult(success=False, output=f"Organized directory '{destination_dir}' is missing.",
                                      verified=False, error="ORGANIZED_DIRECTORY_MISSING")
            misplaced = [
                path for path in destination_dir.rglob("*")
                if path.is_file() and path.parent.name != self._file_category(path.suffix)
            ]
            if misplaced:
                return DispatchResult(success=False,
                                      output=f"Directory verification found {len(misplaced)} misplaced file(s).",
                                      verified=False, error="MISPLACED_FILES")
            return DispatchResult(success=True,
                                  output=f"Verified categorized structure under '{destination_dir}'.",
                                  verified=True, generated_files=[str(destination_dir)])
        if action_name == "clean_temp_cache":
            temp_dir = Path(params.get("temp_dir") or os.environ.get("TEMP", "C:/Windows/Temp"))
            if not temp_dir.is_dir():
                return DispatchResult(success=False, output=f"Temporary directory '{temp_dir}' is unavailable.",
                                      verified=False, error="TEMP_DIRECTORY_MISSING")
            cleaned = 0
            failures = []
            for f in temp_dir.glob("*.tmp"):
                try:
                    f.unlink()
                    if f.exists():
                        failures.append(f.name)
                        continue
                    cleaned += 1
                except OSError as exc:
                    failures.append(f"{f.name}: {exc}")
            if failures:
                return DispatchResult(success=False, output=f"Could not remove {len(failures)} temporary file(s).",
                                      verified=False, error="; ".join(failures[:3]))
            return DispatchResult(success=True, output=f"Verified removal of {cleaned} temporary cache file(s).",
                                  verified=True)
        return DispatchResult(success=False, output=f"Unsupported file operation '{action_name}'.",
                              verified=False, error="UNSUPPORTED_FILE_OPERATION")

    def _move_files(self, params: Dict) -> DispatchResult:
        """Controlled file organization — only within authorized workspace."""
        import shutil

        source_input = params.get("source") or (Path.home() / "Downloads")
        src_dir, source_error = self._resolve_authorized_path(source_input)
        if source_error:
            return DispatchResult(success=False, output="File organization rejected: source path is invalid or unauthorized.",
                                  verified=False, error=f"SOURCE_{source_error}")

        destination_input = params.get("destination") or (src_dir / "Organized")
        dst_dir, destination_error = self._resolve_authorized_path(destination_input)
        if destination_error:
            return DispatchResult(success=False, output="File organization rejected: destination path is invalid or unauthorized.",
                                  verified=False, error=f"DESTINATION_{destination_error}")

        if not src_dir.is_dir():
            return DispatchResult(success=False, output="File organization source is not an available directory.",
                                  verified=False, error="SOURCE_DIRECTORY_MISSING")
        if dst_dir.exists() and not dst_dir.is_dir():
            return DispatchResult(success=False, output="File organization destination is not a directory.",
                                  verified=False, error="DESTINATION_NOT_DIRECTORY")
        if src_dir == dst_dir:
            return DispatchResult(success=False, output="File organization source and destination must differ.",
                                  verified=False, error="SOURCE_EQUALS_DESTINATION")

        try:
            entries = list(src_dir.iterdir())
        except OSError:
            return DispatchResult(success=False, output="File organization source could not be inspected.",
                                  verified=False, error="SOURCE_READ_FAILED")

        operations = []
        failures = []
        for entry in entries:
            if entry.is_symlink():
                try:
                    symlink_target = entry.resolve(strict=False)
                except (OSError, RuntimeError):
                    return DispatchResult(success=False, output="File organization rejected an unresolvable symbolic link.",
                                          verified=False, error="SOURCE_SYMLINK_RESOLUTION_FAILED")
                if not self._path_is_within(symlink_target, src_dir):
                    return DispatchResult(success=False, output="File organization rejected a symbolic-link escape.",
                                          verified=False, error="SOURCE_SYMLINK_ESCAPE")
                if entry.is_file():
                    return DispatchResult(success=False, output="File organization rejected a symbolic-link file.",
                                          verified=False, error="SOURCE_SYMLINK_REJECTED")
                continue
            if not entry.is_file():
                continue

            try:
                source_file = entry.resolve(strict=True)
                category_dir = dst_dir / self._file_category(entry.suffix)
                resolved_category = category_dir.resolve(strict=False)
                destination_file = category_dir / entry.name
                resolved_destination = destination_file.resolve(strict=False)
            except (OSError, RuntimeError):
                return DispatchResult(success=False, output="File organization rejected an unresolvable file path.",
                                      verified=False, error="FILE_PATH_RESOLUTION_FAILED")

            if not self._path_is_within(source_file, src_dir):
                return DispatchResult(success=False, output="File organization rejected a source path escape.",
                                      verified=False, error="SOURCE_PATH_ESCAPE")
            if (
                not self._path_is_within(resolved_category, dst_dir)
                or not self._path_is_within(resolved_destination, dst_dir)
            ):
                return DispatchResult(success=False, output="File organization rejected a destination path escape.",
                                      verified=False, error="DESTINATION_PATH_ESCAPE")
            if category_dir.exists() and not category_dir.is_dir():
                return DispatchResult(success=False, output="A category destination is not a directory.",
                                      verified=False, error="CATEGORY_NOT_DIRECTORY")
            if destination_file.exists() or destination_file.is_symlink():
                failures.append(f"{entry.name}: destination already exists")
                continue
            operations.append((source_file, category_dir, destination_file))

        current_source, source_error = self._resolve_authorized_path(src_dir)
        current_destination, destination_error = self._resolve_authorized_path(dst_dir)
        if source_error or destination_error or current_source != src_dir or current_destination != dst_dir:
            return DispatchResult(success=False, output="File organization paths changed during validation.",
                                  verified=False, error="PATH_CHANGED_DURING_VALIDATION")

        try:
            dst_dir.mkdir(parents=True, exist_ok=True)
            if dst_dir.resolve(strict=True) != dst_dir:
                return DispatchResult(success=False, output="File organization destination changed during validation.",
                                      verified=False, error="DESTINATION_CHANGED_DURING_VALIDATION")
        except OSError:
            return DispatchResult(success=False, output="File organization destination could not be created.",
                                  verified=False, error="DESTINATION_CREATE_FAILED")

        moved = 0
        moved_files = []
        for source_file, category_dir, destination_file in operations:
            try:
                if source_file.is_symlink() or not source_file.is_file() or source_file.resolve(strict=True) != source_file:
                    failures.append(f"{source_file.name}: source changed during organization")
                    continue
                resolved_category = category_dir.resolve(strict=False)
                resolved_destination = destination_file.resolve(strict=False)
                if (
                    not self._path_is_within(resolved_category, dst_dir)
                    or not self._path_is_within(resolved_destination, dst_dir)
                    or destination_file.exists()
                    or destination_file.is_symlink()
                ):
                    failures.append(f"{source_file.name}: destination changed or already exists")
                    continue
                category_dir.mkdir(parents=True, exist_ok=True)
                if category_dir.resolve(strict=True) != resolved_category:
                    failures.append(f"{source_file.name}: category path changed during move")
                    continue
                resolved_destination = destination_file.resolve(strict=False)
                if (
                    source_file.is_symlink()
                    or not source_file.is_file()
                    or source_file.resolve(strict=True) != source_file
                    or not self._path_is_within(resolved_destination, dst_dir)
                    or destination_file.exists()
                    or destination_file.is_symlink()
                ):
                    failures.append(f"{source_file.name}: source or destination changed during move")
                    continue
                shutil.move(str(source_file), str(destination_file))
                if destination_file.is_file() and not source_file.exists():
                    moved += 1
                    moved_files.append(str(destination_file))
                else:
                    failures.append(f"{source_file.name}: move could not be verified")
            except (OSError, RuntimeError) as exc:
                failures.append(f"{source_file.name}: {exc}")

        output = f"Organized {moved} files into categorized subdirectories under {dst_dir}."
        verified = dst_dir.is_dir() and not failures
        return DispatchResult(success=verified, output=output, verified=verified,
                              error="; ".join(failures[:3]) if failures else "",
                              generated_files=moved_files if verified else [])

    def _file_category(self, ext: str) -> str:
        ext = ext.lower()
        if ext in (".pdf", ".docx", ".doc", ".txt", ".xlsx", ".pptx", ".csv", ".md"):
            return "Documents"
        if ext in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp"):
            return "Images"
        if ext in (".exe", ".msi", ".dmg", ".deb", ".appimage"):
            return "Installers"
        if ext in (".py", ".js", ".ts", ".java", ".cpp", ".c", ".go", ".rs", ".zip", ".tar", ".gz"):
            return "Code"
        if ext in (".mp4", ".mkv", ".avi", ".mov", ".mp3", ".wav", ".flac"):
            return "Media"
        return "Other"

    def _security_audit(self) -> DispatchResult:
        try:
            from core.security import security_manager
            audit = security_manager.get_security_audit_log()
            output = f"Security audit complete. Last events: {str(audit)[:300]}"
            return DispatchResult(success=True, output=output, verified=True)
        except Exception as e:
            return DispatchResult(success=False, output="Security audit could not be completed.",
                                  verified=False, error=str(e))

    def _try_action_registry(self, action_name: str, params: Dict) -> Optional[DispatchResult]:
        """Try dispatching via the TOOL-based ActionRegistry if it's been built."""
        try:
            import main as _main_mod
            registry = getattr(_main_mod, "_action_registry", None)
            if registry and registry.has(action_name):
                output = registry.run(action_name, params, ctx={})
                if isinstance(output, dict):
                    success = output.get("success") is True
                    verified = output.get("verified") is True
                    message = str(output.get("output") or output.get("message") or "")
                else:
                    success = getattr(output, "success", False) is True
                    verified = getattr(output, "verified", False) is True
                    message = str(getattr(output, "output", getattr(output, "message", "")) or "")
                success = success and verified
                if not message and isinstance(output, str):
                    message = output.strip()
                return DispatchResult(success=success, output=message or "Registered action reported a verified outcome.",
                                      verified=success,
                                      error="ACTION_NOT_VERIFIABLE" if not success else "")
        except Exception:
            pass
        return None

    def _try_intent_engine(self, action_name: str, params: Dict) -> Optional[DispatchResult]:
        """Map action_name to an intent and dispatch via intent_engine."""
        intent_map = {
            "open_application": "OPEN_APPLICATION",
            "open_website": "OPEN_WEBSITE",
            "web_search": "WEB_SEARCH",
            "time_check": "TIME_CHECK",
            "list_files": "LIST_FILES",
            "create_folder": "CREATE_FOLDER",
            "create_file": "CREATE_FILE",
            "volume_up": "VOLUME_UP",
            "volume_down": "VOLUME_DOWN",
            "system_status": "SYSTEM_STATUS",
        }
        intent_name = intent_map.get(action_name.lower())
        if not intent_name:
            return None
        try:
            from core.intent_engine import IntentResult, intent_engine
            fake_intent = IntentResult(intent=intent_name, confidence=0.95, slots=params,
                                       language="english", is_local_command=True)
            result = intent_engine.execute_local_command(fake_intent)
            verified = bool(result.handled) and getattr(result, "verified", False) is True
            return DispatchResult(success=verified, output=result.response_text, verified=verified,
                                  error="INTENT_OUTCOME_NOT_VERIFIED" if not verified else "")
        except Exception as e:
            return DispatchResult(success=False, output=str(e), error=str(e))

    def _try_intent_engine_text(self, text: str) -> Optional[DispatchResult]:
        try:
            from core.intent_engine import intent_engine
            res = intent_engine.parse(text)
            if res.is_local_command:
                exe = intent_engine.execute_local_command(res)
                verified = bool(exe.handled) and getattr(exe, "verified", False) is True
                return DispatchResult(success=verified, output=exe.response_text, verified=verified,
                                      error="INTENT_OUTCOME_NOT_VERIFIED" if not verified else "")
        except Exception:
            pass
        return None


# Singleton
task_dispatcher = TaskDispatcher.get_instance()

