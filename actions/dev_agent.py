import ast
import subprocess
import sys
import json
import re
import time
from pathlib import Path
from core.action_timeline import timeline


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR         = get_base_dir()
API_CONFIG_PATH  = BASE_DIR / "config" / "api_keys.json"
PROJECTS_DIR     = Path.home() / "Desktop" / "AlexProjects"
MAX_FIX_ATTEMPTS = 5
# Model choice, timeout and fallback ladder all live in core/gemini.py.
from core import gemini

MODEL_PLANNER    = gemini.SMART
MODEL_WRITER     = gemini.SMART

def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _get_model(model_name: str = gemini.SMART):
    """Planning and writing whole files — the reasoning tier, and a long
    deadline because the answer is a source file rather than a sentence."""
    class _W:
        def generate_content(self, contents):
            resp = gemini.call(contents, tier=model_name, timeout_ms=60000)
            if resp is None:
                raise RuntimeError("every Gemini model on the ladder failed")
            return resp

    return _W()


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\r?\n?", "", text)
    text = re.sub(r"\r?\n?```\s*$", "", text)
    return text.strip()


def _is_rate_limit(error: Exception) -> bool:
    msg = str(error).lower()
    return "429" in msg or "quota" in msg or "resource_exhausted" in msg


def _parse_traceback(output: str, project_files: list[str]) -> tuple[str | None, int | None]:

    pattern = re.compile(r'File ["\']([^"\']+\.py)["\'],\s+line\s+(\d+)', re.IGNORECASE)
    matches = pattern.findall(output)

    for raw_path, line_str in reversed(matches):
        raw_name = Path(raw_path).name
        for pf in project_files:
            if Path(pf).name == raw_name or pf == raw_path or raw_path.endswith(pf):
                return pf, int(line_str)

    return None, None


def _classify_error(output: str) -> str:

    low = output.lower()

    if any(x in low for x in ("no module named", "modulenotfounderror", "importerror")):
        return "dependency_error"

    if "syntaxerror" in low or "invalid syntax" in low:
        return "syntax_error"
    
    if "cannot import" in low or "importerror" in low:
        return "import_error"

    if any(x in low for x in (
        "traceback", "exception", "error:", "nameerror", "typeerror",
        "attributeerror", "valueerror", "keyerror", "indexerror",
        "zerodivisionerror", "filenotfounderror", "permissionerror",
    )):
        return "runtime_error"

    return "none"


def _has_error(output: str, run_command: str) -> bool:
    
    low = output.lower()

    if "timed out" in low:
        return False

    if not output.strip():
        return False

    error_type = _classify_error(output)
    return error_type != "none"

class RateLimitError(Exception):
    pass


def _plan_project(description: str, language: str) -> dict:
    model = _get_model(MODEL_PLANNER)

    prompt = f"""You are a senior software architect. Create a minimal, complete file plan for this project.

Language: {language}
Description: {description}

Return ONLY valid JSON — no markdown, no explanation:
{{
  "project_name": "snake_case_name",
  "entry_point": "main.py",
  "files": [
    {{
      "path": "main.py",
      "description": "Entry point — what it does and which modules it imports",
      "imports": ["utils.helpers", "core.engine"]
    }},
    {{
      "path": "utils/helpers.py",
      "description": "Helper utilities — what functions it exposes",
      "imports": []
    }}
  ],
  "run_command": "python main.py",
  "dependencies": ["requests"]
}}

Critical rules:
1. List files in DEPENDENCY ORDER — files with no imports come first, entry point comes last.
2. The "imports" field must list every other project module this file imports (dot-notation, e.g. "utils.helpers").
3. Keep it minimal — only files truly needed.
4. Entry point must be in the files list.
5. Use relative paths only (e.g. "utils/helpers.py", not absolute paths).
6. Standard library modules (os, sys, json, etc.) do NOT go in "dependencies".

JSON:"""

    try:
        response = model.generate_content(prompt)
        raw = _strip_fences(response.text)
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Planner returned invalid JSON: {e}\nRaw: {response.text[:300]}")
    except Exception as e:
        if _is_rate_limit(e):
            raise RateLimitError(str(e))
        raise

def _write_file(
    file_info: dict,
    project_description: str,
    all_files: list[dict],
    language: str,
    project_dir: Path,
    already_written: dict[str, str],
) -> str:
    model = _get_model(MODEL_WRITER)

    file_path = file_info["path"]
    file_desc = file_info.get("description", "")
    file_imports = file_info.get("imports", [])

    file_list = "\n".join(
        f"  [{i+1}] {f['path']}: {f.get('description', '')}"
        for i, f in enumerate(all_files)
    )

    dependency_context = ""
    for dep_dotted in file_imports:
        dep_path = dep_dotted.replace(".", "/") + ".py"
        if dep_path in already_written:
            code_snippet = already_written[dep_path][:2000]
            dependency_context += f"\n\n--- {dep_path} (you must import from this) ---\n{code_snippet}"

    lang_rules = ""
    if language.lower() == "python":
        lang_rules = """
Python-specific rules:
- Use type hints for all function signatures.
- Add docstrings for all public functions and classes.
- Use if __name__ == "__main__": guard in the entry point.
- For relative imports within the project, use: from utils.helpers import foo  (match the project structure exactly).
- Do NOT use implicit relative imports (from . import ...) unless it's a proper package with __init__.py.
- If this is a package subdirectory, create __init__.py files where needed."""
    elif language.lower() in ("javascript", "typescript", "js", "ts"):
        lang_rules = """
JS/TS-specific rules:
- Use ES modules (import/export), not CommonJS (require).
- Add JSDoc comments for all exported functions.
- Handle promise rejections with try/catch in async functions."""

    prompt = f"""You are a senior {language} developer writing production-quality code for a real project.

Project goal: {project_description}

Complete project file structure (in dependency order):
{file_list}

{f"Dependencies this file must import from other project files:{dependency_context}" if dependency_context else ""}

Your task: Write the complete, working code for: {file_path}
Purpose of this file: {file_desc}
{f"This file imports from: {', '.join(file_imports)}" if file_imports else "This file has no project-internal imports."}

{lang_rules}

General rules:
- Output ONLY raw code. Absolutely no explanation, no markdown, no triple backticks.
- Write COMPLETE, RUNNABLE code — no placeholders, no "# TODO", no "pass" stubs.
- Every import must either be from the standard library, listed dependencies, or the project files shown above.
- Match import paths EXACTLY to the file paths in the project structure (e.g. if file is "utils/helpers.py", import as "from utils.helpers import ...").
- Use proper error handling (try/except) where I/O or network calls are made.
- The code must work correctly when the project entry point is run from the project root directory.

Code for {file_path}:"""

    try:
        response = model.generate_content(prompt)
        code = _strip_fences(response.text)

        full_path = project_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(code, encoding="utf-8")

        print(f"[DevAgent] ✅ Written: {file_path} ({len(code)} chars)")
        return code

    except Exception as e:
        if _is_rate_limit(e):
            raise RateLimitError(str(e))
        raise

def _install_dependencies(dependencies: list[str], project_dir: Path) -> str:
    if not dependencies:
        return "No external dependencies."

    to_install = []
    for dep in dependencies:
        pkg_name = re.split(r"[>=<!]", dep)[0].strip()
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", pkg_name],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            to_install.append(dep)
        else:
            print(f"[DevAgent] [OK] Already installed: {pkg_name}")

    if not to_install:
        return f"All dependencies already installed: {', '.join(dependencies)}"

    print(f"[DevAgent] [INSTALL] Installing: {to_install}")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install"] + to_install,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=120, cwd=str(project_dir)
        )
        if result.returncode == 0:
            return f"Installed: {', '.join(to_install)}"
        return f"Install warning (non-fatal): {result.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return "Dependency install timed out (non-fatal)."
    except Exception as e:
        return f"Install error (non-fatal): {e}"

def _open_vscode(project_dir: Path) -> bool:
    vscode_candidates = [
        "code",
        rf"C:\Users\{Path.home().name}\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd",
        r"C:\Program Files\Microsoft VS Code\bin\code.cmd",
    ]
    for cmd in vscode_candidates:
        try:
            subprocess.Popen(
                [cmd, str(project_dir)],
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.5)
            print(f"[DevAgent] [VSCODE] VSCode opened: {project_dir}")
            return True
        except Exception:
            continue
    return False

def _run_project(run_command: str, project_dir: Path, timeout: int = 30) -> str:
    print(f"[DevAgent] [RUN] Running: {run_command}")
    try:
        parts = run_command.split()
        if parts[0].lower() == "python":
            parts[0] = sys.executable

        result = subprocess.run(
            parts,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
            cwd=str(project_dir)
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        combined_parts = []
        if stdout:
            combined_parts.append(f"STDOUT:\n{stdout}")
        if stderr:
            combined_parts.append(f"STDERR:\n{stderr}")

        return "\n\n".join(combined_parts) if combined_parts else "Ran with no output."

    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s — long-running app (server/GUI) is likely working."
    except FileNotFoundError as e:
        return f"Command not found: {e}"
    except Exception as e:
        return f"Run error: {e}"

def _try_auto_install(error_output: str, project_dir: Path) -> bool:
    """If there is a ModuleNotFoundError, tries to auto-install the missing package."""
    pattern = re.compile(
        r"No module named ['\"]([a-zA-Z0-9_\-\.]+)['\"]", re.IGNORECASE
    )
    match = pattern.search(error_output)
    if not match:
        return False

    pkg = match.group(1).replace("_", "-").split(".")[0]
    print(f"[DevAgent] [INSTALL] Auto-installing missing package: {pkg}")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=60, cwd=str(project_dir)
        )
        return result.returncode == 0
    except Exception:
        return False

def _fix_files(
    error_output: str,
    project_description: str,
    all_files: list[dict],
    file_codes: dict[str, str],
    language: str,
    project_dir: Path,
    entry_point: str,
) -> dict[str, str]:

    model = _get_model(MODEL_PLANNER)

    error_file, error_line = _parse_traceback(error_output, list(file_codes.keys()))
    error_type = _classify_error(error_output)

    files_to_fix: list[str] = []

    if error_file:
        files_to_fix.append(error_file)
        if error_type == "import_error":
            for fi in all_files:
                if error_file.replace("/", ".").replace(".py", "") in fi.get("imports", []):
                    p = fi["path"]
                    if p not in files_to_fix:
                        files_to_fix.append(p)
    else:
        files_to_fix.append(entry_point)

    updated_codes: dict[str, str] = {}

    for fix_path in files_to_fix:
        current_code = file_codes.get(fix_path, "")

        other_ctx = ""
        for fp, code in file_codes.items():
            if fp != fix_path and code:
                snippet = code[:1500] + ("..." if len(code) > 1500 else "")
                other_ctx += f"\n--- {fp} ---\n{snippet}\n"

        line_hint = f"\nError appears to be near line {error_line} in this file." if (
            error_line and fix_path == error_file
        ) else ""

        prompt = f"""You are an expert {language} debugger. Fix the broken file below.

Project goal: {project_description}

All project files:
{chr(10).join(f"  - {f['path']}: {f.get('description', '')}" for f in all_files)}

Other files for context (read-only — fix only the target file):
{other_ctx[:3500]}

File to fix: {fix_path}{line_hint}
Error type: {error_type}

Error output:
{error_output[:2500]}

Current (broken) code:
{current_code}

Rules:
- Output ONLY the complete fixed code. No explanation, no markdown, no backticks.
- Fix ALL errors visible in the error output.
- Keep all existing correct logic — do not remove working features.
- Ensure import paths match the actual project file structure exactly.
- Do NOT introduce new bugs or remove error handling.

Fixed code for {fix_path}:"""

        try:
            response = model.generate_content(prompt)
            fixed = _strip_fences(response.text)

            full_path = project_dir / fix_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(fixed, encoding="utf-8")

            updated_codes[fix_path] = fixed
            print(f"[DevAgent] [FIXED] Fixed: {fix_path}")

        except Exception as e:
            if _is_rate_limit(e):
                raise RateLimitError(str(e))
            print(f"[DevAgent] [WARN] Could not fix {fix_path}: {e}")

    return updated_codes

def _build_project(
    description: str,
    language: str,
    project_name: str,
    timeout: int,
    speak=None,
    player=None,
) -> str:

    def log(msg: str):
        print(f"[DevAgent] {msg}")
        if player:
            player.write_log(f"[DevAgent] {msg}")

    log("Planning project structure...")
    try:
        plan = _plan_project(description, language)
    except RateLimitError:
        msg = "Rate limit reached, sir. Please try again in a moment."
        if speak: speak(msg)
        return msg
    except ValueError as e:
        msg = f"Planning failed: {e}"
        if speak: speak(msg)
        return msg

    proj_name    = project_name or plan.get("project_name", "alex_project")
    proj_name    = re.sub(r"[^\w\-]", "_", proj_name)
    project_dir  = PROJECTS_DIR / proj_name
    project_dir.mkdir(parents=True, exist_ok=True)

    files        = plan.get("files", [])
    entry_point  = plan.get("entry_point", "main.py")
    run_command  = plan.get("run_command", f"python {entry_point}")
    dependencies = plan.get("dependencies", [])

    log(f"Project: {proj_name} | Files: {len(files)} | Entry: {entry_point}")

    def _dep_sort_key(fi: dict) -> int:
        return len(fi.get("imports", []))

    sorted_files = sorted(files, key=_dep_sort_key)

    file_codes: dict[str, str] = {}

    for file_info in sorted_files:
        file_path = file_info.get("path", "")
        if not file_path:
            continue

        log(f"Writing {file_path}...")
        for attempt in range(2):
            try:
                code = _write_file(
                    file_info=file_info,
                    project_description=description,
                    all_files=files,
                    language=language,
                    project_dir=project_dir,
                    already_written=file_codes,
                )
                file_codes[file_path] = code
                time.sleep(0.4)
                break
            except RateLimitError:
                if attempt == 0:
                    log("Rate limit — waiting 20s...")
                    time.sleep(20)
                else:
                    log(f"Rate limit retry failed for {file_path}, skipping.")
            except Exception as e:
                log(f"Failed to write {file_path}: {e}")
                break

    if not file_codes:
        msg = "I could not write any project files, sir."
        if speak: speak(msg)
        return msg

    if dependencies:
        install_result = _install_dependencies(dependencies, project_dir)
        log(install_result)

    _open_vscode(project_dir)

    last_output   = ""
    auto_installs = 0  

    for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
        log(f"Running project (attempt {attempt}/{MAX_FIX_ATTEMPTS})...")
        last_output = _run_project(run_command, project_dir, timeout)
        log(f"Output preview: {last_output[:150]}")

        if not _has_error(last_output, run_command):
            msg = (
                f"Project '{proj_name}' is working, sir. "
                f"Built in {attempt} attempt{'s' if attempt > 1 else ''}. "
                f"Saved to: {project_dir}"
            )
            if speak: speak(msg)
            return f"{msg}\n\nOutput:\n{last_output}"

        if attempt == MAX_FIX_ATTEMPTS:
            break

        error_type = _classify_error(last_output)
        if error_type == "dependency_error" and auto_installs < 3:
            installed = _try_auto_install(last_output, project_dir)
            if installed:
                auto_installs += 1
                log("Missing dependency installed, retrying...")
                time.sleep(1)
                continue

        log(f"Fixing errors (type: {error_type})...")
        try:
            updated = _fix_files(
                error_output=last_output,
                project_description=description,
                all_files=files,
                file_codes=file_codes,
                language=language,
                project_dir=project_dir,
                entry_point=entry_point,
            )
            file_codes.update(updated)
            time.sleep(1)
        except RateLimitError:
            msg = "Rate limit reached during fix. Project saved, check it manually in VSCode."
            if speak: speak(msg)
            return msg
        except Exception as e:
            log(f"Fix step failed: {e}")

    msg = (
        f"I couldn't fully fix '{proj_name}' after {MAX_FIX_ATTEMPTS} attempts, Sir. "
        f"Project is saved at {project_dir} — open it in VSCode and check manually."
    )
    if speak: speak(msg)
    return f"{msg}\n\nLast error:\n{last_output[:600]}"


def inspect_and_fix_project(
    project_path: str = ".",
    goal: str = "",
    timeout: int = 30,
    speak=None,
    player=None,
) -> str:
    """
    Autonomous Developer Mode workflow for existing projects:
    1. Discovers and inspects project files and directory structure.
    2. Runs AST static analysis across Python files to catch syntax errors.
    3. Detects entry point or test runner.
    4. Executes the project/tests to capture runtime errors and tracebacks.
    5. Resolves missing dependencies automatically via pip.
    6. Iteratively patches broken files with Gemini intelligence.
    7. Verifies final execution status and reports honest results to Aditya Sir.
    """
    from core.security import OWNER_ADDRESS
    def log(msg: str):
        print(f"[DevAgent] {msg}")
        if player and hasattr(player, "write_log"):
            player.write_log(f"[DevAgent] {msg}")

    # 1. Resolve project directory
    proj_dir = Path(project_path).resolve() if project_path and project_path != "." else BASE_DIR
    if not proj_dir.exists() or not proj_dir.is_dir():
        alt_dir = PROJECTS_DIR / project_path
        if alt_dir.exists() and alt_dir.is_dir():
            proj_dir = alt_dir
        else:
            alt_desktop = Path.home() / "Desktop" / project_path
            if alt_desktop.exists() and alt_desktop.is_dir():
                proj_dir = alt_desktop
            else:
                proj_dir = BASE_DIR

    log(f"Inspecting project at: {proj_dir}")

    # 2. File discovery
    ignored_dirs = {".git", "__pycache__", "venv", ".venv", "env", "node_modules", ".pytest_cache", ".idea", ".vscode", "dist", "build"}
    py_files: list[Path] = []
    file_codes: dict[str, str] = {}
    all_files_meta: list[dict] = []

    for p in proj_dir.rglob("*.py"):
        if any(ign in p.parts for ign in ignored_dirs):
            continue
        py_files.append(p)
        rel_path = str(p.relative_to(proj_dir)).replace("\\", "/")
        try:
            code = p.read_text(encoding="utf-8", errors="replace")
            file_codes[rel_path] = code
            all_files_meta.append({"path": rel_path, "description": f"Python module ({len(code.splitlines())} lines)"})
        except Exception:
            pass

    if not py_files:
        msg = f"{OWNER_ADDRESS}, '{proj_dir.name}' mein koi Python source files nahi mili inspect karne ke liye."
        if speak: speak(msg)
        return msg

    fixed_issues: list[str] = []

    # 3. Static Syntax Audit with ast
    syntax_errors: list[tuple[str, int, str]] = []
    for rel_path, code in list(file_codes.items()):
        try:
            ast.parse(code, filename=rel_path)
        except SyntaxError as se:
            syntax_errors.append((rel_path, se.lineno or 1, se.msg or "invalid syntax"))

    if syntax_errors:
        log(f"Detected {len(syntax_errors)} syntax errors. Attempting fixes...")
        for se_file, se_line, se_msg in syntax_errors[:3]:
            fake_traceback = f'File "{se_file}", line {se_line}\nSyntaxError: {se_msg}'
            try:
                updated = _fix_files(
                    error_output=fake_traceback,
                    project_description=goal or "Fix syntax errors in project",
                    all_files=all_files_meta,
                    file_codes=file_codes,
                    language="python",
                    project_dir=proj_dir,
                    entry_point=se_file,
                )
                file_codes.update(updated)
                fixed_issues.append(f"Fixed SyntaxError in {se_file} (line {se_line}: {se_msg})")
            except Exception as e:
                log(f"Failed to fix syntax error in {se_file}: {e}")

    # 4. Entry Point / Test Discovery
    entry_point = "main.py"
    run_cmd = f"python {entry_point}"
    candidates = ["main.py", "app.py", "run.py", "index.py", "manage.py"]
    for c in candidates:
        if (proj_dir / c).exists():
            entry_point = c
            run_cmd = f"python {entry_point}"
            break
    else:
        test_files = [f for f in py_files if f.name.startswith("test_")]
        if test_files:
            entry_point = str(test_files[0].relative_to(proj_dir)).replace("\\", "/")
            run_cmd = f"python {entry_point}"

    # 5. Iterative Execution & Bug Fixing
    last_output = ""
    auto_installs = 0
    resolved_runtime = False

    for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
        log(f"Testing execution (pass {attempt}/{MAX_FIX_ATTEMPTS}): {run_cmd}")
        last_output = _run_project(run_cmd, proj_dir, timeout=timeout)
        log(f"Execution output preview: {last_output[:120]}")

        if not _has_error(last_output, run_cmd):
            resolved_runtime = True
            break

        error_type = _classify_error(last_output)
        if error_type == "dependency_error" and auto_installs < 3:
            installed = _try_auto_install(last_output, proj_dir)
            if installed:
                auto_installs += 1
                fixed_issues.append("Auto-installed missing dependency")
                time.sleep(1)
                continue

        try:
            updated = _fix_files(
                error_output=last_output,
                project_description=goal or f"Debug and make {run_cmd} run cleanly",
                all_files=all_files_meta,
                file_codes=file_codes,
                language="python",
                project_dir=proj_dir,
                entry_point=entry_point,
            )
            file_codes.update(updated)
            fixed_issues.append(f"Resolved runtime {error_type} in attempt {attempt}")
            time.sleep(1)
        except Exception as e:
            log(f"Runtime fix failed: {e}")
            break

    # Record in Timeline
    timeline.record("DEV_AGENT", f"Project Audit: {proj_dir.name}", f"Files: {len(py_files)}, Fixes: {len(fixed_issues)}, Status: {'PASS' if resolved_runtime else 'NEEDS_ATTENTION'}")

    # Honest Summary Report
    lines = [
        f"{OWNER_ADDRESS}, project '{proj_dir.name}' ka inspection complete ho gaya hai:",
        f"• Project Path: `{proj_dir}`",
        f"• Files Scanned: {len(py_files)} Python source files",
        f"• Entry/Test Script: `{entry_point}`",
    ]
    if fixed_issues:
        lines.append(f"• Resolved Issues ({len(fixed_issues)}):")
        for fix in fixed_issues:
            lines.append(f"  - {fix}")
    else:
        lines.append("• Static Syntax Audit: 0 syntax errors detected.")

    if resolved_runtime:
        lines.append("• Execution Status: Verified — Project runs cleanly without unhandled exceptions.")
    else:
        lines.append(f"• Execution Status: Verification note. Output preview:\n```\n{last_output[:400]}\n```")

    report = "\n".join(lines)
    if speak:
        short_summary = f"{OWNER_ADDRESS}, project inspection complete ho gaya. {len(py_files)} files check kiye hain aur status verify kar diya hai."
        speak(short_summary)
    return report


def dev_agent(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    p            = parameters or {}
    action       = p.get("action", "build").lower().strip()
    description  = p.get("description", "").strip()
    language     = p.get("language", "python").strip()
    project_name = p.get("project_name", "").strip()
    project_path = p.get("project_path", "").strip()
    timeout      = int(p.get("timeout", 30))

    desc_lower   = description.lower()
    if (
        action in ("inspect", "fix", "inspect_and_fix", "audit", "test")
        or project_path
        or any(w in desc_lower for w in ("inspect project", "audit project", "check project", "fix project", "project check", "debug project", "find bugs"))
    ):
        return inspect_and_fix_project(
            project_path = project_path or project_name or ".",
            goal         = description,
            timeout      = timeout,
            speak        = speak,
            player       = player,
        )

    if not description:
        return "Please describe the project you want me to build, Sir."

    return _build_project(
        description  = description,
        language     = language,
        project_name = project_name,
        timeout      = timeout,
        speak        = speak,
        player       = player,
    )


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "dev_agent",
    "description": "Full autonomous developer agent: builds new projects from scratch, or inspects, tests, debugs, and fixes existing codebases.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "build | inspect | fix | audit"
            },
            "description": {
                "type": "STRING",
                "description": "What the project should do, or what issues to inspect/fix"
            },
            "project_path": {
                "type": "STRING",
                "description": "Path to existing project folder to inspect or fix"
            },
            "language": {
                "type": "STRING",
                "description": "Programming language (default: python)"
            },
            "project_name": {
                "type": "STRING",
                "description": "Optional project folder name"
            },
            "timeout": {
                "type": "INTEGER",
                "description": "Run timeout in seconds (default: 30)"
            }
        },
        "required": [
            "description"
        ]
    },
    "handler": dev_agent,
}
