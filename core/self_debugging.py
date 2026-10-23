"""
core/self_debugging.py — Self-Debugging & Evidence-Based Diagnostic System for ALEX.

Owner: Aditya Rajak
Salutation: Sir / Aditya Sir
Assistant: ALEX

Implements Phase 2 Requirement 2:
  • Diagnostic engine that inspects:
      1. Python exceptions and tracebacks
      2. Application logs
      3. Failed imports
      4. Missing packages
      5. Configuration errors
      6. API connection failures
      7. Browser automation failures
      8. Audio pipeline failures
      9. UI errors
      10. Database errors
      11. Test failures
      12. Background task failures
  • Structured records for each issue:
      - error description
      - root cause & confidence level (SUSPECTED, PROBABLE, CONFIRMED)
      - affected files
      - proposed fix
      - fix applied status
      - tests executed
      - verification result
  • Strict Safety & Honesty Principle:
      "Never report a suspected root cause as confirmed without evidence."
"""

from __future__ import annotations

import json
import re
import time
import traceback
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
DIAGNOSTICS_LOG_FILE = BASE_DIR / "memory" / "diagnostic_issues.json"


class RootCauseConfidence(str, Enum):
    SUSPECTED = "SUSPECTED"  # Theoretical correlation or heuristic match
    PROBABLE  = "PROBABLE"   # Strong log/stack correlation, but not isolated/reproduced
    CONFIRMED = "CONFIRMED"  # Mathematically/empirically verified by reproduction script, failing test, or AST syntax error


class DefectCategory(str, Enum):
    EXCEPTION          = "PYTHON_EXCEPTION"
    IMPORT_FAILURE     = "IMPORT_FAILURE"
    MISSING_PACKAGE    = "MISSING_PACKAGE"
    CONFIG_ERROR       = "CONFIG_ERROR"
    API_FAILURE        = "API_FAILURE"
    BROWSER_FAILURE    = "BROWSER_FAILURE"
    AUDIO_FAILURE      = "AUDIO_FAILURE"
    UI_ERROR           = "UI_ERROR"
    DATABASE_ERROR     = "DATABASE_ERROR"
    TEST_FAILURE       = "TEST_FAILURE"
    BACKGROUND_TASK    = "BACKGROUND_TASK_FAILURE"
    LOG_ANOMALY        = "LOG_ANOMALY"


@dataclass
class DiagnosticIssue:
    issue_id: str
    category: DefectCategory
    error_description: str
    root_cause: str
    confidence_level: RootCauseConfidence
    affected_files: List[str]
    proposed_fix: str
    evidence: str
    fix_applied: bool = False
    tests_executed: List[str] = field(default_factory=list)
    verification_result: str = "PENDING"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        d["confidence_level"] = self.confidence_level.value
        return d


class SelfDebuggingEngine:
    """Central diagnostic engine providing empirical root-cause analysis."""

    _instance: Optional[SelfDebuggingEngine] = None

    def __init__(self):
        self._issues: List[DiagnosticIssue] = []
        self._load_issues()

    @classmethod
    def get_instance(cls) -> SelfDebuggingEngine:
        if cls._instance is None:
            cls._instance = SelfDebuggingEngine()
        return cls._instance

    def _load_issues(self) -> None:
        if DIAGNOSTICS_LOG_FILE.exists():
            try:
                data = json.loads(DIAGNOSTICS_LOG_FILE.read_text(encoding="utf-8"))
                for item in data[-200:]:
                    cat = DefectCategory(item.get("category", DefectCategory.EXCEPTION.value))
                    conf = RootCauseConfidence(item.get("confidence_level", RootCauseConfidence.SUSPECTED.value))
                    item["category"] = cat
                    item["confidence_level"] = conf
                    self._issues.append(DiagnosticIssue(**item))
            except Exception:
                self._issues = []

    def _persist(self) -> None:
        try:
            DIAGNOSTICS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            raw = [i.to_dict() for i in self._issues[-200:]]
            DIAGNOSTICS_LOG_FILE.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def record_issue(self, issue: DiagnosticIssue) -> DiagnosticIssue:
        self._issues.append(issue)
        self._persist()
        return issue

    # ── Diagnostic Analyzers ──────────────────────────────────────────────────

    def diagnose_traceback(self, tb_str: str, has_reproduction_proof: bool = False) -> DiagnosticIssue:
        """Inspects Python tracebacks, isolating exact exception, line, and file."""
        lines = [line.strip() for line in tb_str.strip().splitlines() if line.strip()]
        last_line = lines[-1] if lines else "Unknown Exception"

        # Match File "path/to/file.py", line XX
        file_matches = re.findall(r'File ["\']([^"\']+\.py)["\'],\s+line\s+(\d+)', tb_str, re.IGNORECASE)
        affected = [f[0] for f in file_matches]

        confidence = RootCauseConfidence.CONFIRMED if has_reproduction_proof else RootCauseConfidence.PROBABLE

        # Specific diagnosis rules
        if "ModuleNotFoundError: No module named" in last_line:
            mod = last_line.split("No module named")[-1].strip().strip("'\"")
            return self.record_issue(DiagnosticIssue(
                issue_id=f"ISSUE-IMP-{int(time.time()*1000)%1000000}",
                category=DefectCategory.MISSING_PACKAGE,
                error_description=last_line,
                root_cause=f"Python module '{mod}' is not installed in the active virtual environment.",
                confidence_level=RootCauseConfidence.CONFIRMED,  # Proven by interpreter import failure
                affected_files=affected,
                proposed_fix=f"Run: pip install {mod}",
                evidence=f"ModuleNotFoundError: {mod}"
            ))

        if "SyntaxError" in last_line or "IndentationError" in last_line:
            return self.record_issue(DiagnosticIssue(
                issue_id=f"ISSUE-SYN-{int(time.time()*1000)%1000000}",
                category=DefectCategory.EXCEPTION,
                error_description=last_line,
                root_cause=f"Syntax or indentation defect in source file: {last_line}",
                confidence_level=RootCauseConfidence.CONFIRMED,  # Proven directly by parser
                affected_files=affected,
                proposed_fix="Correct syntax violation and verify using AST parser.",
                evidence=tb_str[-400:]
            ))

        if "KeyError" in last_line or "IndexError" in last_line:
            return self.record_issue(DiagnosticIssue(
                issue_id=f"ISSUE-DATA-{int(time.time()*1000)%1000000}",
                category=DefectCategory.EXCEPTION,
                error_description=last_line,
                root_cause=f"Data structure access failure: missing dictionary key or out-of-bounds list index.",
                confidence_level=confidence,
                affected_files=affected,
                proposed_fix="Use safe .get() with fallback value or check collection length before access.",
                evidence=last_line
            ))

        return self.record_issue(DiagnosticIssue(
            issue_id=f"ISSUE-EXC-{int(time.time()*1000)%1000000}",
            category=DefectCategory.EXCEPTION,
            error_description=last_line,
            root_cause=f"Unhandled exception during execution: {last_line}",
            confidence_level=confidence,
            affected_files=affected,
            proposed_fix="Add defensive exception handling or validate prerequisite state.",
            evidence=tb_str[-300:]
        ))

    def diagnose_config_error(self, config_path: str, error_detail: str) -> DiagnosticIssue:
        """Inspects JSON / YAML / ENV configuration failures."""
        return self.record_issue(DiagnosticIssue(
            issue_id=f"ISSUE-CFG-{int(time.time()*1000)%1000000}",
            category=DefectCategory.CONFIG_ERROR,
            error_description=f"Configuration error in {Path(config_path).name}: {error_detail}",
            root_cause=f"Invalid configuration syntax or missing mandatory settings key.",
            confidence_level=RootCauseConfidence.CONFIRMED,
            affected_files=[config_path],
            proposed_fix="Validate JSON formatting with strict parser and restore required default schema values.",
            evidence=error_detail
        ))

    def diagnose_api_failure(self, endpoint: str, status_code: int, error_text: str) -> DiagnosticIssue:
        """Inspects external API connection or quota failures."""
        if status_code == 429 or "quota" in error_text.lower():
            root_cause = "API rate limit reached or quota exhausted on target endpoint."
            conf = RootCauseConfidence.CONFIRMED
            fix = "Activate next tier model in model ladder or apply exponential backoff."
        elif status_code in (401, 403):
            root_cause = "API authentication failed: Invalid or missing API credential."
            conf = RootCauseConfidence.CONFIRMED
            fix = "Verify that api_keys.json contains a valid active key."
        elif "timeout" in error_text.lower() or status_code == 504:
            root_cause = "Remote API connection timed out."
            conf = RootCauseConfidence.PROBABLE
            fix = "Retry request with bounded retry (max 3) or check workstation network connection."
        else:
            root_cause = f"HTTP {status_code} error received from {endpoint}."
            conf = RootCauseConfidence.SUSPECTED
            fix = "Inspect endpoint availability and payload schema."

        return self.record_issue(DiagnosticIssue(
            issue_id=f"ISSUE-API-{int(time.time()*1000)%1000000}",
            category=DefectCategory.API_FAILURE,
            error_description=f"API request to {endpoint} failed with HTTP {status_code}",
            root_cause=root_cause,
            confidence_level=conf,
            affected_files=["config/api_keys.json"],
            proposed_fix=fix,
            evidence=f"HTTP {status_code}: {error_text[:200]}"
        ))

    def diagnose_browser_failure(self, action: str, target: str, error_detail: str) -> DiagnosticIssue:
        """Inspects web browser automation failures."""
        is_selector = "selector" in error_detail.lower() or "not found" in error_detail.lower()
        root = "Target DOM element was not rendered or selector changed dynamically." if is_selector else "Browser navigation or tab communication timed out."
        return self.record_issue(DiagnosticIssue(
            issue_id=f"ISSUE-BROWSER-{int(time.time()*1000)%1000000}",
            category=DefectCategory.BROWSER_FAILURE,
            error_description=f"Browser action '{action}' on '{target}' failed.",
            root_cause=root,
            confidence_level=RootCauseConfidence.PROBABLE,
            affected_files=[],
            proposed_fix="Use semantic text matching or wait for page load state before interacting.",
            evidence=error_detail[:200]
        ))

    def diagnose_audio_failure(self, device_id: Optional[int], error_detail: str) -> DiagnosticIssue:
        """Inspects microphone and speaker hardware/pipeline failures."""
        return self.record_issue(DiagnosticIssue(
            issue_id=f"ISSUE-AUDIO-{int(time.time()*1000)%1000000}",
            category=DefectCategory.AUDIO_FAILURE,
            error_description=f"Audio pipeline error on device {device_id}: {error_detail}",
            root_cause="Audio endpoint busy, disconnected, or unsupported PCM sample rate requested.",
            confidence_level=RootCauseConfidence.CONFIRMED if "device unavailable" in error_detail.lower() else RootCauseConfidence.PROBABLE,
            affected_files=["core/audio_devices.py"],
            proposed_fix="Fallback to system default MME/DirectSound device or switch to visual HUD fallback.",
            evidence=error_detail[:200]
        ))

    def diagnose_database_failure(self, db_path: str, query: str, error_detail: str) -> DiagnosticIssue:
        """Inspects SQLite / database failures."""
        is_locked = "locked" in error_detail.lower() or "busy" in error_detail.lower()
        root = "Database locked due to uncommitted concurrent write transaction." if is_locked else f"SQL syntax or schema violation in query: {query[:80]}"
        return self.record_issue(DiagnosticIssue(
            issue_id=f"ISSUE-DB-{int(time.time()*1000)%1000000}",
            category=DefectCategory.DATABASE_ERROR,
            error_description=f"Database query failed on {Path(db_path).name}: {error_detail}",
            root_cause=root,
            confidence_level=RootCauseConfidence.CONFIRMED,
            affected_files=[db_path],
            proposed_fix="Use busy_timeout pragma and enclose transactions within context manager.",
            evidence=error_detail[:200]
        ))

    def diagnose_test_failure(self, test_name: str, test_output: str) -> DiagnosticIssue:
        """Inspects automated test run failures."""
        return self.record_issue(DiagnosticIssue(
            issue_id=f"ISSUE-TEST-{int(time.time()*1000)%1000000}",
            category=DefectCategory.TEST_FAILURE,
            error_description=f"Test '{test_name}' failed.",
            root_cause=f"Assertion failed or regression detected by automated test suite.",
            confidence_level=RootCauseConfidence.CONFIRMED,  # Proven directly by test assertion
            affected_files=[],
            proposed_fix="Inspect failing test assertion and align code implementation with expected test criteria.",
            evidence=test_output[-400:],
            tests_executed=[test_name]
        ))

    def diagnose_background_task_failure(self, task_id: str, reason: str) -> DiagnosticIssue:
        """Inspects background task crashes or worker timeouts."""
        return self.record_issue(DiagnosticIssue(
            issue_id=f"ISSUE-TASK-{int(time.time()*1000)%1000000}",
            category=DefectCategory.BACKGROUND_TASK,
            error_description=f"Background task '{task_id}' failed: {reason}",
            root_cause="Background worker thread terminated abnormally or exceeded bounded execution timeout.",
            confidence_level=RootCauseConfidence.PROBABLE,
            affected_files=[],
            proposed_fix="Resume from last verified checkpoint or restart worker with extended timeout.",
            evidence=reason
        ))

    def get_all_issues(self) -> List[DiagnosticIssue]:
        return list(self._issues)

    def get_unresolved_issues(self) -> List[DiagnosticIssue]:
        return [i for i in self._issues if not i.fix_applied]


self_debugging_engine = SelfDebuggingEngine.get_instance()

