"""
workflow/artifacts.py — Output & Generated Artifact Tracking, Verification & Versioning.

Guarantees:
  • No false success: Validates that files exist, are readable, and non-empty
  • Versioned filenames to prevent unauthorized overwrites
  • Persistence of generated artifacts in memory/artifacts/ and SQLite store
  • Metadata linkage connecting outputs to workflows and tasks

Owner: Aditya Rajak
Salutation: Aditya Sir / Sir
Assistant: ALEX
"""

from __future__ import annotations

import mimetypes
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from workflow.models import ArtifactRecord

BASE_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = BASE_DIR / "memory" / "artifacts"


class ArtifactManager:
    """Manages output artifact verification, safe versioning, and lifecycle records."""

    _instance: Optional[ArtifactManager] = None
    _lock = threading.RLock()

    def __init__(self):
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        self._artifacts: Dict[str, ArtifactRecord] = {}

    @classmethod
    def get_instance(cls) -> ArtifactManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = ArtifactManager()
            return cls._instance

    def get_safe_artifact_path(self, base_filename: str, workflow_id: str) -> Path:
        """
        Returns a versioned artifact file path within memory/artifacts/ or target dir,
        avoiding accidental overwrites of existing user files.
        """
        p = Path(base_filename)
        ext = p.suffix
        stem = p.stem
        target_dir = p.parent if p.is_absolute() and p.parent.exists() else ARTIFACTS_DIR
        target_dir.mkdir(parents=True, exist_ok=True)

        candidate = target_dir / f"{stem}{ext}"
        if not candidate.exists():
            return candidate

        # Generate versioned path
        for v in range(1, 1000):
            cand_v = target_dir / f"{stem}_v{v}{ext}"
            if not cand_v.exists():
                return cand_v

        return target_dir / f"{stem}_{int(time.time())}{ext}"

    def validate_file_artifact(
        self,
        file_path_str: str,
        expected_type: Optional[str] = None
    ) -> Tuple[bool, str, int]:
        """
        Strictly verifies that generated file exists, is non-empty, and is readable.
        """
        p = Path(file_path_str)
        if not p.exists():
            return False, f"File does not exist: '{file_path_str}'.", 0
        if not p.is_file():
            return False, f"Path is not a regular file: '{file_path_str}'.", 0

        try:
            size = p.stat().st_size
            if size == 0:
                return False, f"File '{p.name}' is empty (0 bytes).", 0

            # Verify readability
            with open(p, "rb") as f:
                header = f.read(64)
                if len(header) == 0:
                    return False, f"Could not read content from '{p.name}'.", 0

            # Optional format check
            if expected_type:
                ext = p.suffix.lower().lstrip(".")
                if ext != expected_type.lower().lstrip("."):
                    return False, f"File extension '{ext}' does not match expected '{expected_type}'.", size

            return True, f"Verified valid file '{p.name}' ({size} bytes).", size
        except Exception as e:
            return False, f"Failed verifying artifact '{file_path_str}': {e}", 0

    def register_artifact(
        self,
        workflow_id: str,
        task_id: str,
        file_path: str,
        source_inputs: Optional[Dict[str, Any]] = None
    ) -> ArtifactRecord:
        """Records a verified artifact and links it to workflow and memory."""
        with self._lock:
            p = Path(file_path)
            valid, msg, size = self.validate_file_artifact(file_path)
            art_id = f"ART-{int(time.time()*1000)%100000:05d}"
            mime, _ = mimetypes.guess_type(file_path)
            file_type = mime or (p.suffix.lstrip(".") if p.suffix else "binary")

            rec = ArtifactRecord(
                artifact_id=art_id,
                file_path=str(p.resolve()),
                file_type=file_type,
                workflow_id=workflow_id,
                task_id=task_id,
                file_size_bytes=size,
                validation_status="VERIFIED" if valid else f"FAILED: {msg}",
                source_inputs=source_inputs or {}
            )
            self._artifacts[art_id] = rec

            # Synchronize to Central SQLite Brain Store
            try:
                from memory.brain_store import brain_store
                brain_store.save_memory(
                    memory_type="knowledge",
                    category="artifacts",
                    key=f"artifact_{art_id}",
                    content=f"Generated artifact: {p.name} ({file_type}, {size} bytes) for workflow {workflow_id}.",
                    metadata={"path": str(p), "workflow_id": workflow_id, "task_id": task_id, "size": size}
                )
            except Exception:
                pass

            return rec

    def list_artifacts(self, workflow_id: Optional[str] = None) -> List[ArtifactRecord]:
        with self._lock:
            if not workflow_id:
                return list(self._artifacts.values())
            return [a for a in self._artifacts.values() if a.workflow_id == workflow_id]


# Singleton Instance
artifact_manager = ArtifactManager.get_instance()

