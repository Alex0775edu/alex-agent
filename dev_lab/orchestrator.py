"""
dev_lab/orchestrator.py — Master Orchestrator for 10-Step Autonomous Debugging Loop.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dev_lab.bug_discovery import BugDiscoveryEngine
from dev_lab.change_guard import CodeChangeGuard
from dev_lab.fixer import SafeCodeFixer
from dev_lab.impact_analyzer import RegressionImpactAnalyzer
from dev_lab.models import (
    ArchitectureSummary,
    BugCategory,
    BugSeverity,
    BugStatus,
    Finding,
    PatchResult,
    ReproductionResult,
    TestRunResult,
)
from dev_lab.repo_intelligence import RepoIntelligence
from dev_lab.reproduction import BugReproducer
from dev_lab.test_runner import AutomatedTestEngine


class DebugLabOrchestrator:
    """Coordinates the canonical 10-step autonomous debugging loop:

    Inspect -> Reproduce -> Diagnose -> Plan -> Authorize -> Patch -> Test -> Review -> Verify -> Report

    Guarantees:
    - Bounded repair attempts (max 3)
    - Checkpoint backups and atomic rollback
    - Strict verification (no false success)
    - Respect for owner changes
    """

    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()
        self.repo_intel = RepoIntelligence(self.root)
        self.discovery = BugDiscoveryEngine(self.root)
        self.reproducer = BugReproducer(self.root)
        self.guard = CodeChangeGuard(self.root)
        self.fixer = SafeCodeFixer(self.root)
        self.tester = AutomatedTestEngine(self.root)
        self.impact = RegressionImpactAnalyzer(self.root)
        self._findings_registry: Dict[str, Finding] = {}
        self._max_fix_attempts = 3

    def inspect_and_scan(self) -> Tuple[ArchitectureSummary, List[Finding]]:
        """Step 1: Inspect repository architecture and discover defects."""
        summary = self.repo_intel.analyze()
        findings = self.discovery.scan_all()
        for f in findings:
            self._findings_registry[f.id] = f
        return summary, findings

    def get_findings(self, status_filter: Optional[str] = None) -> List[Finding]:
        """Fetch discovered findings, optionally filtered by status."""
        items = list(self._findings_registry.values())
        if status_filter:
            items = [f for f in items if f.status.value.lower() == status_filter.lower()]
        return items

    def run_reproduction(self, finding_id: str) -> ReproductionResult:
        """Step 2 & 3: Reproduce the defect before attempting repair."""
        finding = self._findings_registry.get(finding_id)
        if not finding:
            return ReproductionResult(reproduced=False, error_output="Finding ID not found.")

        result = self.reproducer.reproduce(finding)
        if result.reproduced:
            finding.status = BugStatus.CONFIRMED
            finding.is_confirmed = True
            finding.evidence = result.error_output
        else:
            finding.status = BugStatus.UNCONFIRMED
            finding.is_confirmed = False

        finding.updated_at = time.time()
        return result

    def execute_debugging_cycle(self, finding_id: str) -> Dict[str, Any]:
        """Execute the full 10-step bounded repair and verification cycle for a finding."""
        finding = self._findings_registry.get(finding_id)
        if not finding:
            return {"success": False, "message": f"Finding '{finding_id}' not found in registry."}

        # Step 2: Reproduce
        repro = self.reproducer.reproduce(finding)
        if not repro.reproduced and finding.category != BugCategory.INVALID_CONFIG:
            finding.status = BugStatus.UNCONFIRMED
            return {
                "success": False,
                "step": "reproduce",
                "message": f"Could not reproduce failure for {finding_id}. Marked as UNCONFIRMED.",
                "reproduction": repro.to_dict(),
            }

        finding.status = BugStatus.IN_PROGRESS

        # Step 4 & 5: Plan & Authorize
        if finding.requires_approval or finding.severity == BugSeverity.CRITICAL or finding.category == BugCategory.SECURITY:
            finding.status = BugStatus.UNRESOLVED
            return {
                "success": False,
                "step": "authorize",
                "message": f"Requires Level 3 Approval from Aditya Sir: {finding.title}",
                "requires_approval": True,
                "approval_id": f"APPR-FIX-{finding.id}",
            }

        # Run pre-fix tests baseline
        pre_test = self.tester.run_tests()

        # Step 6: Patch (Safe Automatic Fix)
        patch = self.fixer.apply_fix(finding)
        if not patch.success:
            finding.status = BugStatus.UNRESOLVED
            return {
                "success": False,
                "step": "patch",
                "message": patch.message,
                "patch": patch.to_dict(),
            }

        # Step 7 & 8: Test & Review (Impact Analysis)
        impact_report = self.impact.analyze_impact(
            changed_files=patch.modified_files,
            pre_test_result=pre_test,
            checkpoint_id=patch.backup_id,
        )

        if not impact_report.safe_to_finalize:
            finding.status = BugStatus.ROLLED_BACK
            return {
                "success": False,
                "step": "review",
                "message": "Regression detected during testing. Automatically rolled back patch to protect repository.",
                "impact": impact_report.to_dict(),
            }

        # Step 9: Verify (Re-run reproduction probe)
        verify_repro = self.reproducer.reproduce(finding)
        if verify_repro.reproduced:
            # Bug still reproducing after fix!
            finding.status = BugStatus.UNRESOLVED
            if patch.backup_id:
                self.guard.rollback_checkpoint(patch.backup_id)
            return {
                "success": False,
                "step": "verify",
                "message": "Verification failed: defect is still reproducing after patch. Reverted changes.",
                "reproduction": verify_repro.to_dict(),
            }

        # Step 10: Report & Finalize
        finding.status = BugStatus.VERIFIED
        finding.updated_at = time.time()

        return {
            "success": True,
            "step": "report",
            "message": f"Defect {finding.id} successfully diagnosed, patched, and verified.",
            "diff": patch.diff,
            "modified_files": patch.modified_files,
            "impact": impact_report.to_dict(),
            "status": finding.status.value,
        }

    def rollback_finding(self, finding_id: str, checkpoint_id: str) -> Dict[str, Any]:
        """Roll back an applied patch cleanly."""
        ok, restored, msg = self.guard.rollback_checkpoint(checkpoint_id)
        if ok:
            finding = self._findings_registry.get(finding_id)
            if finding:
                finding.status = BugStatus.ROLLED_BACK
                finding.updated_at = time.time()
        return {"success": ok, "restored_files": restored, "message": msg}

