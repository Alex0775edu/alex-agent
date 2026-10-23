"""
workflow/state_machine.py — Explicit Workflow State Machine & Transition Rules.

Enforces:
  • 12 Explicit Workflow States
  • Valid transition matrix verification
  • Safe exception handling on illegal state transitions
  • Duplicate submission prevention for active workflows

Owner: Aditya Rajak
Salutation: Aditya Sir / Sir
Assistant: ALEX
"""

from __future__ import annotations

import hashlib
import time
from typing import Dict, List, Optional, Set, Tuple

from workflow.models import Workflow, WorkflowStatus


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal workflow state transition is attempted."""
    pass


class DuplicateWorkflowError(ValueError):
    """Raised when an identical workflow request is already actively running."""
    pass


# Strict Transition Matrix defining allowed lifecycle paths
VALID_TRANSITIONS: Dict[WorkflowStatus, Set[WorkflowStatus]] = {
    WorkflowStatus.CREATED: {
        WorkflowStatus.PLANNING,
        WorkflowStatus.READY,
        WorkflowStatus.RUNNING,
        WorkflowStatus.AWAITING_APPROVAL,
        WorkflowStatus.CANCELLED
    },
    WorkflowStatus.PLANNING: {
        WorkflowStatus.READY,
        WorkflowStatus.RUNNING,
        WorkflowStatus.AWAITING_APPROVAL,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED
    },
    WorkflowStatus.AWAITING_APPROVAL: {
        WorkflowStatus.READY,
        WorkflowStatus.RUNNING,
        WorkflowStatus.PARTIALLY_COMPLETED,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED
    },
    WorkflowStatus.READY: {
        WorkflowStatus.RUNNING,
        WorkflowStatus.PAUSED,
        WorkflowStatus.AWAITING_APPROVAL,
        WorkflowStatus.CANCELLED
    },
    WorkflowStatus.RUNNING: {
        WorkflowStatus.PAUSED,
        WorkflowStatus.RECOVERING,
        WorkflowStatus.VERIFYING,
        WorkflowStatus.COMPLETED,
        WorkflowStatus.PARTIALLY_COMPLETED,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
        WorkflowStatus.AWAITING_APPROVAL
    },
    WorkflowStatus.PAUSED: {
        WorkflowStatus.RUNNING,
        WorkflowStatus.CANCELLED
    },
    WorkflowStatus.RECOVERING: {
        WorkflowStatus.RUNNING,
        WorkflowStatus.AWAITING_APPROVAL,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED
    },
    WorkflowStatus.VERIFYING: {
        WorkflowStatus.COMPLETED,
        WorkflowStatus.PARTIALLY_COMPLETED,
        WorkflowStatus.FAILED,
        WorkflowStatus.RECOVERING
    },
    # Terminal States: can only be re-planned / retried manually
    WorkflowStatus.COMPLETED: set(),
    WorkflowStatus.PARTIALLY_COMPLETED: set(),
    WorkflowStatus.FAILED: {
        WorkflowStatus.RECOVERING,
        WorkflowStatus.PLANNING,
        WorkflowStatus.RUNNING
    },
    WorkflowStatus.CANCELLED: set(),
}


class WorkflowStateMachine:
    """Manages state transitions and guards against duplicate/invalid operations."""

    @staticmethod
    def can_transition(current: WorkflowStatus, target: WorkflowStatus) -> bool:
        """Checks if a transition between two states is valid."""
        allowed = VALID_TRANSITIONS.get(current, set())
        return target in allowed

    @classmethod
    def transition(cls, workflow: Workflow, target: WorkflowStatus, reason: str = "") -> Workflow:
        """
        Transitions a workflow to a new state if allowed, or raises InvalidStateTransitionError.
        """
        current = workflow.current_status
        if current == target:
            return workflow

        if not cls.can_transition(current, target):
            raise InvalidStateTransitionError(
                f"Cannot transition workflow '{workflow.workflow_id}' from '{current.value}' to '{target.value}'. "
                f"Allowed transitions from '{current.value}': {[s.value for s in VALID_TRANSITIONS.get(current, set())]}."
            )

        workflow.current_status = target
        if target in (
            WorkflowStatus.COMPLETED,
            WorkflowStatus.PARTIALLY_COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED
        ):
            workflow.end_time = time.monotonic()

        if target == WorkflowStatus.CANCELLED and reason:
            workflow.cancellation_reason = reason

        return workflow

    @staticmethod
    def compute_request_fingerprint(request_text: str) -> str:
        """Computes a normalized SHA-256 fingerprint of a request."""
        normalized = " ".join(request_text.lower().strip().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @classmethod
    def check_duplicate_submission(
        cls,
        new_request: str,
        active_workflows: List[Workflow]
    ) -> Tuple[bool, Optional[str]]:
        """
        Checks if an identical workflow request is already active/running.
        Returns (True, workflow_id) if duplicate found, else (False, None).
        """
        new_fp = cls.compute_request_fingerprint(new_request)
        for wf in active_workflows:
            if not wf.is_terminal:
                if cls.compute_request_fingerprint(wf.user_request) == new_fp:
                    return True, wf.workflow_id
        return False, None
