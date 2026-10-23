"""
dev_lab/repo_intelligence.py — Deep Repository Intelligence, Static Analysis & Dependency Mapping.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from dev_lab.models import ArchitectureSummary


class RepoIntelligence:
    """Performs static analysis, dependency mapping, circular import detection,

    dead code identification, and security risk auditing on a codebase.
    """

    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()
        self.project_name = self.root.name
        self._ignore_dirs = {
            ".git", "__pycache__", ".venv", "venv", "env", "node_modules",
            ".pytest_cache", ".mypy_cache", "dist", "build", ".alex_checkpoints"
        }

    def analyze(self) -> ArchitectureSummary:
        """Run complete repository inspection and return structured summary."""
        py_files = self._get_python_files()
        primary_lang, frameworks = self._detect_languages_and_frameworks()
        entry_points = self._detect_entry_points(py_files)
        
        internal_modules, import_graph, external_deps = self._build_import_graph(py_files)
        circular_imports = self._find_circular_imports(import_graph)
        
        dead_code = self._detect_dead_code(py_files, entry_points, internal_modules)
        duplicate_blocks = self._detect_duplicate_logic(py_files)
        todos_and_fixmes = self._scan_todos_and_fixmes()
        unused_deps = self._detect_unused_dependencies(external_deps)
        missing_tests = self._detect_missing_tests(py_files)
        error_risks = self._audit_error_handling(py_files)
        sec_risks = self._audit_security_risks()

        return ArchitectureSummary(
            project_name=self.project_name,
            project_path=str(self.root),
            primary_language=primary_lang,
            frameworks=frameworks,
            entry_points=entry_points,
            modules_count=len(py_files),
            dependencies_count=len(external_deps),
            external_dependencies=sorted(list(external_deps)),
            unused_dependencies=unused_deps,
            circular_imports=circular_imports,
            dead_code_items=dead_code,
            duplicate_logic_items=duplicate_blocks,
            todos_and_fixmes=todos_and_fixmes,
            missing_tests=missing_tests,
            error_handling_risks=error_risks,
            security_risks=sec_risks,
        )

    def _get_python_files(self) -> List[Path]:
        files: List[Path] = []
        for root, dirs, filenames in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in self._ignore_dirs]
            for f in filenames:
                if f.endswith(".py"):
                    files.append(Path(root) / f)
        return files

    def _detect_languages_and_frameworks(self) -> Tuple[str, List[str]]:
        ext_counts: Dict[str, int] = {}
        frameworks: Set[str] = set()

        for root, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in self._ignore_dirs]
            for f in files:
                ext = Path(f).suffix.lower()
                if ext:
                    ext_counts[ext] = ext_counts.get(ext, 0) + 1

        primary_lang = "Python"
        if ext_counts.get(".js", 0) + ext_counts.get(".ts", 0) > ext_counts.get(".py", 0):
            primary_lang = "JavaScript/TypeScript"
        elif ext_counts.get(".php", 0) > ext_counts.get(".py", 0):
            primary_lang = "PHP"

        # Check framework markers
        for req_file in [self.root / "requirements.txt", self.root / "pyproject.toml"]:
            if req_file.exists():
                text = req_file.read_text(encoding="utf-8", errors="ignore").lower()
                if "fastapi" in text:
                    frameworks.add("FastAPI")
                if "flask" in text:
                    frameworks.add("Flask")
                if "django" in text:
                    frameworks.add("Django")
                if "pytest" in text:
                    frameworks.add("pytest")
                if "torch" in text or "pytorch" in text:
                    frameworks.add("PyTorch")
                if "pyqt6" in text or "pyqt5" in text:
                    frameworks.add("PyQt")

        pkg_json = self.root / "package.json"
        if pkg_json.exists():
            text = pkg_json.read_text(encoding="utf-8", errors="ignore").lower()
            if "react" in text:
                frameworks.add("React")
            if "express" in text:
                frameworks.add("Express")
            if "vue" in text:
                frameworks.add("Vue")
            if "next" in text:
                frameworks.add("Next.js")

        return primary_lang, sorted(list(frameworks))

    def _detect_entry_points(self, py_files: List[Path]) -> List[str]:
        entry_points = []
        common_entry_names = {"main.py", "app.py", "server.py", "run.py", "manage.py", "wsgi.py", "asgi.py"}

        for p in py_files:
            rel = str(p.relative_to(self.root)).replace("\\", "/")
            if p.name in common_entry_names:
                entry_points.append(rel)
                continue
            # Look for if __name__ == '__main__':
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                if '__name__' in content and '__main__' in content:
                    if rel not in entry_points:
                        entry_points.append(rel)
            except Exception:
                pass

        return entry_points

    def _build_import_graph(self, py_files: List[Path]) -> Tuple[Dict[str, Path], Dict[str, Set[str]], Set[str]]:
        internal_modules: Dict[str, Path] = {}
        for p in py_files:
            rel = p.relative_to(self.root)
            mod_name = str(rel.with_suffix("")).replace("\\", ".").replace("/", ".")
            internal_modules[mod_name] = p
            # Also store short name
            internal_modules[p.stem] = p

        import_graph: Dict[str, Set[str]] = {str(p.relative_to(self.root)).replace("\\", "/"): set() for p in py_files}
        external_deps: Set[str] = set()

        stdlib_mods = {
            "os", "sys", "time", "json", "math", "re", "pathlib", "ast", "subprocess", "socket",
            "typing", "collections", "itertools", "functools", "shutil", "tempfile", "hashlib",
            "base64", "datetime", "uuid", "sqlite3", "threading", "queue", "asyncio", "logging",
            "unittest", "dataclasses", "enum", "inspect", "difflib", "traceback"
        }

        for p in py_files:
            rel_str = str(p.relative_to(self.root)).replace("\\", "/")
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            base_pkg = alias.name.split(".")[0]
                            if base_pkg in internal_modules:
                                target_path = str(internal_modules[base_pkg].relative_to(self.root)).replace("\\", "/")
                                if target_path != rel_str:
                                    import_graph[rel_str].add(target_path)
                            elif base_pkg not in stdlib_mods and not base_pkg.startswith("_"):
                                external_deps.add(base_pkg)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            base_pkg = node.module.split(".")[0]
                            if base_pkg in internal_modules:
                                target_path = str(internal_modules[base_pkg].relative_to(self.root)).replace("\\", "/")
                                if target_path != rel_str:
                                    import_graph[rel_str].add(target_path)
                            elif base_pkg not in stdlib_mods and not base_pkg.startswith("_"):
                                external_deps.add(base_pkg)
            except Exception:
                pass

        return internal_modules, import_graph, external_deps

    def _find_circular_imports(self, graph: Dict[str, Set[str]]) -> List[List[str]]:
        cycles: List[List[str]] = []
        visited: Dict[str, int] = {}  # 0=unvisited, 1=visiting, 2=visited
        path: List[str] = []

        def dfs(node: str):
            visited[node] = 1
            path.append(node)
            for neighbor in graph.get(node, []):
                if visited.get(neighbor, 0) == 1:
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    if len(cycle) > 2 and cycle not in cycles:
                        cycles.append(cycle)
                elif visited.get(neighbor, 0) == 0:
                    dfs(neighbor)
            path.pop()
            visited[node] = 2

        for node in graph:
            if visited.get(node, 0) == 0:
                dfs(node)

        return cycles

    def _detect_dead_code(
        self, py_files: List[Path], entry_points: List[str], internal_modules: Dict[str, Path]
    ) -> List[Dict[str, Any]]:
        dead_items: List[Dict[str, Any]] = []

        for p in py_files:
            rel_str = str(p.relative_to(self.root)).replace("\\", "/")
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue

            # 1. Unreachable statements after return, raise, break, continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.For, ast.While, ast.If)):
                    body = getattr(node, "body", [])
                    has_terminal = False
                    for idx, stmt in enumerate(body):
                        if has_terminal:
                            dead_items.append({
                                "file": rel_str,
                                "line": getattr(stmt, "lineno", 0),
                                "type": "unreachable_statement",
                                "detail": f"Unreachable statement after return/raise/break: {type(stmt).__name__}",
                            })
                        elif isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                            has_terminal = True

            # 2. Unreferenced private/internal functions in non-entry files
            if rel_str not in entry_points and not p.name.startswith("test_"):
                defined_funcs: Dict[str, int] = {}
                called_funcs: Set[str] = set()

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if node.name.startswith("_") and not node.name.startswith("__"):
                            defined_funcs[node.name] = node.lineno
                    elif isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Name):
                            called_funcs.add(node.func.id)
                        elif isinstance(node.func, ast.Attribute):
                            called_funcs.add(node.func.attr)

                for f_name, line in defined_funcs.items():
                    if f_name not in called_funcs:
                        dead_items.append({
                            "file": rel_str,
                            "line": line,
                            "type": "unused_private_function",
                            "detail": f"Internal function '{f_name}' is defined but never called within file",
                        })

        return dead_items

    def _detect_duplicate_logic(self, py_files: List[Path]) -> List[Dict[str, Any]]:
        """Detect near-duplicate function blocks across the codebase."""
        duplicates: List[Dict[str, Any]] = []
        body_hashes: Dict[str, List[Tuple[str, str, int]]] = {}

        for p in py_files:
            rel_str = str(p.relative_to(self.root)).replace("\\", "/")
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if len(node.body) >= 5:  # significant functions only
                        try:
                            # Normalize variable names to generic tokens for structural comparison
                            body_dump = ast.dump(node)
                            h = hashlib.sha256(body_dump.encode("utf-8")).hexdigest()[:16]
                            if h not in body_hashes:
                                body_hashes[h] = []
                            body_hashes[h].append((rel_str, node.name, node.lineno))
                        except Exception:
                            pass

        for h, instances in body_hashes.items():
            if len(instances) > 1:
                duplicates.append({
                    "hash": h,
                    "instances": [{"file": f, "function": fn, "line": ln} for f, fn, ln in instances],
                    "message": f"Identical AST logic duplicated in {len(instances)} locations"
                })

        return duplicates

    def _scan_todos_and_fixmes(self) -> List[Dict[str, Any]]:
        findings = []
        pattern = re.compile(r"#\s*(TODO|FIXME|XXX|BUG)\s*[:\-]?\s*(.*)", re.IGNORECASE)

        for root, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in self._ignore_dirs]
            for f in files:
                if f.endswith((".py", ".js", ".ts", ".html", ".css", ".md")):
                    p = Path(root) / f
                    rel_str = str(p.relative_to(self.root)).replace("\\", "/")
                    try:
                        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
                        for idx, line in enumerate(lines):
                            m = pattern.search(line)
                            if m:
                                findings.append({
                                    "file": rel_str,
                                    "line": idx + 1,
                                    "tag": m.group(1).upper(),
                                    "comment": m.group(2).strip(),
                                })
                    except Exception:
                        pass
        return findings

    def _detect_unused_dependencies(self, external_deps: Set[str]) -> List[str]:
        req_file = self.root / "requirements.txt"
        if not req_file.exists():
            return []

        unused: List[str] = []
        try:
            lines = req_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                pkg = re.split(r"[=<>!~]", line)[0].strip().lower().replace("-", "_")
                # Normalize common package name differences
                pkg_alias_map = {
                    "pillow": "pil",
                    "pyyaml": "yaml",
                    "beautifulsoup4": "bs4",
                    "opencv_python": "cv2",
                }
                actual_name = pkg_alias_map.get(pkg, pkg)
                
                matched = any(
                    dep.lower().replace("-", "_") == actual_name or
                    dep.lower().replace("-", "_") == pkg
                    for dep in external_deps
                )
                if not matched and pkg not in {"pytest", "flake8", "black", "mypy", "wheel", "setuptools"}:
                    unused.append(line)
        except Exception:
            pass

        return unused

    def _detect_missing_tests(self, py_files: List[Path]) -> List[str]:
        missing: List[str] = []
        test_file_names = {p.name for p in py_files if p.name.startswith("test_")}

        for p in py_files:
            if p.name.startswith("test_") or p.name == "__init__.py" or p.name in {"setup.py", "conftest.py"}:
                continue
            expected_test_name = f"test_{p.name}"
            if expected_test_name not in test_file_names:
                rel = str(p.relative_to(self.root)).replace("\\", "/")
                missing.append(rel)

        return missing

    def _audit_error_handling(self, py_files: List[Path]) -> List[Dict[str, Any]]:
        risks = []
        for p in py_files:
            rel = str(p.relative_to(self.root)).replace("\\", "/")
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    # 1. Bare except:
                    if node.type is None:
                        risks.append({
                            "file": rel,
                            "line": node.lineno,
                            "type": "bare_except",
                            "severity": "HIGH",
                            "detail": "Bare 'except:' catches SystemExit and KeyboardInterrupt. Use 'except Exception:' instead."
                        })
                    # 2. except Exception: pass (silent swallow)
                    elif len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                        risks.append({
                            "file": rel,
                            "line": node.lineno,
                            "type": "swallowed_exception",
                            "severity": "MEDIUM",
                            "detail": "Exception silently swallowed with 'pass'. Log error or handle appropriately."
                        })
        return risks

    def _audit_security_risks(self) -> List[Dict[str, Any]]:
        risks = []
        patterns = [
            (re.compile(r'eval\s*\('), "eval_usage", "CRITICAL", "Usage of eval() detected which may lead to code injection"),
            (re.compile(r'exec\s*\('), "exec_usage", "CRITICAL", "Usage of exec() detected which may execute arbitrary strings"),
            (re.compile(r'subprocess\..*shell\s*=\s*True'), "shell_true", "HIGH", "subprocess with shell=True creates command injection risks"),
            (re.compile(r'(?:api_key|secret|password|token)\s*=\s*["\'][a-zA-Z0-9_\-]{16,}["\']', re.IGNORECASE), "hardcoded_secret", "HIGH", "Potentially hardcoded secret or credential token detected"),
        ]

        for root, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in self._ignore_dirs]
            for f in files:
                if f.endswith((".py", ".json", ".js", ".ts")):
                    p = Path(root) / f
                    rel = str(p.relative_to(self.root)).replace("\\", "/")
                    try:
                        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
                        for idx, line in enumerate(lines):
                            for regex, p_type, sev, desc in patterns:
                                if regex.search(line):
                                    risks.append({
                                        "file": rel,
                                        "line": idx + 1,
                                        "type": p_type,
                                        "severity": sev,
                                        "detail": desc,
                                    })
                    except Exception:
                        pass
        return risks

    def generate_report_markdown(self, summary: ArchitectureSummary) -> str:
        """Generate comprehensive clean markdown architecture report."""
        lines = [
            f"# REPOSITORY ARCHITECTURE & INTELLIGENCE REPORT: {summary.project_name}",
            f"**Path:** `{summary.project_path}`",
            f"**Primary Language:** {summary.primary_language}",
            f"**Frameworks Detected:** {', '.join(summary.frameworks) if summary.frameworks else 'None'}",
            f"**Entry Points ({len(summary.entry_points)}):** {', '.join(summary.entry_points) if summary.entry_points else 'None'}",
            "",
            "## 1. Modules & Dependency Metrics",
            f"- **Total Source Modules:** {summary.modules_count}",
            f"- **External Dependencies Detected:** {summary.dependencies_count}",
            f"- **Unused Dependencies in Config:** {len(summary.unused_dependencies)}",
            f"- **Circular Import Cycles:** {len(summary.circular_imports)}",
            "",
        ]

        if summary.circular_imports:
            lines.append("### Circular Import Warning:")
            for cycle in summary.circular_imports:
                lines.append(f"- `{' -> '.join(cycle)}`")
            lines.append("")

        lines.extend([
            "## 2. Code Quality & Maintenance Metrics",
            f"- **Dead / Unreachable Code Items:** {len(summary.dead_code_items)}",
            f"- **Duplicate Logic Blocks:** {len(summary.duplicate_logic_items)}",
            f"- **Pending TODOs / FIXMEs:** {len(summary.todos_and_fixmes)}",
            f"- **Modules Missing Unit Tests:** {len(summary.missing_tests)}",
            f"- **Error Handling Defects:** {len(summary.error_handling_risks)}",
            f"- **Security & Vulnerability Risks:** {len(summary.security_risks)}",
            "",
        ])

        if summary.security_risks:
            lines.append("### Security & Risk Findings:")
            for s in summary.security_risks[:5]:
                lines.append(f"- **[{s['severity']}]** `{s['file']}:{s['line']}` — {s['detail']}")
            if len(summary.security_risks) > 5:
                lines.append(f"  *(and {len(summary.security_risks) - 5} more)*")
            lines.append("")

        return "\n".join(lines)

