"""
workflow/approvals.py — Parameter-Bound Human Approval Gates for Sensitive Operations.

Ensures no high-risk, sensitive, or irreversible actions execute autonomously:
  • Level 3 Sensitive operations
  • Destructive file modifications or deletions
  • Irreversible external transmissions
  • Autonomy level policy enforcement

Owner: Aditya Rajak
Salutation: Aditya Sir / Sir
Assistant: ALEX
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from core.security import PERM_LEVEL_3_SENSITIVE, security_manager
from core.task_center import AutonomyLevel, task_center
from workflow.models import ApprovalRequest, TaskStatus, Workflow, WorkflowTask


class ApprovalManager:
    """Manages fine-grained, action-specific approval requests and decisions."""

    _instance: Optional[ApprovalManager] = None
    _lock = threading.RLock()

    def __init__(self):
        self._requests: Dict[str, ApprovalRequest] = {}

    @classmethod
    def get_instance(cls) -> ApprovalManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = ApprovalManager()
            return cls._instance

    def requires_approval(self, task: WorkflowTask, workflow: Optional[Workflow] = None) -> Tuple[bool, str]:
        """
        Determines whether a task requires explicit owner approval before execution.
        """
        # 1. Level 3 Sensitive Permissions
        if task.permission_requirements >= PERM_LEVEL_3_SENSITIVE:
            return True, f"Operation requires Level {task.permission_requirements} authorization: '{task.objective}'."

        # 2. Irreversible Actions (file deletion, remote message broadcast)
        if task.is_irreversible:
            return True, f"Action is irreversible and requires explicit confirmation: '{task.objective}'."

        # 3. Global Autonomy Settings
        autonomy = task_center.get_autonomy_level()
        if autonomy == AutonomyLevel.ASK_EVERYTHING:
            return True, "Current autonomy policy requires confirmation for all actions."

        # 4. Check action parameters for destructive keywords
        inputs_str = str(task.inputs).lower()
        if any(w in inputs_str for w in ("delete", "remove", "overwrite", "drop", "destroy", "wipe")):
            return True, f"Destructive parameter detected in task inputs: '{task.objective}'."

        return False, "Autonomous execution approved."

    def create_approval_request(
        self,
        workflow_id: str,
        task: WorkflowTask,
        reason: str
    ) -> ApprovalRequest:
        """Creates a parameter-bound approval request record."""
        with self._lock:
            appr_id = f"APPR-{int(time.time()*1000)%100000:05d}"
            req = ApprovalRequest(
                approval_id=appr_id,
                workflow_id=workflow_id,
                task_id=task.task_id,
                action_name=task.action_name or task.required_skill,
                description=f"{task.objective} (Reason: {reason})",
                risk_level=task.permission_requirements,
                parameters=dict(task.inputs),
                status="PENDING"
            )
            self._requests[appr_id] = req
            task.status = TaskStatus.AWAITING_APPROVAL
            return req

    def get_request(self, approval_id: str) -> Optional[ApprovalRequest]:
        with self._lock:
            return self._requests.get(approval_id)

    def list_pending(self, workflow_id: Optional[str] = None) -> List[ApprovalRequest]:
        with self._lock:
            out = []
            for r in self._requests.values():
                if r.status == "PENDING":
                    if not workflow_id or r.workflow_id == workflow_id:
                        out.append(r)
            return out

    def approve(self, approval_id: str, decision_note: str = "") -> Tuple[bool, str]:
        with self._lock:
            req = self._requests.get(approval_id)
            if not req:
                return False, f"Approval request '{approval_id}' not found."
            if req.status != "PENDING":
                return False, f"Request '{approval_id}' is already {req.status}."

            req.status = "APPROVED"
            req.decision_note = decision_note or "Approved by Aditya Sir."
            return True, f"Action '{req.action_name}' approved."

    def reject(self, approval_id: str, decision_note: str = "") -> Tuple[bool, str]:
        with self._lock:
            req = self._requests.get(approval_id)
            if not req:
                return False, f"Approval request '{approval_id}' not found."
            if req.status != "PENDING":
                return False, f"Request '{approval_id}' is already {req.status}."

            req.status = "REJECTED"
            req.decision_note = decision_note or "Rejected by Aditya Sir."
            return True, f"Action '{req.action_name}' rejected."


# Singleton Instance
approval_manager = ApprovalManager.get_instance()

