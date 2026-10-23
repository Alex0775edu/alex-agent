"""
dev_lab/bug_discovery.py — Structured Bug Discovery & Static/Dynamic Defect Auditing.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import ast
import json
import os
import py_compile
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from dev_lab.models import BugCategory, BugSeverity, BugStatus, Finding


class BugDiscoveryEngine:
    """Discovers bugs, syntax errors, import failures, async blocking calls,

    resource leaks, and argument count mismatches in a project.
    """

    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()
        self._ignore_dirs = {
            ".git", "__pycache__", ".venv", "venv", "env", "node_modules",
            ".pytest_cache", ".mypy_cache", "dist", "build", ".alex_checkpoints"
        }

    def scan_all(self) -> List[Finding]:
        """Perform comprehensive bug scan across the project."""
        findings: List[Finding] = []
        py_files = self._get_python_files()

        # 1. Syntax & Compilation Audit
        findings.extend(self._scan_syntax_errors(py_files))

        # 2. Import & Module Resolution Audit
        findings.extend(self._scan_import_errors(py_files))

        # 3. Argument Count Mismatches
        findings.extend(self._scan_argument_mismatches(py_files))

        # 4. Async & Threading Issues (e.g. time.sleep in async def)
        findings.extend(self._scan_async_threading_issues(py_files))

        # 5. Resource Leaks (unclosed open())
        findings.extend(self._scan_resource_leaks(py_files))

        # 6. Missing Referenced Local Files
        findings.extend(self._scan_missing_files(py_files))

        # 7. Invalid Configuration Files (JSON/YAML)
        findings.extend(self._scan_invalid_configurations())

        # 8. Infinite Loops Without Delay or Exit Condition
        findings.extend(self._scan_infinite_loops(py_files))

        # 9. SQL Injection Risks
        findings.extend(self._scan_sql_injection_risks(py_files))

        return findings

    def _get_python_files(self) -> List[Path]:
        files: List[Path] = []
        for root, dirs, filenames in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in self._ignore_dirs]
            for f in filenames:
                if f.endswith(".py"):
                    files.append(Path(root) / f)
        return files

    def _scan_syntax_errors(self, py_files: List[Path]) -> List[Finding]:
        findings: List[Finding] = []
        for p in py_files:
            rel = str(p.relative_to(self.root)).replace("\\", "/")
            try:
                py_compile.compile(str(p), doraise=True)
            except py_compile.PyCompileError as e:
                # Extract line number and message
                msg = str(e)
                line = 1
                line_m = re.search(r'line\s+(\d+)', msg, re.IGNORECASE)
                if line_m:
                    line = int(line_m.group(1))

                findings.append(Finding(
                    id=f"BUG-SYNTAX-{p.stem}-{line}",
                    file_path=rel,
                    line_number=line,
                    category=BugCategory.SYNTAX,
                    severity=BugSeverity.CRITICAL,
                    status=BugStatus.CONFIRMED,
                    title=f"Syntax Error in {p.name}",
                    description=f"Python code failed bytecode compilation: {msg}",
                    evidence=msg,
                    is_confirmed=True,
                    suggested_fix="Fix the syntax error according to Python grammar.",
                ))
            except Exception as e:
                findings.append(Finding(
                    id=f"BUG-SYNTAX-{p.stem}-1",
                    file_path=rel,
                    line_number=1,
                    category=BugCategory.SYNTAX,
                    severity=BugSeverity.CRITICAL,
                    status=BugStatus.CONFIRMED,
                    title=f"Compilation Failure in {p.name}",
                    description=str(e),
                    evidence=str(e),
                    is_confirmed=True,
                ))
        return findings

    def _scan_import_errors(self, py_files: List[Path]) -> List[Finding]:
        findings: List[Finding] = []
        # Map internal package paths
        known_modules: Set[str] = set()
        for p in py_files:
            rel = p.relative_to(self.root)
            parts = rel.with_suffix("").parts
            known_modules.add(".".join(parts))
            known_modules.add(p.stem)

        for p in py_files:
            rel = str(p.relative_to(self.root)).replace("\\", "/")
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue  # already caught by syntax scan

            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    # Check relative import without dots or valid target
                    if node.module and node.level == 0:
                        # If importing from a local module that doesn't exist
                        base_mod = node.module.split(".")[0]
                        # If it looks like a local folder/file import that is missing
                        local_target_dir = self.root / base_mod
                        local_target_file = self.root / f"{base_mod}.py"
                        if not local_target_dir.exists() and not local_target_file.exists():
                            # Check if it's an external library or stdlib
                            if not self._is_known_package(base_mod):
                                findings.append(Finding(
                                    id=f"BUG-IMPORT-{p.stem}-{node.lineno}",
                                    file_path=rel,
                                    line_number=node.lineno,
                                    category=BugCategory.IMPORT,
                                    severity=BugSeverity.HIGH,
                                    status=BugStatus.CONFIRMED,
                                    title=f"Missing Module Import: {node.module}",
                                    description=f"File imports '{node.module}' which is neither in stdlib, project root, nor installed packages.",
                                    evidence=f"from {node.module} import ... on line {node.lineno}",
                                    is_confirmed=True,
                                    suggested_fix=f"Install package '{base_mod}' or correct the import path.",
                                ))
        return findings

    def _is_known_package(self, pkg_name: str) -> bool:
        stdlib_mods = {
            "os", "sys", "time", "json", "math", "re", "pathlib", "ast", "subprocess", "socket",
            "typing", "collections", "itertools", "functools", "shutil", "tempfile", "hashlib",
            "base64", "datetime", "uuid", "sqlite3", "threading", "queue", "asyncio", "logging",
            "unittest", "dataclasses", "enum", "inspect", "difflib", "traceback", "copy",
            "string", "io", "contextlib", "abc", "typing_extensions", "ctypes", "platform",
            "py_compile", "importlib"
        }
        if pkg_name in stdlib_mods or pkg_name.startswith("_"):
            return True
        try:
            import importlib.util
            spec = importlib.util.find_spec(pkg_name)
            return spec is not None
        except Exception:
            return False

    def _scan_argument_mismatches(self, py_files: List[Path]) -> List[Finding]:
        findings: List[Finding] = []
        function_sigs: Dict[str, Tuple[int, int, str]] = {}  # name -> (min_args, max_args, rel_path)

        for p in py_files:
            rel = str(p.relative_to(self.root)).replace("\\", "/")
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = node.args
                    total_pos = len(args.args)
                    defaults_count = len(args.defaults)
                    min_args = total_pos - defaults_count
                    max_args = total_pos if not args.vararg else 999
                    # Ignore 'self' or 'cls' adjustment if method
                    if args.args and args.args[0].arg in ("self", "cls"):
                        min_args = max(0, min_args - 1)
                        if max_args != 999:
                            max_args = max(0, max_args - 1)
                    function_sigs[node.name] = (min_args, max_args, rel)

        # Now check calls
        for p in py_files:
            rel = str(p.relative_to(self.root)).replace("\\", "/")
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    fn_name = node.func.id
                    if fn_name in function_sigs:
                        min_a, max_a, def_path = function_sigs[fn_name]
                        provided_args = len(node.args) + len(node.keywords)
                        if provided_args < min_a or provided_args > max_a:
                            findings.append(Finding(
                                id=f"BUG-ARG-{p.stem}-{node.lineno}",
                                file_path=rel,
                                line_number=node.lineno,
                                category=BugCategory.ARGUMENT_MISMATCH,
                                severity=BugSeverity.HIGH,
                                status=BugStatus.CONFIRMED,
                                title=f"Incorrect Argument Count for '{fn_name}'",
                                description=f"Function '{fn_name}' defined in {def_path} expects {min_a}-{max_a} args, but received {provided_args} args.",
                                evidence=f"Call: {fn_name}(...) on line {node.lineno}",
                                is_confirmed=True,
                                suggested_fix=f"Adjust arguments to match function signature of '{fn_name}'.",
                            ))
        return findings

    def _scan_async_threading_issues(self, py_files: List[Path]) -> List[Finding]:
        findings: List[Finding] = []
        for p in py_files:
            rel = str(p.relative_to(self.root)).replace("\\", "/")
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.AsyncFunctionDef):
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Call):
                            # Check time.sleep() inside async function
                            if (
                                isinstance(sub.func, ast.Attribute) and
                                isinstance(sub.func.value, ast.Name) and
                                sub.func.value.id == "time" and
                                sub.func.attr == "sleep"
                            ):
                                findings.append(Finding(
                                    id=f"BUG-ASYNC-BLOCK-{p.stem}-{sub.lineno}",
                                    file_path=rel,
                                    line_number=sub.lineno,
                                    category=BugCategory.THREADING_ASYNC,
                                    severity=BugSeverity.HIGH,
                                    status=BugStatus.CONFIRMED,
                                    title="Blocking time.sleep() in async function",
                                    description=f"Function '{node.name}' is an async coroutine but calls synchronous blocking time.sleep(). This freezes the entire event loop.",
                                    evidence=f"time.sleep() on line {sub.lineno} in async def {node.name}",
                                    is_confirmed=True,
                                    suggested_fix="Replace 'time.sleep(...)' with 'await asyncio.sleep(...)'.",
                                ))
        return findings

    def _scan_resource_leaks(self, py_files: List[Path]) -> List[Finding]:
        findings: List[Finding] = []
        for p in py_files:
            rel = str(p.relative_to(self.root)).replace("\\", "/")
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue

            for node in ast.walk(tree):
                # Check for bare open() not enclosed in a with statement
                if isinstance(node, ast.Assign):
                    if isinstance(node.value, ast.Call):
                        if isinstance(node.value.func, ast.Name) and node.value.func.id == "open":
                            findings.append(Finding(
                                id=f"BUG-RESOURCE-{p.stem}-{node.lineno}",
                                file_path=rel,
                                line_number=node.lineno,
                                category=BugCategory.RESOURCE_LEAK,
                                severity=BugSeverity.MEDIUM,
                                status=BugStatus.CONFIRMED,
                                title="Unmanaged File Descriptor open()",
                                description="File handle opened via direct assignment without context manager ('with open(...)'). Risk of file lock and descriptor leak.",
                                evidence=f"open() on line {node.lineno}",
                                is_confirmed=True,
                                suggested_fix="Refactor to use 'with open(...) as f:' pattern.",
                            ))
        return findings

    def _scan_missing_files(self, py_files: List[Path]) -> List[Finding]:
        findings: List[Finding] = []
        for p in py_files:
            rel = str(p.relative_to(self.root)).replace("\\", "/")
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                # Look for open("path", ...) where path is a static relative literal string
                matches = re.finditer(r'open\s*\(\s*["\']([^"\']+\.[a-zA-Z0-9]+)["\']', content)
                for m in matches:
                    ref_path = m.group(1)
                    if not ref_path.startswith(("http", "/")):
                        resolved = self.root / ref_path
                        if not resolved.exists() and not (p.parent / ref_path).exists():
                            line_no = content[:m.start()].count("\n") + 1
                            findings.append(Finding(
                                id=f"BUG-MISSING-FILE-{p.stem}-{line_no}",
                                file_path=rel,
                                line_number=line_no,
                                category=BugCategory.MISSING_FILE,
                                severity=BugSeverity.HIGH,
                                status=BugStatus.CONFIRMED,
                                title=f"Referenced File Does Not Exist: '{ref_path}'",
                                description=f"Code attempts to open file '{ref_path}' which does not exist on disk.",
                                evidence=f"open('{ref_path}') at line {line_no}",
                                is_confirmed=True,
                                suggested_fix=f"Create file '{ref_path}' or check file existence before opening.",
                            ))
            except Exception:
                pass
        return findings

    def _scan_invalid_configurations(self) -> List[Finding]:
        findings: List[Finding] = []
        for root, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in self._ignore_dirs]
            for f in files:
                p = Path(root) / f
                rel = str(p.relative_to(self.root)).replace("\\", "/")
                if f.endswith(".json"):
                    try:
                        json.loads(p.read_text(encoding="utf-8"))
                    except json.JSONDecodeError as e:
                        findings.append(Finding(
                            id=f"BUG-CONFIG-{p.stem}-{e.lineno}",
                            file_path=rel,
                            line_number=e.lineno,
                            category=BugCategory.INVALID_CONFIG,
                            severity=BugSeverity.HIGH,
                            status=BugStatus.CONFIRMED,
                            title=f"Invalid JSON Configuration: {p.name}",
                            description=f"JSON parsing error at line {e.lineno}, column {e.colno}: {e.msg}",
                            evidence=str(e),
                            is_confirmed=True,
                            suggested_fix="Fix JSON syntax (trailing commas, quotes, brackets).",
                        ))
        return findings

    def _scan_infinite_loops(self, py_files: List[Path]) -> List[Finding]:
        findings: List[Finding] = []
        for p in py_files:
            rel = str(p.relative_to(self.root)).replace("\\", "/")
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.While):
                    # Check while True: without break, return, or sleep
                    is_true_cond = (
                        (isinstance(node.test, ast.Constant) and node.test.value is True) or
                        (isinstance(node.test, ast.NameConstant) and node.test.value is True) or
                        (isinstance(node.test, ast.Constant) and node.test.value == 1)
                    )
                    if is_true_cond:
                        has_exit_or_delay = False
                        for sub in ast.walk(node):
                            if isinstance(sub, (ast.Break, ast.Return, ast.Raise)):
                                has_exit_or_delay = True
                                break
                            if isinstance(sub, ast.Call):
                                if isinstance(sub.func, ast.Attribute) and sub.func.attr == "sleep":
                                    has_exit_or_delay = True
                                    break
                        if not has_exit_or_delay:
                            findings.append(Finding(
                                id=f"BUG-LOOP-{p.stem}-{node.lineno}",
                                file_path=rel,
                                line_number=node.lineno,
                                category=BugCategory.RUNTIME,
                                severity=BugSeverity.CRITICAL,
                                status=BugStatus.CONFIRMED,
                                title="Tight Infinite Loop (100% CPU lock risk)",
                                description="while True loop found without break, return, or sleep calls. Causes complete CPU lockup.",
                                evidence=f"while True: at line {node.lineno}",
                                is_confirmed=True,
                                suggested_fix="Add break condition, exit logic, or sleep throttling to the loop.",
                            ))
        return findings

    def _scan_sql_injection_risks(self, py_files: List[Path]) -> List[Finding]:
        findings: List[Finding] = []
        for p in py_files:
            rel = str(p.relative_to(self.root)).replace("\\", "/")
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute) and node.func.attr in ("execute", "executemany"):
                        if node.args and isinstance(node.args[0], ast.JoinedStr):  # f-string in SQL query
                            findings.append(Finding(
                                id=f"BUG-SQLI-{p.stem}-{node.lineno}",
                                file_path=rel,
                                line_number=node.lineno,
                                category=BugCategory.SECURITY,
                                severity=BugSeverity.CRITICAL,
                                status=BugStatus.CONFIRMED,
                                title="SQL Injection via f-string query formatting",
                                description="SQL query constructed via interpolated f-string directly into execute(). Subject to SQL injection.",
                                evidence=f"execute(f'...') at line {node.lineno}",
                                is_confirmed=True,
                                requires_approval=True,
                                suggested_fix="Use parameterized queries (e.g. execute('SELECT ... WHERE id = ?', (val,))).",
                            ))
        return findings

