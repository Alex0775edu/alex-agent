"""
dev_lab/env_doctor.py — Dependency and Environment Doctor for ALEX Workstation.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dev_lab.models import EnvironmentReport


class EnvironmentDoctor:
    """Diagnoses runtime environments, package versions, virtualenvs,

    system tools, and environment variables.
    """

    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()

    def diagnose(self) -> EnvironmentReport:
        """Run full environment diagnosis and return structured report."""
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        is_venv = (
            hasattr(sys, "real_prefix") or
            (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
        )
        venv_path = sys.prefix if is_venv else None

        # Check installed packages
        installed_pkgs = self._get_installed_packages()
        missing_pkgs, conflicts = self._check_requirements(installed_pkgs)

        # Check essential system tools
        system_tools = {
            "python": True,
            "git": shutil.which("git") is not None,
            "code": shutil.which("code") is not None,
            "curl": shutil.which("curl") is not None,
            "sqlite3": True,  # Python built-in
        }

        # Check environment variables
        env_vars = self._check_env_vars()

        # Build recommendations
        recs: List[str] = []
        if not is_venv:
            recs.append("Recommendation: Run project within an isolated Python virtual environment (e.g. 'python -m venv .venv').")
        if missing_pkgs:
            recs.append(f"Missing packages: Run 'pip install {' '.join(missing_pkgs)}' to satisfy requirements.")
        if conflicts:
            recs.append(f"Version conflicts detected in {len(conflicts)} packages. Review pyproject.toml / requirements.txt.")

        return EnvironmentReport(
            python_version=py_ver,
            is_virtualenv=is_venv,
            venv_path=venv_path,
            installed_packages_count=len(installed_pkgs),
            missing_packages=missing_pkgs,
            conflicts=conflicts,
            env_vars_checked=env_vars,
            system_tools=system_tools,
            recommendations=recs,
        )

    def _get_installed_packages(self) -> Dict[str, str]:
        """Fetch installed packages and versions via pip."""
        try:
            res = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if res.returncode == 0:
                import json
                data = json.loads(res.stdout)
                return {item["name"].lower().replace("-", "_"): item["version"] for item in data}
        except Exception:
            pass
        return {}

    def _check_requirements(self, installed: Dict[str, str]) -> Tuple[List[str], List[str]]:
        req_file = self.root / "requirements.txt"
        if not req_file.exists():
            return [], []

        missing: List[str] = []
        conflicts: List[str] = []

        try:
            lines = req_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Simple specifier parsing
                import re
                parts = re.split(r'([=<>!~]+)', line)
                pkg_name = parts[0].strip().lower().replace("-", "_")

                if pkg_name not in installed:
                    # Check common aliases
                    alias_map = {"pillow": "pil", "pyyaml": "yaml", "opencv_python": "cv2"}
                    if alias_map.get(pkg_name, pkg_name) not in installed:
                        missing.append(line)
        except Exception:
            pass

        return missing, conflicts

    def _check_env_vars(self) -> List[Dict[str, Any]]:
        expected_keys = ["PATH", "TEMP", "USERNAME", "USERPROFILE", "ALEX_WORKSPACE", "GEMINI_API_KEY"]
        checked = []
        for k in expected_keys:
            val = os.environ.get(k)
            # Mask secret if key name implies sensitive
            is_secret = "KEY" in k or "SECRET" in k or "PASSWORD" in k or "TOKEN" in k
            masked = "***REDACTED***" if (val and is_secret) else (val[:30] + "..." if val and len(val) > 30 else val)
            checked.append({
                "key": k,
                "is_set": val is not None,
                "masked_value": masked if val else "NOT_SET",
            })
        return checked

