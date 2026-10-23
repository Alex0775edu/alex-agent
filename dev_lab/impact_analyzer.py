"""
dev_lab/impact_analyzer.py — Regression Analysis, Dependency Traversal & Safe Rollback.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Dict, List, Set

from dev_lab.change_guard import CodeChangeGuard
from dev_lab.models import ImpactReport, TestRunResult
from dev_lab.test_runner import AutomatedTestEngine


class RegressionImpactAnalyzer:
    """Performs impact and regression analysis when code modifications occur:

    1. Traces all dependent callers and importing modules.
    2. Runs test suites to detect regressions.
    3. Reverts ALEX-applied changes automatically if regressions are found.
    """

    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()
        self.guard = CodeChangeGuard(self.root)
        self.tester = AutomatedTestEngine(self.root)

    def analyze_impact(
        self,
        changed_files: List[str],
        pre_test_result: Optional[TestRunResult] = None,
        checkpoint_id: Optional[str] = None
    ) -> ImpactReport:
        """Evaluate dependencies and execute regression tests."""
        dependent_modules: Set[str] = set()
        affected_callers: Set[str] = set()

        # 1. Dependency graph traversal
        changed_stems = {Path(f).stem for f in changed_files}

        for root, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".venv", "venv", ".alex_checkpoints"}]
            for f in files:
                if f.endswith(".py"):
                    p = Path(root) / f
                    rel_str = str(p.relative_to(self.root)).replace("\\", "/")
                    if rel_str in changed_files:
                        continue
                    try:
                        content = p.read_text(encoding="utf-8", errors="ignore")
                        # Check if any changed module is imported
                        for stem in changed_stems:
                            if f"import {stem}" in content or f"from {stem}" in content:
                                dependent_modules.add(rel_str)
                    except Exception:
                        pass

        # 2. Run regression tests
        post_test = self.tester.run_tests()
        regression_detected = False
        regression_details: List[str] = []

        if pre_test_result:
            # Check if failures increased or new errors appeared
            if post_test.failed > pre_test_result.failed or post_test.errors > pre_test_result.errors:
                regression_detected = True
                regression_details.append(
                    f"Test failures increased from {pre_test_result.failed} to {post_test.failed} "
                    f"(errors: {pre_test_result.errors} -> {post_test.errors})"
                )

        if post_test.timed_out:
            regression_detected = True
            regression_details.append("Post-fix test suite timed out.")

        # 3. Automatic Rollback if regression is detected
        safe_to_finalize = not regression_detected
        if regression_detected and checkpoint_id:
            ok, restored, msg = self.guard.rollback_checkpoint(checkpoint_id)
            regression_details.append(f"Auto-rollback triggered: {msg}")

        return ImpactReport(
            changed_files=changed_files,
            dependent_modules=sorted(list(dependent_modules)),
            affected_callers=sorted(list(affected_callers)),
            regression_detected=regression_detected,
            regression_details=regression_details,
            safe_to_finalize=safe_to_finalize,
        )

