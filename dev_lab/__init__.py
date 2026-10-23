"""
dev_lab/__init__.py — ALEX Phase 9 Software Engineering, Bug Hunting & Self-Debugging Lab.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from dev_lab.models import (
    ArchitectureSummary,
    BugCategory,
    BugSeverity,
    BugStatus,
    EnvironmentReport,
    Finding,
    ImpactReport,
    PatchResult,
    ReproductionResult,
    SelfDiagnosticCheck,
    SelfDiagnosticReport,
    TestRunResult,
)
from dev_lab.repo_intelligence import RepoIntelligence
from dev_lab.bug_discovery import BugDiscoveryEngine
from dev_lab.reproduction import BugReproducer
from dev_lab.change_guard import CodeChangeGuard
from dev_lab.fixer import SafeCodeFixer
from dev_lab.test_runner import AutomatedTestEngine
from dev_lab.impact_analyzer import RegressionImpactAnalyzer
from dev_lab.env_doctor import EnvironmentDoctor
from dev_lab.db_api_diagnostics import DatabaseApiDiagnostics
from dev_lab.self_diagnostics import AlexSelfDiagnostics
from dev_lab.orchestrator import DebugLabOrchestrator

__all__ = [
    "ArchitectureSummary",
    "BugCategory",
    "BugSeverity",
    "BugStatus",
    "EnvironmentReport",
    "Finding",
    "ImpactReport",
    "PatchResult",
    "ReproductionResult",
    "SelfDiagnosticCheck",
    "SelfDiagnosticReport",
    "TestRunResult",
    "RepoIntelligence",
    "BugDiscoveryEngine",
    "BugReproducer",
    "CodeChangeGuard",
    "SafeCodeFixer",
    "AutomatedTestEngine",
    "RegressionImpactAnalyzer",
    "EnvironmentDoctor",
    "DatabaseApiDiagnostics",
    "AlexSelfDiagnostics",
    "DebugLabOrchestrator",
]

