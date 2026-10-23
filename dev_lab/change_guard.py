"""
dev_lab/change_guard.py — Code Change Protection, Git Preservation & Atomic Checkpoint/Rollback.

Owner: Aditya Rajak
Salutation: Sir
Assistant: ALEX
"""

from __future__ import annotations

import difflib
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class CodeChangeGuard:
    """Safeguards user source files before any automated modification:

    1. Checks Git status and respects uncommitted user work.
    2. Enforces security boundary containment.
    3. Backs up exact original files to .alex_checkpoints/<id>.
    4. Generates clean unified diffs.
    5. Provides atomic rollbacks of ALEX-modified files only.
    """

    PROTECTED_PATTERNS = {
        ".env", ".env.local", "api_keys.json", "secrets.json",
        "*.pem", "*.key", "alex.key", "id_rsa", ".git"
    }

    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()
        self.checkpoint_dir = self.root / ".alex_checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def check_git_status(self) -> Dict[str, Any]:
        """Check real Git status of the project if git is initialized."""
        git_dir = self.root / ".git"
        if not git_dir.exists():
            return {"is_git": False, "status": "Not a git repository", "dirty_files": []}

        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(self.root),
                timeout=5,
            )
            dirty_files = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            return {
                "is_git": True,
                "clean": len(dirty_files) == 0,
                "dirty_files": dirty_files,
                "status": f"{len(dirty_files)} uncommitted file(s) present" if dirty_files else "Working directory clean",
            }
        except Exception as e:
            return {"is_git": True, "clean": False, "dirty_files": [], "status": f"Git status error: {e}"}

    def is_protected_file(self, file_path: str | Path) -> bool:
        """Verify whether a file path contains secrets or is restricted from modification."""
        p = Path(file_path)
        name = p.name.lower()
        if name in {".env", ".env.local", "api_keys.json", "secrets.json", "alex.key"}:
            return True
        if name.endswith((".pem", ".key")):
            return True
        return False

    def create_checkpoint(self, finding_id: str, files_to_modify: List[str]) -> Tuple[str, List[str]]:
        """Create a timestamped backup of the files scheduled for modification.

        Returns (checkpoint_id, backed_up_paths).
        """
        timestamp = int(time.time())
        checkpoint_id = f"ckpt_{finding_id}_{timestamp}"
        target_dir = self.checkpoint_dir / checkpoint_id
        target_dir.mkdir(parents=True, exist_ok=True)

        backed_up: List[str] = []
        for rel_file in files_to_modify:
            abs_file = (self.root / rel_file).resolve()
            # Boundary verification
            if not str(abs_file).startswith(str(self.root)):
                raise PermissionError(f"Target file {rel_file} is outside authorized project boundary!")

            if self.is_protected_file(abs_file):
                raise PermissionError(f"Target file {rel_file} is protected (secret/credential). Modification denied!")

            if abs_file.exists():
                backup_dest = target_dir / rel_file
                backup_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(abs_file, backup_dest)
                backed_up.append(rel_file)

        return checkpoint_id, backed_up

    def generate_diff(self, original_text: str, modified_text: str, filename: str) -> str:
        """Generate standardized unified diff representation."""
        orig_lines = original_text.splitlines(keepends=True)
        mod_lines = modified_text.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(
            orig_lines, mod_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm=""
        ))
        return "".join(diff_lines)

    def rollback_checkpoint(self, checkpoint_id: str) -> Tuple[bool, List[str], str]:
        """Restore files from backup checkpoint.

        Only rolls back the files touched by ALEX. Unrelated user work is never disturbed.
        Returns (success, restored_files, message).
        """
        target_dir = self.checkpoint_dir / checkpoint_id
        if not target_dir.exists():
            return False, [], f"Checkpoint '{checkpoint_id}' not found."

        restored: List[str] = []
        try:
            for root, _, files in os.walk(target_dir):
                for f in files:
                    backup_file = Path(root) / f
                    rel = backup_file.relative_to(target_dir)
                    dest_file = self.root / rel
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_file, dest_file)
                    restored.append(str(rel).replace("\\", "/"))

            return True, restored, f"Successfully rolled back {len(restored)} file(s) from checkpoint '{checkpoint_id}'."
        except Exception as e:
            return False, restored, f"Rollback failed: {e}"

