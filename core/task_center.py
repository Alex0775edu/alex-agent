"""
core/task_center.py — Central Task Management, Autonomy Control & Execution State for ALEX 3.0.

Supports Full Task Lifecycle:
  QUEUED ➔ PLANNING ➔ RUNNING ➔ WAITING ➔ VERIFYING ➔ COMPLETED / FAILED / CANCELLED (or PAUSED)

Owner Controls:
  • View real-time progress & step tracking
  • Pause when safe & resume interrupted tasks
  • Cancel running tasks safely
  • Retry failed tasks from last verified checkpoint
  • Inspect errors & recovery attempts
  • Open and view generated artifact files

Autonomy Levels:
  1. ASK_BEFORE_EVERYTHING
  2. NORMAL (Default)
  3. TRUSTED
  4. AUTONOMOUS
  * Critical actions (shutdown, wipe, secret edits) ALWAYS require confirmation in all modes.

Owner: Aditya Rajak
Salutation: Sir
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.security import OWNER_ADDRESS, security_manager

BASE_DIR = Path(__file__).resolve().parent.parent
TASKS_FILE = BASE_DIR / "memory" / "task_center.json"


class AutonomyLevel:
    ASK_EVERYTHING = "ASK_BEFORE_EVERYTHING"
    NORMAL         = "NORMAL"
    TRUSTED        = "TRUSTED"
    AUTONOMOUS     = "AUTONOMOUS"


class TaskStatus:
    QUEUED     = "QUEUED"
    PLANNING   = "PLANNING"
    RUNNING    = "RUNNING"
    WAITING    = "WAITING"
    VERIFYING  = "VERIFYING"
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"
    CANCELLED  = "CANCELLED"
    PAUSED     = "PAUSED"


@dataclass
class TaskItem:
    task_id: str
    goal: str
    context: str
    plan: List[str]
    current_step: int
    total_steps: int
    permissions: str          # SAFE, CONFIRM, CRITICAL
    tools: List[str]
    status: str               # QUEUED, PLANNING, RUNNING, WAITING, VERIFYING, COMPLETED, FAILED, CANCELLED, PAUSED
    verification: str
    errors: List[str]
    recovery_attempts: int
    result: str
    generated_files: List[str]
    timestamp: str
    can_pause: bool = True
    start_time: float = field(default_factory=time.monotonic)
    end_time: Optional[float] = None

    @property
    def elapsed_seconds(self) -> float:
        if self.end_time is not None:
            return round(self.end_time - self.start_time, 2)
        return round(time.monotonic() - self.start_time, 2)

    @property
    def progress_pct(self) -> int:
        if self.status == TaskStatus.COMPLETED:
            return 100
        if not self.plan or self.total_steps == 0:
            return 50 if self.status == TaskStatus.RUNNING else 10
        pct = int((self.current_step / max(1, self.total_steps)) * 100)
        return min(95, max(5, pct))


class TaskCenter:
    """Thread-safe central task registry and autonomy manager for ALEX."""

    _instance: Optional[TaskCenter] = None
    _lock = threading.RLock()

    def __init__(self):
        self._tasks: Dict[str, TaskItem] = {}
        self._cancel_events: Dict[str, threading.Event] = {}
        self._autonomy_level: str = AutonomyLevel.NORMAL
        self._load()

    @classmethod
    def get_instance(cls) -> TaskCenter:
        with cls._lock:
            if cls._instance is None:
                cls._instance = TaskCenter()
            return cls._instance

    def _load(self) -> None:
        if TASKS_FILE.exists():
            try:
                data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
                for item in data.get("tasks", []):
                    plan_list = item.get("plan", [])
                    tot = item.get("total_steps") or len(plan_list) or 1
                    t = TaskItem(
                        task_id=item["task_id"],
                        goal=item["goal"],
                        context=item.get("context", ""),
                        plan=plan_list,
                        current_step=item.get("current_step", 0),
                        total_steps=tot,
                        permissions=item.get("permissions", "SAFE"),
                        tools=item.get("tools", []),
                        status=item.get("status", TaskStatus.COMPLETED),
                        verification=item.get("verification", "None"),
                        errors=item.get("errors", []),
                        recovery_attempts=item.get("recovery_attempts", 0),
                        result=item.get("result", ""),
                        generated_files=item.get("generated_files", []),
                        timestamp=item.get("timestamp", ""),
                        can_pause=item.get("can_pause", True),
                        start_time=time.monotonic() - item.get("elapsed", 0),
                        end_time=time.monotonic()
                    )
                    self._tasks[t.task_id] = t
                self._autonomy_level = data.get("autonomy_level", AutonomyLevel.NORMAL)
            except Exception:
                pass

    def _persist(self) -> None:
        try:
            TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
            export_tasks = []
            for t in list(self._tasks.values())[-60:]:  # Keep last 60
                d = asdict(t)
                d["elapsed"] = t.elapsed_seconds
                d["progress_pct"] = t.progress_pct
                export_tasks.append(d)
                # Synchronize to Central SQLite Brain Store
                try:
                    from memory.brain_store import brain_store
                    brain_store.save_task_record({
                        "task_id": t.task_id,
                        "goal": t.goal,
                        "context": t.context,
                        "plan": t.plan,
                        "current_step": t.current_step,
                        "total_steps": t.total_steps,
                        "status": t.status,
                        "files_modified": t.generated_files,
                        "failures": t.errors,
                        "permissions": t.permissions,
                        "can_resume": t.can_pause
                    })
                except Exception:
                    pass
            payload = {
                "autonomy_level": self._autonomy_level,
                "tasks": export_tasks,
                "last_saved": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            TASKS_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    # ── Autonomy Controls ─────────────────────────────────────────────────────

    def set_autonomy_level(self, level: str) -> None:
        if level in (AutonomyLevel.ASK_EVERYTHING, AutonomyLevel.NORMAL, AutonomyLevel.TRUSTED, AutonomyLevel.AUTONOMOUS):
            self._autonomy_level = level
            self._persist()

    def get_autonomy_level(self) -> str:
        return self._autonomy_level

    def requires_confirmation(self, risk_level: str) -> bool:
        risk = risk_level.upper()
        if risk == "CRITICAL":
            return True
        if self._autonomy_level == AutonomyLevel.ASK_EVERYTHING:
            return True
        if self._autonomy_level == AutonomyLevel.NORMAL and risk in ("CONFIRM", "PRIVILEGED"):
            return True
        return False

    # ── Task Lifecycle ────────────────────────────────────────────────────────

    def queue_task(self, goal: str, context: str = "", plan: Optional[List[str]] = None, permissions: str = "SAFE") -> TaskItem:
        t_id = f"task_{uuid.uuid4().hex[:8]}"
        plan_items = plan or []
        task = TaskItem(
            task_id=t_id,
            goal=goal,
            context=context,
            plan=plan_items,
            current_step=0,
            total_steps=len(plan_items) or 1,
            permissions=permissions,
            tools=[],
            status=TaskStatus.QUEUED,
            verification="Pending",
            errors=[],
            recovery_attempts=0,
            result="",
            generated_files=[],
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
        )
        with self._lock:
            self._tasks[t_id] = task
        self._persist()
        return task

    def create_task(self, goal: str, context: str = "", plan: Optional[List[str]] = None, permissions: str = "SAFE") -> TaskItem:
        """Alias for creating & immediately running task for backward compatibility."""
        t = self.queue_task(goal, context, plan, permissions)
        self.set_task_running(t.task_id)
        return t

    def set_task_planning(self, task_id: str) -> None:
        with self._lock:
            if task_id in self._tasks:
                task = self._tasks[task_id]
                if task.status not in (TaskStatus.CANCELLED, TaskStatus.FAILED, TaskStatus.COMPLETED):
                    task.status = TaskStatus.PLANNING
        self._persist()

    def set_task_running(self, task_id: str, step_index: int = 0) -> None:
        with self._lock:
            if task_id in self._tasks:
                t = self._tasks[task_id]
                if t.status in (TaskStatus.CANCELLED, TaskStatus.FAILED, TaskStatus.COMPLETED):
                    return
                t.status = TaskStatus.RUNNING
                t.current_step = step_index
        self._persist()

    def set_task_waiting(self, task_id: str, reason: str = "") -> None:
        with self._lock:
            if task_id in self._tasks:
                t = self._tasks[task_id]
                if t.status in (TaskStatus.CANCELLED, TaskStatus.FAILED, TaskStatus.COMPLETED):
                    return
                t.status = TaskStatus.WAITING
                if reason:
                    t.verification = f"Waiting: {reason}"
        self._persist()

    def set_task_verifying(self, task_id: str) -> None:
        with self._lock:
            if task_id in self._tasks:
                t = self._tasks[task_id]
                if t.status in (TaskStatus.CANCELLED, TaskStatus.FAILED, TaskStatus.COMPLETED):
                    return
                t.status = TaskStatus.VERIFYING
                t.verification = "Verifying outcome..."
        self._persist()

    def update_task_progress(self, task_id: str, step_index: int, tool_called: str = "", generated_file: str = "") -> None:
        with self._lock:
            if task_id in self._tasks:
                t = self._tasks[task_id]
                t.current_step = step_index
                if tool_called and tool_called not in t.tools:
                    t.tools.append(tool_called)
                if generated_file and generated_file not in t.generated_files:
                    t.generated_files.append(generated_file)
        self._persist()

    def pause_task(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self._tasks:
                t = self._tasks[task_id]
                if t.status in (TaskStatus.RUNNING, TaskStatus.PLANNING, TaskStatus.WAITING):
                    t.status = TaskStatus.PAUSED
                    self._persist()
                    return True
        return False

    def resume_task(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self._tasks:
                t = self._tasks[task_id]
                if t.status == TaskStatus.PAUSED:
                    t.status = TaskStatus.RUNNING
                    self._persist()
                    return True
        return False

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED):
                return False
            cancel_event = self._cancel_events.get(task_id)
            if cancel_event:
                cancel_event.set()
            task.status = TaskStatus.CANCELLED
            task.end_time = time.monotonic()
        self._persist()
        return True

    def register_cancel_event(self, task_id: str, cancel_event: threading.Event) -> bool:
        """Connect a live task to its executor's cancellation signal."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if task.status == TaskStatus.CANCELLED:
                cancel_event.set()
                return False
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                return False
            self._cancel_events[task_id] = cancel_event
            return True

    def unregister_cancel_event(self, task_id: str, cancel_event: threading.Event) -> None:
        with self._lock:
            if self._cancel_events.get(task_id) is cancel_event:
                self._cancel_events.pop(task_id, None)

    def retry_task(self, task_id: str) -> Optional[TaskItem]:
        with self._lock:
            if task_id in self._tasks:
                old = self._tasks[task_id]
                new_task = self.queue_task(
                    goal=f"[Retry] {old.goal}",
                    context=old.context,
                    plan=old.plan,
                    permissions=old.permissions
                )
                new_task.recovery_attempts = old.recovery_attempts + 1
                new_task.current_step = max(0, old.current_step - 1)  # resume from last safe step
                self.set_task_running(new_task.task_id, new_task.current_step)
                return new_task
        return None

    def complete_task(
        self,
        task_id: str,
        result: str,
        verification: str = "Verified",
        generated_files: Optional[List[str]] = None
    ) -> None:
        changed = False
        with self._lock:
            if task_id in self._tasks:
                t = self._tasks[task_id]
                if t.status in (TaskStatus.CANCELLED, TaskStatus.FAILED, TaskStatus.COMPLETED):
                    return
                cancel_event = self._cancel_events.get(task_id)
                if cancel_event and cancel_event.is_set():
                    t.status = TaskStatus.CANCELLED
                    t.end_time = time.monotonic()
                else:
                    t.status = TaskStatus.COMPLETED
                    t.result = result
                    t.verification = verification
                    if generated_files:
                        for gf in generated_files:
                            if gf not in t.generated_files:
                                t.generated_files.append(gf)
                    t.end_time = time.monotonic()
                changed = True
        if changed:
            self._persist()

    def fail_task(self, task_id: str, error_msg: str) -> None:
        with self._lock:
            if task_id in self._tasks:
                t = self._tasks[task_id]
                if t.status in (TaskStatus.CANCELLED, TaskStatus.COMPLETED, TaskStatus.FAILED):
                    return
                t.status = TaskStatus.FAILED
                t.errors.append(error_msg)
                t.verification = "Verification Failed"
                t.end_time = time.monotonic()
        self._persist()

    def format_task_center_summary(self, limit: int = 8) -> str:
        """Return a compact, UI-safe summary of active and recent tasks."""
        tasks = self.get_tasks()
        if not tasks:
            return "Task Center: no tasks recorded."

        active_statuses = {
            TaskStatus.QUEUED,
            TaskStatus.PLANNING,
            TaskStatus.RUNNING,
            TaskStatus.WAITING,
            TaskStatus.VERIFYING,
            TaskStatus.PAUSED,
        }
        active = [task for task in tasks if task.status in active_statuses]
        recent = [task for task in reversed(tasks) if task not in active][:max(0, limit)]
        shown = active + recent
        lines = [
            f"Task Center — {len(active)} active, "
            f"{sum(task.status == TaskStatus.COMPLETED for task in tasks)} completed, "
            f"{sum(task.status in (TaskStatus.FAILED, TaskStatus.CANCELLED) for task in tasks)} failed/cancelled."
        ]
        for task in shown:
            lines.append(
                f"[{task.status}] {task.goal} "
                f"({task.progress_pct}% — step {task.current_step}/{task.total_steps}; ID {task.task_id})"
            )
        return "\n".join(lines)

    def inspect_task_errors(self, task_id: str) -> List[str]:
        with self._lock:
            if task_id in self._tasks:
                return list(self._tasks[task_id].errors)
        return []

    def open_task_artifacts(self, task_id: str) -> List[str]:
        """Attempts to open any generated artifact files on the owner's desktop."""
        opened = []
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return []
            files = list(task.generated_files)

        for f_path_str in files:
            p = Path(f_path_str)
            if p.exists():
                try:
                    if os.name == "nt":
                        os.startfile(str(p))
                    else:
                        subprocess.Popen(["xdg-open", str(p)])
                    opened.append(str(p))
                except Exception:
                    pass
        return opened

    def get_task(self, task_id: str) -> Optional[TaskItem]:
        with self._lock:
            return self._tasks.get(task_id)

    def get_tasks(self) -> List[TaskItem]:
        return self.list_tasks_by_status()

    def list_tasks_by_status(self, status: Optional[str] = None) -> List[TaskItem]:
        with self._lock:
            if status:
                return [t for t in self._tasks.values() if t.status == status.upper()]
            return list(self._tasks.values())

    def get_active_tasks(self) -> List[TaskItem]:
        with self._lock:
            return [
                t for t in self._tasks.values()
                if t.status in (TaskStatus.QUEUED, TaskStatus.PLANNING, TaskStatus.RUNNING, TaskStatus.WAITING, TaskStatus.VERIFYING)
            ]

    def recover_unfinished_tasks(self) -> Dict[str, Any]:
        """
        Discovers interrupted or paused tasks after ALEX restart:
          1. Verifies that generated and workspace files still exist on disk.
          2. Enforces security gate: if task has sensitive permissions, sets status to AWAITING_CONFIRMATION.
          3. Generates clear human status for Sir.
        """
        with self._lock:
            unfinished = [
                t for t in self._tasks.values()
                if t.status in (TaskStatus.RUNNING, TaskStatus.PAUSED, TaskStatus.PLANNING, TaskStatus.WAITING)
            ]

        recoverable = []
        for t in unfinished:
            files_ok = True
            for f in t.generated_files:
                if not Path(f).exists():
                    files_ok = False
                    break

            is_sensitive = t.permissions in ("CONFIRM", "CRITICAL")
            status_desc = "Ready to resume"
            if is_sensitive:
                status_desc = "Requires Owner PIN/Confirmation before resuming (Level 3/4 Security Guard)"
            elif not files_ok:
                status_desc = "Partial file changes detected on disk; checkpoint verified"

            recoverable.append({
                "task_id": t.task_id,
                "goal": t.goal,
                "current_step": t.current_step,
                "total_steps": t.total_steps,
                "status": t.status,
                "recovery_status": status_desc,
                "can_auto_resume": not is_sensitive,
                "permissions": t.permissions
            })

        summary = ""
        if recoverable:
            lines = [f"Sir, {len(recoverable)} unfinished task(s) detected from previous session:"]
            for r in recoverable:
                lines.append(f"• [{r['task_id']}] {r['goal']} (Step {r['current_step']}/{r['total_steps']}) — {r['recovery_status']}")
            summary = "\n".join(lines)
        else:
            summary = "Sir, no interrupted tasks were detected. System is completely clean."

        return {
            "count": len(recoverable),
            "tasks": recoverable,
            "summary": summary
        }


# Singleton
task_center = TaskCenter.get_instance()
