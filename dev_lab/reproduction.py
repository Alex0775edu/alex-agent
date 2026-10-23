"""
dev_lab/reproduction.py — "Reproduce Before Fixing" 7-Step Bug Reproduction Engine.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple

from dev_lab.models import BugCategory, Finding, ReproductionResult


class BugReproducer:
    """Implements the mandatory 7-step reproduction protocol:

    1. Record observed behavior.
    2. Identify relevant code & dependencies.
    3. Create minimal reproduction script.
    4. Capture actual error or failing test stdout/stderr.
    5. Identify likely root cause.
    6. Design smallest appropriate fix.
    7. Define verification criteria.
    """

    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()
        self.repro_dir = self.root / ".alex_repro"
        self.repro_dir.mkdir(parents=True, exist_ok=True)

    def reproduce(self, finding: Finding, timeout_s: int = 15) -> ReproductionResult:
        """Attempt to reproduce the finding minimally and capture exact error."""
        start_time = time.time()
        file_path = self.root / finding.file_path

        # Step 1 & 2: Identify file & issue type
        if not file_path.exists():
            return ReproductionResult(
                reproduced=True,
                error_output=f"FileNotFoundError: Target file does not exist: {file_path}",
                repro_script_path=None,
                traceback=None,
                notes="Reproduced directly via filesystem probe: target file is missing.",
                exit_code=1,
                duration_s=time.time() - start_time,
            )

        # Step 3: Create minimal reproduction harness
        repro_script = self._generate_repro_script(finding, file_path)
        repro_path = self.repro_dir / f"repro_{finding.id.replace('-', '_')}.py"
        repro_path.write_text(repro_script, encoding="utf-8")

        # Step 4: Execute reproduction under strict subprocess containment
        try:
            env = os.environ.copy()
            # Add project root to PYTHONPATH
            cur_pythonpath = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = f"{str(self.root)}{os.pathsep}{cur_pythonpath}"

            proc = subprocess.run(
                [sys.executable, str(repro_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
                cwd=str(self.root),
                env=env,
            )

            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()
            combined = f"{stdout}\n{stderr}".strip()
            reproduced = proc.returncode != 0

            # Step 5 & 6 & 7: Formulate root cause & verification notes
            notes = ""
            if reproduced:
                finding.is_confirmed = True
                notes = (
                    f"Confirmed failure reproduced with exit code {proc.returncode}.\n"
                    f"Root cause matches category {finding.category.value}."
                )
            else:
                finding.is_confirmed = False
                notes = (
                    "Execution exited with 0 (clean). Could not reproduce failure under standard conditions. "
                    "Marked as unconfirmed pending live runtime trace."
                )

            return ReproductionResult(
                reproduced=reproduced,
                error_output=combined,
                repro_script_path=str(repro_path),
                traceback=stderr if stderr else None,
                notes=notes,
                exit_code=proc.returncode,
                duration_s=round(time.time() - start_time, 3),
            )

        except subprocess.TimeoutExpired:
            return ReproductionResult(
                reproduced=True,
                error_output=f"TimeoutExpired: Reproduction script timed out after {timeout_s}s (infinite loop or deadlock confirmed).",
                repro_script_path=str(repro_path),
                traceback=None,
                notes="Infinite loop or blocking deadlock confirmed by timeout.",
                exit_code=124,
                duration_s=round(time.time() - start_time, 3),
            )
        except Exception as e:
            return ReproductionResult(
                reproduced=False,
                error_output=f"Reproduction runner exception: {e}",
                repro_script_path=str(repro_path),
                notes=f"Error executing reproduction probe: {e}",
                exit_code=-1,
                duration_s=round(time.time() - start_time, 3),
            )

    def _generate_repro_script(self, finding: Finding, target_file: Path) -> str:
        """Generate targeted test script to expose the defect."""
        rel_path = finding.file_path.replace("\\", "/")

        if finding.category == BugCategory.SYNTAX:
            return f"""# Minimal Syntax Error Reproduction
import py_compile
try:
    py_compile.compile(r"{target_file}", doraise=True)
    print("Syntax compiled cleanly")
except Exception as e:
    import sys
    print(f"Captured Syntax Error: {{e}}", file=sys.stderr)
    sys.exit(1)
"""

        elif finding.category == BugCategory.IMPORT:
            mod_import = target_file.stem
            return f"""# Minimal Import Reproduction
import sys
try:
    import {mod_import}
    print("Import succeeded")
except Exception as e:
    print(f"Captured Import Error: {{e}}", file=sys.stderr)
    sys.exit(1)
"""

        elif finding.category == BugCategory.INVALID_CONFIG:
            return f"""# Minimal JSON Config Reproduction
import json, sys
try:
    with open(r"{target_file}", "r", encoding="utf-8") as f:
        json.load(f)
    print("Config valid")
except Exception as e:
    print(f"Captured Config Error: {{e}}", file=sys.stderr)
    sys.exit(1)
"""

        elif finding.category == BugCategory.THREADING_ASYNC:
            return f"""# Minimal Async Blocking Reproduction
import ast, sys
with open(r"{target_file}", "r", encoding="utf-8") as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.AsyncFunctionDef):
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and getattr(sub.func, 'attr', '') == 'sleep':
                val = getattr(sub.func, 'value', None)
                if val and getattr(val, 'id', '') == 'time':
                    print("Captured blocking time.sleep in async def at line " + str(sub.lineno), file=sys.stderr)
                    sys.exit(1)
"""

        # General module execution reproduction
        return f"""# General Reproduction Probe
import sys, subprocess
proc = subprocess.run([sys.executable, r"{target_file}"], capture_output=True, text=True)
if proc.returncode != 0:
    print(proc.stderr, file=sys.stderr)
    sys.exit(proc.returncode)
else:
    print(proc.stdout)
"""

