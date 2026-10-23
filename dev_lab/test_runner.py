"""
dev_lab/test_runner.py — Automated Test Engine, Framework Detection & Timeout Containment.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dev_lab.models import TestRunResult


class AutomatedTestEngine:
    """Discovers, executes, and parses test suites across Python and other frameworks.

    Guarantees:
    - Real execution (zero invented results)
    - Strict timeout handling
    - Live service / production protection
    """

    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()

    def detect_framework(self) -> str:
        """Identify available testing framework."""
        # 1. Pytest
        if (self.root / "pytest.ini").exists() or (self.root / "pyproject.toml").exists():
            return "pytest"
        
        # Check if pytest is importable and test files exist
        has_tests = any(self.root.rglob("test_*.py")) or any(self.root.rglob("*_test.py"))
        if has_tests:
            try:
                import pytest
                return "pytest"
            except ImportError:
                return "unittest"

        # 2. Node / Jest
        if (self.root / "package.json").exists():
            return "npm_test"

        return "unittest"

    def run_tests(self, test_filter: Optional[str] = None, timeout_s: int = 45) -> TestRunResult:
        """Run project tests with real subprocess isolation and timeout."""
        framework = self.detect_framework()
        start_time = time.time()

        env = os.environ.copy()
        cur_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{str(self.root)}{os.pathsep}{cur_pp}"

        # Production / live service safety guard
        env["ALEX_TEST_ENV"] = "ISOLATED_TEST"
        env["ENVIRONMENT"] = "testing"

        cmd: List[str] = []
        if framework == "pytest":
            cmd = [sys.executable, "-m", "pytest", "-v"]
            if test_filter:
                cmd.append(test_filter)
        elif framework == "npm_test":
            cmd = ["npm", "test"]
        else:
            # Python unittest
            cmd = [sys.executable, "-m", "unittest", "discover", "-s", str(self.root), "-p", "test_*.py"]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
                cwd=str(self.root),
                env=env,
            )

            raw = f"{proc.stdout}\n{proc.stderr}".strip()
            duration = round(time.time() - start_time, 2)

            return self._parse_output(raw, framework, proc.returncode, duration)

        except subprocess.TimeoutExpired:
            duration = round(time.time() - start_time, 2)
            return TestRunResult(
                total=1,
                passed=0,
                failed=1,
                skipped=0,
                errors=1,
                timed_out=True,
                duration_s=duration,
                framework=framework,
                raw_output=f"Test runner timed out after {timeout_s} seconds.",
                failures_detail=[{"test": "TestSuite", "reason": f"Execution timed out (> {timeout_s}s)"}],
            )
        except Exception as e:
            duration = round(time.time() - start_time, 2)
            return TestRunResult(
                total=0,
                passed=0,
                failed=0,
                skipped=0,
                errors=1,
                timed_out=False,
                duration_s=duration,
                framework=framework,
                raw_output=f"Test invocation error: {e}",
                failures_detail=[{"test": "ExecutionFailure", "reason": str(e)}],
            )

    def _parse_output(self, output: str, framework: str, returncode: int, duration: float) -> TestRunResult:
        """Accurately parse test output to extract metrics without hallucination."""
        passed = 0
        failed = 0
        skipped = 0
        errors = 0
        total = 0
        failures_detail: List[Dict[str, Any]] = []

        if framework == "pytest":
            # e.g.: === 5 passed, 1 failed, 2 skipped in 1.23s ===
            m_pass = re.search(r'(\d+)\s+passed', output)
            m_fail = re.search(r'(\d+)\s+failed', output)
            m_skip = re.search(r'(\d+)\s+skipped', output)
            m_err = re.search(r'(\d+)\s+error', output)

            if m_pass:
                passed = int(m_pass.group(1))
            if m_fail:
                failed = int(m_fail.group(1))
            if m_skip:
                skipped = int(m_skip.group(1))
            if m_err:
                errors = int(m_err.group(1))

            total = passed + failed + skipped + errors

            # Extract failure messages
            fail_blocks = re.findall(r'FAILED\s+([^\s]+)\s+-\s+(.+)', output)
            for test_name, reason in fail_blocks:
                failures_detail.append({"test": test_name, "reason": reason.strip()})

        elif framework == "unittest":
            # e.g.: Ran 7 tests in 0.052s\n\nFAILED (failures=2, errors=1)
            # or: Ran 5 tests in 0.021s\n\nOK (skipped=1)
            m_ran = re.search(r'Ran\s+(\d+)\s+test', output)
            if m_ran:
                total = int(m_ran.group(1))

            if "OK" in output and returncode == 0:
                m_skip = re.search(r'skipped=(\d+)', output)
                if m_skip:
                    skipped = int(m_skip.group(1))
                passed = max(0, total - skipped)
            else:
                m_fail = re.search(r'failures=(\d+)', output)
                m_err = re.search(r'errors=(\d+)', output)
                if m_fail:
                    failed = int(m_fail.group(1))
                if m_err:
                    errors = int(m_err.group(1))
                passed = max(0, total - failed - errors)

        else:
            # Fallback parsing
            if returncode == 0:
                total = 1
                passed = 1
            else:
                total = 1
                failed = 1

        if total == 0 and returncode == 0 and "no tests ran" in output.lower():
            total = 0

        return TestRunResult(
            total=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            timed_out=False,
            duration_s=duration,
            framework=framework,
            raw_output=output,
            failures_detail=failures_detail,
        )

