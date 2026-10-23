"""
dev_lab/fixer.py — Safe Automatic Code Fixer & Approval Gating.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dev_lab.change_guard import CodeChangeGuard
from dev_lab.models import BugCategory, BugSeverity, Finding, PatchResult


class SafeCodeFixer:
    """Performs surgical, targeted fixes for verified low-risk defects.

    Complex, security-sensitive, or architectural modifications are gated behind approval requests.
    """

    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()
        self.guard = CodeChangeGuard(self.root)

    def apply_fix(self, finding: Finding) -> PatchResult:
        """Apply targeted fix for the given confirmed finding."""
        target_path = self.root / finding.file_path
        if not target_path.exists():
            return PatchResult(
                success=False,
                modified_files=[],
                diff="",
                message=f"Target file {finding.file_path} not found.",
            )

        # 1. Approval Gate Check for high risk or security-sensitive changes
        if finding.requires_approval or finding.severity == BugSeverity.CRITICAL or finding.category == BugCategory.SECURITY:
            return PatchResult(
                success=False,
                modified_files=[finding.file_path],
                diff="",
                requires_approval=True,
                approval_id=f"APPR-FIX-{finding.id}",
                message=f"Modification requires Level 3 Approval from Aditya Sir ({finding.title}).",
            )

        # 2. Checkpoint creation before modification
        checkpoint_id, backed_up = self.guard.create_checkpoint(finding.id, [finding.file_path])

        original_content = target_path.read_text(encoding="utf-8")
        modified_content = original_content

        # 3. Surgical fix strategies based on category
        fixed = False
        fix_note = ""

        if finding.category == BugCategory.THREADING_ASYNC and "time.sleep" in finding.evidence:
            # Replace time.sleep(...) with await asyncio.sleep(...) in async functions
            modified_content = self._fix_async_blocking_sleep(original_content)
            fixed = modified_content != original_content
            fix_note = "Replaced blocking time.sleep with await asyncio.sleep"

        elif finding.category == BugCategory.RESOURCE_LEAK and "open()" in finding.evidence:
            # Wrap open call or add close
            modified_content = self._fix_resource_leak(original_content, finding.line_number)
            fixed = modified_content != original_content
            fix_note = "Refactored unmanaged file open into context manager pattern"

        elif finding.category == BugCategory.IMPORT and "Missing Module Import" in finding.title:
            # Fix missing import statement or add required import
            modified_content = self._fix_missing_import(original_content, finding)
            fixed = modified_content != original_content
            fix_note = "Added missing import statement"

        elif finding.category == BugCategory.SYNTAX:
            # Fix simple syntax errors (e.g. missing colon, unbalanced parenthesis on target line)
            modified_content = self._fix_syntax_error(original_content, finding.line_number)
            fixed = modified_content != original_content
            fix_note = "Corrected syntax error at target line"

        elif finding.category == BugCategory.INVALID_CONFIG and target_path.suffix == ".json":
            # Fix trailing commas in JSON
            modified_content = self._fix_json_syntax(original_content)
            fixed = modified_content != original_content
            fix_note = "Removed trailing commas and sanitized JSON configuration"

        if not fixed:
            # Clean rollback if no modification succeeded
            self.guard.rollback_checkpoint(checkpoint_id)
            return PatchResult(
                success=False,
                modified_files=[],
                diff="",
                message=f"No automatic surgical fix could be applied with high confidence for {finding.id}.",
            )

        # 4. Write modified content and generate unified diff
        target_path.write_text(modified_content, encoding="utf-8")
        diff = self.guard.generate_diff(original_content, modified_content, finding.file_path)

        finding.diff = diff
        finding.suggested_fix = fix_note

        return PatchResult(
            success=True,
            modified_files=[finding.file_path],
            diff=diff,
            requires_approval=False,
            message=f"Successfully applied fix: {fix_note}",
            backup_id=checkpoint_id,
        )

    def _fix_async_blocking_sleep(self, content: str) -> str:
        # Check if asyncio is imported
        has_asyncio = bool(re.search(r'^\s*import\s+asyncio\b', content, re.MULTILINE))
        lines = content.splitlines()
        new_lines = []

        if not has_asyncio:
            new_lines.append("import asyncio")

        for line in lines:
            if "time.sleep(" in line:
                # Replace with await asyncio.sleep
                new_line = re.sub(r'\btime\.sleep\(', 'await asyncio.sleep(', line)
                new_lines.append(new_line)
            else:
                new_lines.append(line)

        return "\n".join(new_lines) + ("\n" if content.endswith("\n") else "")

    def _fix_resource_leak(self, content: str, line_no: Optional[int]) -> str:
        lines = content.splitlines()
        if not line_no or line_no > len(lines):
            return content

        idx = line_no - 1
        target_line = lines[idx]

        # e.g.: f = open("test.txt", "r") -> with open("test.txt", "r") as f:
        m = re.match(r'^(\s*)([a-zA-Z0-9_]+)\s*=\s*(open\(.+\))\s*$', target_line)
        if m:
            indent, var_name, open_call = m.groups()
            lines[idx] = f"{indent}with {open_call} as {var_name}:"
            # Indent following line if present
            if idx + 1 < len(lines):
                lines[idx + 1] = f"    {lines[idx + 1]}"
            return "\n".join(lines) + ("\n" if content.endswith("\n") else "")

        return content

    def _fix_missing_import(self, content: str, finding: Finding) -> str:
        # Extract missing package or class from title or evidence
        m = re.search(r'Missing Module Import:\s*([a-zA-Z0-9_\.]+)', finding.title)
        if m:
            mod_to_import = m.group(1).split(".")[0]
            import_stmt = f"import {mod_to_import}"
            return f"{import_stmt}\n{content}"
        return content

    def _fix_syntax_error(self, content: str, line_no: Optional[int]) -> str:
        lines = content.splitlines()
        if not line_no or line_no > len(lines):
            return content

        idx = line_no - 1
        target = lines[idx]

        # Check for missing colon at end of def/if/for/while/class
        if re.match(r'^\s*(def\s+|class\s+|if\s+|elif\s+|else\s*|for\s+|while\s+|try\s*|except\s*)', target):
            if not target.strip().endswith(":"):
                lines[idx] = f"{target}:"
                return "\n".join(lines) + ("\n" if content.endswith("\n") else "")

        return content

    def _fix_json_syntax(self, content: str) -> str:
        # Remove trailing commas before } or ]
        cleaned = re.sub(r',\s*([}\]])', r'\1', content)
        return cleaned

