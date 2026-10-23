"""
dev_lab/self_diagnostics.py — ALEX Workstation Self-Diagnostics & Subsystem Health Audit.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import json
import os
import py_compile
import sqlite3
import sys
from pathlib import Path
from typing import List

from dev_lab.models import BugSeverity, SelfDiagnosticCheck, SelfDiagnosticReport


class AlexSelfDiagnostics:
    """Deep inspection engine for ALEX's own architecture, configuration,

    databases, audio devices, and registered tool health.
    """

    def __init__(self, alex_root: str | Path):
        self.root = Path(alex_root).resolve()

    def run_self_audit(self) -> SelfDiagnosticReport:
        """Execute exhaustive diagnostic check across all ALEX subsystems."""
        checks: List[SelfDiagnosticCheck] = []

        # 1. Core Architecture Files Presence
        checks.append(self._check_core_files())

        # 2. Python Bytecode Compilation Integrity
        checks.append(self._check_compilation())

        # 3. Security Manager & Owner Identity
        checks.append(self._check_security_manager())

        # 4. Storage & Memory Databases
        checks.append(self._check_storage_integrity())

        # 5. Skills Engine Registration
        checks.append(self._check_skills_engine())

        # 6. Audio Subsystem Health
        checks.append(self._check_audio_subsystem())

        # 7. Model Provider Configuration
        checks.append(self._check_model_provider_config())

        # 8. Dashboard Web Assets
        checks.append(self._check_dashboard_assets())

        # Aggregate metrics
        passed = sum(1 for c in checks if c.status == "PASS")
        warned = sum(1 for c in checks if c.status == "WARN")
        failed = sum(1 for c in checks if c.status == "FAIL")

        overall = "HEALTHY"
        if failed > 0:
            overall = "CRITICAL" if any(c.severity == BugSeverity.CRITICAL for c in checks if c.status == "FAIL") else "DEGRADED"
        elif warned > 0:
            overall = "DEGRADED"

        return SelfDiagnosticReport(
            overall_status=overall,
            checks_total=len(checks),
            checks_passed=passed,
            checks_failed=failed,
            checks_warned=warned,
            checks=checks,
        )

    def _check_core_files(self) -> SelfDiagnosticCheck:
        required_dirs = ["core", "actions", "skills", "workflow", "dashboard", "memory", "config"]
        missing = [d for d in required_dirs if not (self.root / d).is_dir()]

        if missing:
            return SelfDiagnosticCheck(
                component="Architecture Structure",
                status="FAIL",
                severity=BugSeverity.CRITICAL,
                message=f"Missing essential directory trees: {missing}",
                evidence=f"Directory audit against root: {self.root}",
                probable_cause="Incomplete clone or accidental folder deletion.",
                suggested_steps="Restore missing directories from repository base.",
            )
        return SelfDiagnosticCheck(
            component="Architecture Structure",
            status="PASS",
            severity=BugSeverity.INFO,
            message="All core directory trees present and verified.",
            evidence=f"Verified 7 core packages in {self.root}",
        )

    def _check_compilation(self) -> SelfDiagnosticCheck:
        errors = []
        count = 0
        for py_path in self.root.rglob("*.py"):
            if any(ign in str(py_path) for ign in [".git", "__pycache__", ".venv", "venv", ".alex_checkpoints"]):
                continue
            count += 1
            try:
                py_compile.compile(str(py_path), doraise=True)
            except Exception as e:
                errors.append(f"{py_path.name}: {e}")

        if errors:
            return SelfDiagnosticCheck(
                component="Bytecode Compilation",
                status="FAIL",
                severity=BugSeverity.HIGH,
                message=f"Compilation failure in {len(errors)} file(s).",
                evidence="\n".join(errors[:3]),
                probable_cause="Syntax or encoding error in Python sources.",
                suggested_steps="Run test_alex_master.py to inspect failed files.",
            )
        return SelfDiagnosticCheck(
            component="Bytecode Compilation",
            status="PASS",
            severity=BugSeverity.INFO,
            message=f"All {count} Python files compiled cleanly with 0 syntax errors.",
            evidence=f"Clean compilation across {count} modules.",
        )

    def _check_security_manager(self) -> SelfDiagnosticCheck:
        try:
            from core.security import OWNER_ADDRESS, security_manager
            sec = security_manager
            owner = sec.get_current_identity()
            address = OWNER_ADDRESS
            if owner == "Aditya Rajak" and address == "Sir":
                return SelfDiagnosticCheck(
                    component="Security & Owner Vault",
                    status="PASS",
                    severity=BugSeverity.INFO,
                    message="Owner identity and security vault verified successfully.",
                    evidence=f"Owner: {owner} | Addressing: {address} | Lock: {sec.is_locked()}",
                )
            else:
                return SelfDiagnosticCheck(
                    component="Security & Owner Vault",
                    status="WARN",
                    severity=BugSeverity.HIGH,
                    message=f"Owner identity mismatch: {owner}",
                    evidence=f"Owner configured as '{owner}'",
                    probable_cause="Unexpected config override in security settings.",
                    suggested_steps="Verify config/owner_credentials.json settings.",
                )
        except Exception as e:
            return SelfDiagnosticCheck(
                component="Security & Owner Vault",
                status="FAIL",
                severity=BugSeverity.CRITICAL,
                message=f"Security manager initialization failed: {e}",
                evidence=str(e),
                probable_cause="Missing dependency or DPAPI vault error.",
                suggested_steps="Inspect core/security.py and DPAPI vault key.",
            )

    def _check_storage_integrity(self) -> SelfDiagnosticCheck:
        db_path = self.root / "alex_brain.db"
        if not db_path.exists():
            return SelfDiagnosticCheck(
                component="Storage & Memory Databases",
                status="WARN",
                severity=BugSeverity.MEDIUM,
                message="alex_brain.db not found yet; running on memory storage.",
                evidence=f"Checked {db_path}",
                probable_cause="First-time launch before initialization.",
                suggested_steps="Initialize database via MemoryManager.",
            )
        try:
            conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            res = cur.fetchone()[0]
            conn.close()
            if res.lower() == "ok":
                return SelfDiagnosticCheck(
                    component="Storage & Memory Databases",
                    status="PASS",
                    severity=BugSeverity.INFO,
                    message="alex_brain.db SQLite database integrity verified (OK).",
                    evidence="PRAGMA integrity_check returned OK.",
                )
            else:
                return SelfDiagnosticCheck(
                    component="Storage & Memory Databases",
                    status="FAIL",
                    severity=BugSeverity.HIGH,
                    message=f"Database corruption detected: {res}",
                    evidence=res,
                    probable_cause="Improper shutdown or concurrent write error.",
                    suggested_steps="Restore from backup or rebuild SQLite index.",
                )
        except Exception as e:
            return SelfDiagnosticCheck(
                component="Storage & Memory Databases",
                status="FAIL",
                severity=BugSeverity.HIGH,
                message=f"Storage error: {e}",
                evidence=str(e),
            )

    def _check_skills_engine(self) -> SelfDiagnosticCheck:
        try:
            from skills.engine import skills_engine
            installed = skills_engine.list_skills()
            return SelfDiagnosticCheck(
                component="Skills Engine Registry",
                status="PASS",
                severity=BugSeverity.INFO,
                message=f"Skills Engine online with {len(installed)} registered skills.",
                evidence=f"Loaded skills: {[s.id for s in installed[:5]]}",
            )
        except Exception as e:
            return SelfDiagnosticCheck(
                component="Skills Engine Registry",
                status="WARN",
                severity=BugSeverity.MEDIUM,
                message=f"Skills Engine warning: {e}",
                evidence=str(e),
                probable_cause="Optional skills module missing dependencies.",
                suggested_steps="Inspect skills/engine.py and plugin manifests.",
            )

    def _check_audio_subsystem(self) -> SelfDiagnosticCheck:
        try:
            import sounddevice as sd
            devs = sd.query_devices()
            in_devs = [d for d in devs if d.get("max_input_channels", 0) > 0]
            out_devs = [d for d in devs if d.get("max_output_channels", 0) > 0]
            if in_devs and out_devs:
                return SelfDiagnosticCheck(
                    component="Audio Hardware Resolution",
                    status="PASS",
                    severity=BugSeverity.INFO,
                    message=f"Audio resolved: {len(in_devs)} input device(s), {len(out_devs)} output device(s).",
                    evidence=f"Microphone: {in_devs[0].get('name')}",
                )
            else:
                return SelfDiagnosticCheck(
                    component="Audio Hardware Resolution",
                    status="WARN",
                    severity=BugSeverity.LOW,
                    message="Audio devices partially resolved.",
                    evidence=f"Inputs: {len(in_devs)}, Outputs: {len(out_devs)}",
                    probable_cause="Headless or virtualized environment.",
                    suggested_steps="Connect a microphone or audio output device.",
                )
        except Exception as e:
            return SelfDiagnosticCheck(
                component="Audio Hardware Resolution",
                status="WARN",
                severity=BugSeverity.LOW,
                message=f"Sounddevice probe warning: {e}",
                evidence=str(e),
                probable_cause="No audio driver available in session.",
                suggested_steps="Check Windows audio service.",
            )

    def _check_model_provider_config(self) -> SelfDiagnosticCheck:
        cfg = self.root / "config" / "api_keys.json"
        if not cfg.exists():
            return SelfDiagnosticCheck(
                component="Model Provider Configuration",
                status="WARN",
                severity=BugSeverity.MEDIUM,
                message="config/api_keys.json not found.",
                evidence=f"Checked {cfg}",
                probable_cause="First-time installation without configured API keys.",
                suggested_steps="Configure gemini_api_key in config/api_keys.json.",
            )
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            has_gemini = bool(data.get("gemini_api_key"))
            return SelfDiagnosticCheck(
                component="Model Provider Configuration",
                status="PASS" if has_gemini else "WARN",
                severity=BugSeverity.INFO if has_gemini else BugSeverity.MEDIUM,
                message="Gemini API key configured." if has_gemini else "Gemini API key is empty.",
                evidence=f"Key present: {has_gemini}",
            )
        except Exception as e:
            return SelfDiagnosticCheck(
                component="Model Provider Configuration",
                status="FAIL",
                severity=BugSeverity.HIGH,
                message=f"Failed to parse config/api_keys.json: {e}",
                evidence=str(e),
            )

    def _check_dashboard_assets(self) -> SelfDiagnosticCheck:
        app_html = self.root / "dashboard" / "static" / "app.html"
        server_py = self.root / "dashboard" / "server.py"
        if app_html.exists() and server_py.exists():
            return SelfDiagnosticCheck(
                component="Dashboard Web Assets",
                status="PASS",
                severity=BugSeverity.INFO,
                message="Command center HTML app and FastAPI server present and verified.",
                evidence=f"Verified {app_html.name} ({app_html.stat().st_size} bytes)",
            )
        return SelfDiagnosticCheck(
            component="Dashboard Web Assets",
            status="FAIL",
            severity=BugSeverity.HIGH,
            message="Dashboard server or static HTML asset missing.",
            evidence=f"Checked {app_html} and {server_py}",
        )
