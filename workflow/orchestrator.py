"""
workflow/orchestrator.py — Central Workflow Orchestration Engine for ALEX 8.0.

Provides the master coordination layer:
  • Natural language request deconstruction into verifiable DAG workflows
  • Bounded execution, state machine transitions, and persistent checkpointing
  • Central Security Manager and Skills Engine dynamic tool invocation
  • Parameter-bound approval handling and recovery strategies
  • Seamless crash/restart recovery

Owner: Aditya Rajak
Salutation: Aditya Sir / Sir
Assistant: ALEX
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.event_bus import event_bus
from core.security import OWNER_ADDRESS
from workflow.approvals import approval_manager
from workflow.artifacts import artifact_manager
from workflow.checkpoint_manager import checkpoint_manager
from workflow.executor import workflow_executor
from workflow.models import ApprovalRequest, TaskStatus, Workflow, WorkflowStatus, WorkflowTask
from workflow.planner import workflow_planner
from workflow.recovery import recovery_engine
from workflow.state_machine import DuplicateWorkflowError, WorkflowStateMachine


class WorkflowOrchestrator:
    """Master workflow orchestration engine for autonomous multi-step operations."""

    _instance: Optional[WorkflowOrchestrator] = None
    _lock = threading.RLock()

    def __init__(self):
        self._active_threads: Dict[str, threading.Thread] = {}
        # Perform startup recovery check
        self.recover_on_startup()

    @classmethod
    def get_instance(cls) -> WorkflowOrchestrator:
        with cls._lock:
            if cls._instance is None:
                cls._instance = WorkflowOrchestrator()
            return cls._instance

    # ── Workflow Lifecycle Operations ─────────────────────────────────────────

    def submit_workflow(
        self,
        user_request: str,
        project_id: Optional[str] = None,
        auto_start: bool = True
    ) -> Workflow:
        """
        Accepts a user request, validates against duplicate submissions,
        builds a DAG plan, and optionally begins execution.
        """
        with self._lock:
            # 1. Duplicate check against active workflows
            active = [w for w in checkpoint_manager.list_workflows() if not w.is_terminal]
            is_dup, dup_id = WorkflowStateMachine.check_duplicate_submission(user_request, active)
            if is_dup and dup_id:
                raise DuplicateWorkflowError(
                    f"Identical workflow is already active: '{dup_id}'. "
                    f"Please wait for it to complete or cancel it before resubmitting."
                )

            # 2. Plan workflow
            wf = workflow_planner.plan_workflow(user_request, project_id=project_id)
            checkpoint_manager.save_checkpoint(wf)
            event_bus.publish("WORKFLOW_CREATED", {"workflow_id": wf.workflow_id, "request": user_request})

            # 3. Start execution if requested
            if auto_start:
                self.start_workflow(wf.workflow_id, background=True)

            return wf

    def start_workflow(self, workflow_id: str, background: bool = False) -> Tuple[bool, str]:
        """Starts execution of a ready or planned workflow."""
        wf = checkpoint_manager.get_workflow(workflow_id)
        if not wf:
            return False, f"Workflow '{workflow_id}' not found."

        if wf.is_terminal:
            return False, f"Workflow '{workflow_id}' is already in terminal state: {wf.current_status.value}."

        def _run_worker():
            workflow_executor.execute_workflow(wf)

        if background:
            t = threading.Thread(target=_run_worker, name=f"WFRunner-{workflow_id}", daemon=True)
            self._active_threads[workflow_id] = t
            t.start()
            return True, f"Workflow '{workflow_id}' dispatched in background."
        else:
            return workflow_executor.execute_workflow(wf)

    def pause_workflow(self, workflow_id: str) -> Tuple[bool, str]:
        """Pauses a running workflow safely between steps."""
        wf = checkpoint_manager.get_workflow(workflow_id)
        if not wf:
            return False, f"Workflow '{workflow_id}' not found."

        if wf.current_status != WorkflowStatus.RUNNING:
            return False, f"Cannot pause workflow in state '{wf.current_status.value}' (must be RUNNING)."

        WorkflowStateMachine.transition(wf, WorkflowStatus.PAUSED)
        checkpoint_manager.save_checkpoint(wf)
        event_bus.publish("WORKFLOW_PAUSED", {"workflow_id": workflow_id})
        return True, f"Workflow '{workflow_id}' paused."

    def resume_workflow(self, workflow_id: str, background: bool = True) -> Tuple[bool, str]:
        """Resumes a paused workflow."""
        wf = checkpoint_manager.get_workflow(workflow_id)
        if not wf:
            return False, f"Workflow '{workflow_id}' not found."

        if wf.current_status not in (WorkflowStatus.PAUSED, WorkflowStatus.AWAITING_APPROVAL, WorkflowStatus.READY):
            return False, f"Cannot resume workflow in state '{wf.current_status.value}'."

        WorkflowStateMachine.transition(wf, WorkflowStatus.RUNNING)
        checkpoint_manager.save_checkpoint(wf)
        event_bus.publish("WORKFLOW_RESUMED", {"workflow_id": workflow_id})

        return self.start_workflow(workflow_id, background=background)

    def cancel_workflow(self, workflow_id: str, reason: str = "") -> Tuple[bool, str]:
        """Safely cancels an active workflow."""
        wf = checkpoint_manager.get_workflow(workflow_id)
        if not wf:
            return False, f"Workflow '{workflow_id}' not found."

        if wf.is_terminal:
            return False, f"Workflow '{workflow_id}' is already terminal ({wf.current_status.value})."

        WorkflowStateMachine.transition(wf, WorkflowStatus.CANCELLED, reason=reason or "Cancelled by Aditya Sir.")
        checkpoint_manager.save_checkpoint(wf)
        event_bus.publish("WORKFLOW_CANCELLED", {"workflow_id": workflow_id, "reason": wf.cancellation_reason})
        return True, f"Workflow '{workflow_id}' cancelled."

    def retry_task(self, workflow_id: str, task_id: str, background: bool = True) -> Tuple[bool, str]:
        """Manually retries a failed task inside a workflow."""
        wf = checkpoint_manager.get_workflow(workflow_id)
        if not wf:
            return False, f"Workflow '{workflow_id}' not found."

        target_task = next((t for t in wf.tasks if t.task_id == task_id), None)
        if not target_task:
            return False, f"Task '{task_id}' not found in workflow '{workflow_id}'."

        if target_task.status != TaskStatus.FAILED:
            return False, f"Task '{task_id}' is not in FAILED state (current: {target_task.status.value})."

        target_task.status = TaskStatus.PENDING
        target_task.error_message = None
        target_task.retry_count = 0

        if wf.current_status in (WorkflowStatus.FAILED, WorkflowStatus.PARTIALLY_COMPLETED):
            WorkflowStateMachine.transition(wf, WorkflowStatus.RUNNING)

        checkpoint_manager.save_checkpoint(wf)
        return self.start_workflow(workflow_id, background=background)

    def approve_task(self, approval_id: str, note: str = "") -> Tuple[bool, str]:
        """Approves a parked approval gate and resumes the workflow."""
        req = approval_manager.get_request(approval_id)
        if not req:
            return False, f"Approval request '{approval_id}' not found."

        ok, msg = approval_manager.approve(approval_id, decision_note=note)
        if not ok:
            return False, msg

        wf = checkpoint_manager.get_workflow(req.workflow_id)
        if wf:
            task = next((t for t in wf.tasks if t.task_id == req.task_id), None)
            if task:
                task.status = TaskStatus.PENDING
            # Resume workflow
            self.resume_workflow(wf.workflow_id, background=True)

        return True, f"Approval granted. Resuming workflow {req.workflow_id}."

    def reject_task(self, approval_id: str, note: str = "") -> Tuple[bool, str]:
        """Rejects a parked approval gate and cancels the task."""
        req = approval_manager.get_request(approval_id)
        if not req:
            return False, f"Approval request '{approval_id}' not found."

        ok, msg = approval_manager.reject(approval_id, decision_note=note)
        if not ok:
            return False, msg

        wf = checkpoint_manager.get_workflow(req.workflow_id)
        if wf:
            task = next((t for t in wf.tasks if t.task_id == req.task_id), None)
            if task:
                task.status = TaskStatus.SKIPPED
                task.error_message = f"Rejected by Aditya Sir: {note or 'Authorization denied.'}"
            WorkflowStateMachine.transition(wf, WorkflowStatus.PARTIALLY_COMPLETED)
            checkpoint_manager.save_checkpoint(wf)

        return True, f"Approval rejected for workflow {req.workflow_id}."

    # ── Queries & Inspection ──────────────────────────────────────────────────

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        return checkpoint_manager.get_workflow(workflow_id)

    def list_workflows(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return [w.to_dict() for w in checkpoint_manager.list_workflows(status=status)]

    def recover_on_startup(self) -> List[Workflow]:
        """Restores interrupted workflows from previous sessions."""
        return checkpoint_manager.recover_unfinished_workflows()


# Singleton Instance
workflow_orchestrator = WorkflowOrchestrator.get_instance()

