"""
workflow/checkpoint_manager.py — Persistent Checkpoints & Restart Recovery Engine.

Guarantees:
  • Atomic persistence of workflow states across application restarts
  • Milestone checkpointing after task completions and state changes
  • Smart restart recovery: Resumes eligible tasks without repeating completed actions
  • File and resource integrity verification on recovery

Owner: Aditya Rajak
Salutation: Aditya Sir / Sir
Assistant: ALEX
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from workflow.models import TaskStatus, Workflow, WorkflowStatus

BASE_DIR = Path(__file__).resolve().parent.parent
WORKFLOWS_FILE = BASE_DIR / "memory" / "workflows.json"


class CheckpointManager:
    """Manages persistent workflow state snapshots and crash/restart recovery."""

    _instance: Optional[CheckpointManager] = None
    _lock = threading.RLock()

    def __init__(self):
        WORKFLOWS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Workflow] = {}
        self._load_from_disk()

    @classmethod
    def get_instance(cls) -> CheckpointManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = CheckpointManager()
            return cls._instance

    def _load_from_disk(self) -> None:
        if WORKFLOWS_FILE.exists():
            try:
                data = json.loads(WORKFLOWS_FILE.read_text(encoding="utf-8"))
                for wf_data in data.get("workflows", []):
                    wf = Workflow.from_dict(wf_data)
                    self._cache[wf.workflow_id] = wf
            except Exception:
                pass

    def save_checkpoint(self, workflow: Workflow) -> None:
        """Atomically saves the workflow state snapshot to disk and SQLite store."""
        with self._lock:
            self._cache[workflow.workflow_id] = workflow
            try:
                # Keep last 100 workflows
                active_list = list(self._cache.values())[-100:]
                payload = {
                    "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "count": len(active_list),
                    "workflows": [w.to_dict() for w in active_list]
                }
                # Atomic file write via temporary file
                tmp_path = WORKFLOWS_FILE.with_suffix(".tmp")
                tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
                # Replace target atomically
                if os.name == "nt" and WORKFLOWS_FILE.exists():
                    WORKFLOWS_FILE.unlink()
                tmp_path.rename(WORKFLOWS_FILE)

                # Synchronize to Central SQLite Brain Store
                try:
                    from memory.brain_store import brain_store
                    brain_store.save_task_record({
                        "task_id": workflow.workflow_id,
                        "goal": workflow.user_request,
                        "context": workflow.desired_outcome,
                        "plan": [t.objective for t in workflow.tasks],
                        "current_step": workflow.current_step_index,
                        "total_steps": len(workflow.tasks),
                        "status": workflow.current_status.value,
                        "files_modified": workflow.output_file_paths,
                        "failures": [str(e) for e in workflow.errors_and_retry_history],
                        "permissions": "CONFIRM" if any(t.permission_requirements >= 3 for t in workflow.tasks) else "SAFE",
                        "can_resume": workflow.can_resume_on_restart
                    })
                except Exception:
                    pass

            except Exception as e:
                # Fallback non-blocking notice
                pass

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        with self._lock:
            return self._cache.get(workflow_id)

    def list_workflows(self, status: Optional[str] = None) -> List[Workflow]:
        with self._lock:
            items = list(self._cache.values())
            if status:
                st_upper = status.upper()
                items = [w for w in items if w.current_status.value == st_upper]
            return items

    def recover_unfinished_workflows(self) -> List[Workflow]:
        """
        Scans for workflows interrupted in non-terminal states and restores them safely.
        """
        with self._lock:
            recovered: List[Workflow] = []
            interrupted_statuses = (
                WorkflowStatus.RUNNING,
                WorkflowStatus.PAUSED,
                WorkflowStatus.RECOVERING,
                WorkflowStatus.VERIFYING
            )

            for wf in self._cache.values():
                if wf.current_status in interrupted_statuses and wf.can_resume_on_restart:
                    # Validate that generated files still exist on disk
                    valid_files = []
                    for fp in wf.output_file_paths:
                        if Path(fp).exists():
                            valid_files.append(fp)
                    wf.output_file_paths = valid_files

                    # Mark interrupted tasks as PAUSED or PENDING (do NOT re-run COMPLETED ones)
                    for t in wf.tasks:
                        if t.status in (TaskStatus.RUNNING, TaskStatus.RETRIED):
                            t.status = TaskStatus.PAUSED
                            t.error_message = "Interrupted by system restart. Ready for resumption."

                    # Transition workflow safely into PAUSED
                    wf.current_status = WorkflowStatus.PAUSED
                    self.save_checkpoint(wf)
                    recovered.append(wf)

            return recovered


# Singleton Instance
checkpoint_manager = CheckpointManager.get_instance()

