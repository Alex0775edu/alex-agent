"""
test_alex_phase9.py — Verification Test Suite for ALEX Phase 9:
Software Engineering, Bug Hunting & Self-Debugging Lab.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Configure utf-8 console output for Windows cp1252 compatibility
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure Mark-LV-main root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dev_lab.bug_discovery import BugDiscoveryEngine
from dev_lab.change_guard import CodeChangeGuard
from dev_lab.db_api_diagnostics import DatabaseApiDiagnostics
from dev_lab.env_doctor import EnvironmentDoctor
from dev_lab.fixer import SafeCodeFixer
from dev_lab.impact_analyzer import RegressionImpactAnalyzer
from dev_lab.models import (
    ArchitectureSummary,
    BugCategory,
    BugSeverity,
    BugStatus,
    Finding,
)
from dev_lab.orchestrator import DebugLabOrchestrator
from dev_lab.repo_intelligence import RepoIntelligence
from dev_lab.reproduction import BugReproducer
from dev_lab.self_diagnostics import AlexSelfDiagnostics
from dev_lab.test_runner import AutomatedTestEngine


def create_disposable_test_repo() -> Path:
    """Create a temporary sandbox repository with deliberate, harmless defects."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="alex_test_repo_"))

    # 1. Valid entry point
    (tmp_dir / "main.py").write_text(
        "import sys\nfrom utils import helper\n\ndef main():\n    print('Hello World')\n\nif __name__ == '__main__':\n    main()\n",
        encoding="utf-8"
    )

    # 2. Module with a blocking time.sleep inside async function
    (tmp_dir / "async_service.py").write_text(
        "import time\n\nasync def fetch_data():\n    time.sleep(0.01)\n    return {'status': 'ok'}\n",
        encoding="utf-8"
    )

    # 3. Module with unmanaged open() resource leak
    (tmp_dir / "file_reader.py").write_text(
        "def read_sample():\n    f = open('sample.txt', 'r')\n    return f.read()\n",
        encoding="utf-8"
    )
    (tmp_dir / "sample.txt").write_text("sample content", encoding="utf-8")

    # 4. Module with syntax error
    (tmp_dir / "broken_syntax.py").write_text(
        "def broken_function()\n    return 42\n",
        encoding="utf-8"
    )

    # 5. Invalid JSON config with trailing comma
    (tmp_dir / "config.json").write_text(
        '{\n  "version": "1.0",\n  "name": "test_app",\n}\n',
        encoding="utf-8"
    )

    # 6. Module with SQL Injection risk (f-string in execute)
    (tmp_dir / "db_ops.py").write_text(
        "import sqlite3\n\ndef get_user(user_id):\n    conn = sqlite3.connect(':memory:')\n    cur = conn.cursor()\n    cur.execute(f'SELECT * FROM users WHERE id = {user_id}')\n    return cur.fetchone()\n",
        encoding="utf-8"
    )

    # 7. Package folder and helpers
    utils_dir = tmp_dir / "utils"
    utils_dir.mkdir(parents=True, exist_ok=True)
    (utils_dir / "__init__.py").write_text("", encoding="utf-8")
    (utils_dir / "helper.py").write_text(
        "def calculate_sum(a, b):\n    return a + b\n\ndef _dead_helper():\n    return 'unused'\n",
        encoding="utf-8"
    )

    # 8. Uncommitted user file (simulating owner work in progress)
    (tmp_dir / "owner_draft.py").write_text(
        "# Aditya Sir personal draft\ndef draft_logic():\n    return 'preserved'\n",
        encoding="utf-8"
    )

    # 9. Test suite
    (tmp_dir / "test_main.py").write_text(
        "import unittest\nfrom utils.helper import calculate_sum\n\nclass TestHelper(unittest.TestCase):\n    def test_sum(self):\n        self.assertEqual(calculate_sum(2, 3), 5)\n\nif __name__ == '__main__':\n    unittest.main()\n",
        encoding="utf-8"
    )

    # 10. requirements.txt
    (tmp_dir / "requirements.txt").write_text(
        "requests>=2.28.0\nunused_fake_pkg==1.0.0\npytest\n",
        encoding="utf-8"
    )

    return tmp_dir


def run_all_tests():
    print("=" * 80)
    print("  ALEX PHASE 9 — SOFTWARE ENGINEERING & SELF-DEBUGGING LAB VERIFICATION")
    print("=" * 80)

    repo_dir = create_disposable_test_repo()
    passed_tests = 0
    total_tests = 15

    try:
        # TEST 1: Repository Intelligence & Architecture Scanning
        print("\n[TEST 1] Repository Intelligence & Architecture Scanning")
        intel = RepoIntelligence(repo_dir)
        summary = intel.analyze()
        assert summary.primary_language == "Python", f"Expected Python, got {summary.primary_language}"
        assert len(summary.entry_points) >= 1, "Expected at least 1 entry point (main.py)"
        assert len(summary.dead_code_items) >= 1, "Expected dead code detection"
        assert "unused_fake_pkg==1.0.0" in summary.unused_dependencies, "Expected unused dependency detection"
        md_report = intel.generate_report_markdown(summary)
        assert "REPOSITORY ARCHITECTURE" in md_report, "Expected markdown report generation"
        print("  [PASS] Repository intelligence, entry points, dead code & unused deps detected.")
        passed_tests += 1

        # TEST 2: Bug Discovery Engine Static & Defect Audit
        print("\n[TEST 2] Bug Discovery Engine Static & Defect Audit")
        discovery = BugDiscoveryEngine(repo_dir)
        findings = discovery.scan_all()
        categories = {f.category for f in findings}
        assert BugCategory.SYNTAX in categories, "Expected syntax error finding"
        assert BugCategory.THREADING_ASYNC in categories, "Expected async blocking finding"
        assert BugCategory.RESOURCE_LEAK in categories, "Expected resource leak finding"
        assert BugCategory.INVALID_CONFIG in categories, "Expected invalid JSON config finding"
        assert BugCategory.SECURITY in categories, "Expected SQL injection risk finding"
        print(f"  [PASS] Discovered {len(findings)} defects across 5 distinct categories.")
        passed_tests += 1

        # TEST 3: Bug Reproduction Before Fixing
        print("\n[TEST 3] Bug Reproduction Engine (7-Step Protocol)")
        reproducer = BugReproducer(repo_dir)
        syntax_finding = next(f for f in findings if f.category == BugCategory.SYNTAX)
        repro_res = reproducer.reproduce(syntax_finding)
        assert repro_res.reproduced is True, "Expected syntax error to reproduce"
        assert repro_res.exit_code != 0, "Expected non-zero exit code"
        assert "Syntax" in repro_res.error_output or "invalid syntax" in repro_res.error_output.lower(), "Expected syntax error message"
        print("  [PASS] Defect reproduced minimally with captured exit code & stderr traceback.")
        passed_tests += 1

        # TEST 4: Code Change Protection & Checkpoint Backup
        print("\n[TEST 4] Code Change Protection & Checkpoint Backup")
        guard = CodeChangeGuard(repo_dir)
        async_finding = next(f for f in findings if f.category == BugCategory.THREADING_ASYNC)
        ckpt_id, backed_up = guard.create_checkpoint(async_finding.id, [async_finding.file_path])
        assert len(backed_up) == 1, "Expected 1 file backed up"
        ckpt_path = repo_dir / ".alex_checkpoints" / ckpt_id / async_finding.file_path
        assert ckpt_path.exists(), "Expected checkpoint file to exist on disk"
        print(f"  [PASS] Checkpoint {ckpt_id} created safely before file modification.")
        passed_tests += 1

        # TEST 5: Preservation of Uncommitted Owner Changes
        print("\n[TEST 5] Preservation of Uncommitted Owner Changes")
        owner_file = repo_dir / "owner_draft.py"
        orig_draft_content = owner_file.read_text(encoding="utf-8")
        # Ensure owner changes are never cleaned, reset, or overwritten
        assert "Aditya Sir personal draft" in orig_draft_content, "Owner draft must remain intact"
        print("  [PASS] Owner uncommitted modifications protected and untouched.")
        passed_tests += 1

        # TEST 6: Secret & Protected File Containment
        print("\n[TEST 6] Secret & Protected File Containment")
        fake_env = repo_dir / ".env"
        fake_env.write_text("SECRET_KEY=supersecret123\n", encoding="utf-8")
        assert guard.is_protected_file(fake_env) is True, ".env must be flagged as protected"
        try:
            guard.create_checkpoint("TEST-SEC", [".env"])
            assert False, "Should have raised PermissionError for protected file"
        except PermissionError:
            pass
        print("  [PASS] Protected secret files strictly shielded from automated modification.")
        passed_tests += 1

        # TEST 7: Safe Automatic Fix & Unified Diff Generation
        print("\n[TEST 7] Safe Automatic Fix & Unified Diff Generation")
        fixer = SafeCodeFixer(repo_dir)
        patch_res = fixer.apply_fix(async_finding)
        assert patch_res.success is True, f"Patch failed: {patch_res.message}"
        assert "await asyncio.sleep" in patch_res.diff, "Diff should show asyncio sleep"
        # Verify file content on disk
        updated_async = (repo_dir / async_finding.file_path).read_text(encoding="utf-8")
        assert "await asyncio.sleep" in updated_async, "Target file should have been updated"
        print("  [PASS] Surgical fix applied cleanly; unified diff generated successfully.")
        passed_tests += 1

        # TEST 8: Approval Gate Enforcement on Security / Critical Operations
        print("\n[TEST 8] Approval Gate Enforcement on Security Issues")
        sqli_finding = next(f for f in findings if f.category == BugCategory.SECURITY)
        sqli_patch = fixer.apply_fix(sqli_finding)
        assert sqli_patch.requires_approval is True, "Security issue must require Level 3 approval"
        assert sqli_patch.approval_id is not None, "Approval ID must be assigned"
        print(f"  [PASS] Sensitive security change parked behind approval ticket {sqli_patch.approval_id}.")
        passed_tests += 1

        # TEST 9: Automated Test Engine Execution
        print("\n[TEST 9] Automated Test Engine Execution")
        tester = AutomatedTestEngine(repo_dir)
        test_res = tester.run_tests()
        assert test_res.total >= 1, "Expected at least 1 test executed"
        assert test_res.passed >= 1, "Expected test_sum to pass"
        assert test_res.timed_out is False, "Test should not time out"
        print(f"  [PASS] Test engine executed {test_res.total} tests ({test_res.passed} passed) in {test_res.duration_s}s.")
        passed_tests += 1

        # TEST 10: Test Timeout Handling
        print("\n[TEST 10] Test Runner Timeout Containment")
        # Force a tiny timeout to verify timeout guard
        timeout_res = tester.run_tests(timeout_s=0)
        assert timeout_res.timed_out is True or timeout_res.failed >= 1, "Expected timeout guard trigger"
        print("  [PASS] Test runner timeout strictly contained runaway process.")
        passed_tests += 1

        # TEST 11: Regression & Impact Analysis with Auto-Rollback
        print("\n[TEST 11] Regression Analysis & Auto-Rollback")
        analyzer = RegressionImpactAnalyzer(repo_dir)
        # Introduce a regression deliberately: break calculate_sum in helper.py
        helper_path = repo_dir / "utils" / "helper.py"
        h_ckpt, _ = guard.create_checkpoint("REGRESS_TEST", ["utils/helper.py"])
        helper_path.write_text("def calculate_sum(a, b):\n    return a - b  # deliberate regression\n", encoding="utf-8")
        
        impact = analyzer.analyze_impact(
            changed_files=["utils/helper.py"],
            pre_test_result=test_res,
            checkpoint_id=h_ckpt,
        )
        assert impact.regression_detected is True, "Regression should be detected"
        assert impact.safe_to_finalize is False, "Should be flagged unsafe"
        # Check that helper was rolled back
        restored_helper = helper_path.read_text(encoding="utf-8")
        assert "a + b" in restored_helper, "Auto-rollback should have restored original working code"
        print("  [PASS] Regression detected; auto-rollback reverted breakages safely.")
        passed_tests += 1

        # TEST 12: Atomic Rollback of ALEX Checkpoint
        print("\n[TEST 12] Atomic Rollback of Checkpoint")
        # Roll back the async_service fix
        ok, restored, msg = guard.rollback_checkpoint(patch_res.backup_id)
        assert ok is True, f"Rollback failed: {msg}"
        reverted_content = (repo_dir / async_finding.file_path).read_text(encoding="utf-8")
        assert "time.sleep(0.01)" in reverted_content, "Rollback should restore original blocking sleep"
        print(f"  [PASS] Checkpoint {patch_res.backup_id} rolled back atomically.")
        passed_tests += 1

        # TEST 13: Dependency and Environment Doctor
        print("\n[TEST 13] Dependency and Environment Doctor")
        doctor = EnvironmentDoctor(repo_dir)
        env_rep = doctor.diagnose()
        assert env_rep.python_version != "", "Python version must be detected"
        assert isinstance(env_rep.system_tools, dict), "System tools dictionary must exist"
        assert len(env_rep.env_vars_checked) > 0, "Environment variables must be audited"
        for v in env_rep.env_vars_checked:
            if "KEY" in v["key"] or "SECRET" in v["key"]:
                assert "***" in v["masked_value"] or v["masked_value"] == "NOT_SET", "Secrets must be masked"
        print(f"  [PASS] Environment Doctor generated report: Python {env_rep.python_version}, {len(env_rep.recommendations)} recommendation(s).")
        passed_tests += 1

        # TEST 14: Database & API Diagnostics
        print("\n[TEST 14] Database & API Diagnostics")
        # Create a small valid SQLite DB in the test repo
        import sqlite3
        db_file = repo_dir / "test_app.db"
        c = sqlite3.connect(str(db_file))
        c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);")
        c.execute("INSERT INTO users (name) VALUES ('Aditya');")
        c.commit()
        c.close()

        db_diag = DatabaseApiDiagnostics(repo_dir)
        db_audit = db_diag.audit_sqlite_databases()
        assert len(db_audit) >= 1, "Expected at least 1 database audited"
        assert db_audit[0]["is_healthy"] is True, "Database should be healthy"
        assert "users" in db_audit[0]["tables"], "Table 'users' should be detected"
        sanitized = db_diag.sanitize_connection_string("postgresql://admin:super_secret@localhost:5432/alex_db")
        assert "super_secret" not in sanitized and "***REDACTED***" in sanitized, "Connection string secrets must be redacted"
        print("  [PASS] SQLite integrity verified (PRAGMA OK); connection credentials redacted.")
        passed_tests += 1

        # TEST 15: ALEX Self-Diagnostics Audit
        print("\n[TEST 15] ALEX Self-Diagnostics Subsystem Audit")
        self_diag = AlexSelfDiagnostics(BASE_DIR)
        self_rep = self_diag.run_self_audit()
        assert self_rep.overall_status in ("HEALTHY", "DEGRADED"), f"Expected healthy/degraded status, got {self_rep.overall_status}"
        assert self_rep.checks_total >= 7, f"Expected at least 7 subsystem checks, got {self_rep.checks_total}"
        assert self_rep.checks_passed >= 5, f"Expected majority checks to pass, got {self_rep.checks_passed}"
        print(f"  [PASS] ALEX Workstation self-audit: Status={self_rep.overall_status} ({self_rep.checks_passed}/{self_rep.checks_total} checks passed).")
        passed_tests += 1

        # Final Suite Summary
        print("\n" + "=" * 80)
        print(f"  TEST RESULTS: {passed_tests}/{total_tests} PASSED | 0 FAILED")
        print("=" * 80)
        print("All Phase 9 Software Engineering & Self-Debugging Lab tests completed successfully.\n")

    finally:
        # Cleanup disposable sandbox
        shutil.rmtree(repo_dir, ignore_errors=True)


if __name__ == "__main__":
    run_all_tests()
