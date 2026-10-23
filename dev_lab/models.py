"""
dev_lab/models.py — Data models for ALEX Software Engineering & Self-Debugging Lab.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class BugSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class BugStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    UNCONFIRMED = "UNCONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    FIXED = "FIXED"
    VERIFIED = "VERIFIED"
    UNRESOLVED = "UNRESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    ROLLBACK_REQUESTED = "ROLLBACK_REQUESTED"
    ROLLED_BACK = "ROLLED_BACK"


class BugCategory(str, Enum):
    SYNTAX = "SYNTAX"
    IMPORT = "IMPORT"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    RUNTIME = "RUNTIME"
    ARGUMENT_MISMATCH = "ARGUMENT_MISMATCH"
    MISSING_FILE = "MISSING_FILE"
    INVALID_CONFIG = "INVALID_CONFIG"
    DATABASE = "DATABASE"
    API_INTEGRATION = "API_INTEGRATION"
    UI_EVENT = "UI_EVENT"
    THREADING_ASYNC = "THREADING_ASYNC"
    RESOURCE_LEAK = "RESOURCE_LEAK"
    RACE_CONDITION = "RACE_CONDITION"
    SECURITY = "SECURITY"
    LOGIC = "LOGIC"


@dataclass
class Finding:
    """Represents a discovered defect, risk, or static analysis finding."""
    id: str
    file_path: str
    line_number: Optional[int]
    category: BugCategory
    severity: BugSeverity
    status: BugStatus
    title: str
    description: str
    evidence: str
    reproduction_steps: str = ""
    suggested_fix: str = ""
    diff: str = ""
    test_case: str = ""
    is_confirmed: bool = False
    requires_approval: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        d["severity"] = self.severity.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Finding:
        return cls(
            id=data["id"],
            file_path=data["file_path"],
            line_number=data.get("line_number"),
            category=BugCategory(data["category"]),
            severity=BugSeverity(data["severity"]),
            status=BugStatus(data["status"]),
            title=data["title"],
            description=data["description"],
            evidence=data.get("evidence", ""),
            reproduction_steps=data.get("reproduction_steps", ""),
            suggested_fix=data.get("suggested_fix", ""),
            diff=data.get("diff", ""),
            test_case=data.get("test_case", ""),
            is_confirmed=data.get("is_confirmed", False),
            requires_approval=data.get("requires_approval", False),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )


@dataclass
class ArchitectureSummary:
    """Summary of project architecture and dependencies."""
    project_name: str
    project_path: str
    primary_language: str
    frameworks: List[str]
    entry_points: List[str]
    modules_count: int
    dependencies_count: int
    external_dependencies: List[str]
    unused_dependencies: List[str]
    circular_imports: List[List[str]]
    dead_code_items: List[Dict[str, Any]]
    duplicate_logic_items: List[Dict[str, Any]]
    todos_and_fixmes: List[Dict[str, Any]]
    missing_tests: List[str]
    error_handling_risks: List[Dict[str, Any]]
    security_risks: List[Dict[str, Any]]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReproductionResult:
    """Result of attempting to reproduce a bug."""
    reproduced: bool
    error_output: str
    repro_script_path: Optional[str] = None
    traceback: Optional[str] = None
    notes: str = ""
    exit_code: int = 0
    duration_s: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PatchResult:
    """Result of applying a proposed code change."""
    success: bool
    modified_files: List[str]
    diff: str
    requires_approval: bool = False
    approval_id: Optional[str] = None
    message: str = ""
    backup_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TestRunResult:
    """Result of running project automated tests."""
    total: int
    passed: int
    failed: int
    skipped: int
    errors: int
    timed_out: bool
    duration_s: float
    framework: str
    raw_output: str
    failures_detail: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.failed == 0 and self.errors == 0 and not self.timed_out and self.total > 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["is_success"] = self.is_success
        return d


@dataclass
class ImpactReport:
    """Impact and regression analysis."""
    changed_files: List[str]
    dependent_modules: List[str]
    affected_callers: List[str]
    regression_detected: bool
    regression_details: List[str] = field(default_factory=list)
    safe_to_finalize: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EnvironmentReport:
    """Environment and dependency audit report."""
    python_version: str
    is_virtualenv: bool
    venv_path: Optional[str]
    installed_packages_count: int
    missing_packages: List[str]
    conflicts: List[str]
    env_vars_checked: List[Dict[str, Any]]
    system_tools: Dict[str, bool]
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SelfDiagnosticCheck:
    """Individual diagnostic check on ALEX itself."""
    component: str
    status: str  # PASS, WARN, FAIL
    severity: BugSeverity
    message: str
    evidence: str
    probable_cause: str = ""
    suggested_steps: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


@dataclass
class SelfDiagnosticReport:
    """Complete diagnostic report of ALEX personal AI workstation."""
    overall_status: str  # HEALTHY, DEGRADED, CRITICAL
    checks_total: int
    checks_passed: int
    checks_failed: int
    checks_warned: int
    checks: List[SelfDiagnosticCheck]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "checks_total": self.checks_total,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "checks_warned": self.checks_warned,
            "checks": [c.to_dict() for c in self.checks],
            "timestamp": self.timestamp,
        }

