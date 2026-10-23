"""
workflow/models.py — Data Models & Schemas for ALEX Multi-Step Workflow Orchestrator.

Defines:
  • WorkflowStatus: Explicit 12-state state machine enum
  • TaskStatus: Individual task lifecycle enum
  • FailureType: Categorization of execution failures
  • WorkflowTask: Granular, verifiable task unit in DAG
  • ArtifactRecord: Metadata and verification records for generated outputs
  • ApprovalRequest: Parameter-bound human authorization gate
  • Workflow: Top-level persistent workflow record

Owner: Aditya Rajak
Salutation: Aditya Sir / Sir
Assistant: ALEX
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class WorkflowStatus(str, Enum):
    CREATED             = "CREATED"
    PLANNING            = "PLANNING"
    AWAITING_APPROVAL   = "AWAITING_APPROVAL"
    READY               = "READY"
    RUNNING             = "RUNNING"
    PAUSED              = "PAUSED"
    RECOVERING          = "RECOVERING"
    VERIFYING           = "VERIFYING"
    COMPLETED           = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED              = "FAILED"
    CANCELLED           = "CANCELLED"


class TaskStatus(str, Enum):
    PENDING           = "PENDING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    RUNNING           = "RUNNING"
    COMPLETED         = "COMPLETED"
    FAILED            = "FAILED"
    SKIPPED           = "SKIPPED"
    RETRIED           = "RETRIED"
    PAUSED            = "PAUSED"


class FailureType(str, Enum):
    TRANSIENT           = "TRANSIENT"            # Temporary lock, busy port, network blip (retryable)
    PERMANENT           = "PERMANENT"            # Invalid syntax, missing file, logic error
    PERMISSION_DENIED   = "PERMISSION_DENIED"    # Blocked by Central Security Manager
    DEPENDENCY_MISSING  = "DEPENDENCY_MISSING"   # Required Python package or binary missing
    VERIFICATION_FAILED = "VERIFICATION_FAILED"  # File empty, checksum mismatch, test failure
    TIMEOUT             = "TIMEOUT"              # Exceeded step timeout seconds


@dataclass
class ArtifactRecord:
    artifact_id: str
    file_path: str
    file_type: str
    workflow_id: str
    task_id: str
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    file_size_bytes: int = 0
    validation_status: str = "PENDING"
    source_inputs: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ApprovalRequest:
    approval_id: str
    workflow_id: str
    task_id: str
    action_name: str
    description: str
    risk_level: int = 3  # Level 1=Read, 2=Normal, 3=Sensitive, 4=Restricted
    parameters: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    status: str = "PENDING"  # PENDING, APPROVED, REJECTED
    decision_note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowTask:
    task_id: str
    objective: str
    inputs: Dict[str, Any]
    expected_output: str
    required_skill: str
    action_name: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)  # Prerequisites task_ids
    permission_requirements: int = 2                       # 1=Read, 2=Normal, 3=Sensitive, 4=Restricted
    timeout_seconds: int = 45
    verification_procedure: str = "output_non_empty"       # file_exists, syntax_valid, output_non_empty, test_suite
    recovery_strategy: str = "retry_exponential"          # retry_exponential, alternative_tool, rollback, ask_owner
    is_irreversible: bool = False                         # If True, never automatically retried without approval
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    output: Any = None
    error_message: Optional[str] = None
    verified: bool = False
    verification_details: str = ""
    duration_ms: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> WorkflowTask:
        d = dict(data)
        if "status" in d and isinstance(d["status"], str):
            try:
                d["status"] = TaskStatus(d["status"])
            except ValueError:
                d["status"] = TaskStatus.PENDING
        return cls(**d)


@dataclass
class Workflow:
    workflow_id: str
    user_request: str
    desired_outcome: str
    creation_time: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    current_status: WorkflowStatus = WorkflowStatus.CREATED
    tasks: List[WorkflowTask] = field(default_factory=list)
    current_step_index: int = 0
    output_file_paths: List[str] = field(default_factory=list)
    errors_and_retry_history: List[Dict[str, Any]] = field(default_factory=list)
    verification_results: Dict[str, Any] = field(default_factory=dict)
    cancellation_reason: Optional[str] = None
    final_summary: str = ""
    project_id: Optional[str] = None
    can_resume_on_restart: bool = True
    start_time: float = field(default_factory=time.monotonic)
    end_time: Optional[float] = None

    @property
    def progress_pct(self) -> int:
        if self.current_status == WorkflowStatus.COMPLETED:
            return 100
        if not self.tasks:
            return 0
        completed = sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED)
        return int((completed / len(self.tasks)) * 100)

    @property
    def is_terminal(self) -> bool:
        return self.current_status in (
            WorkflowStatus.COMPLETED,
            WorkflowStatus.PARTIALLY_COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED
        )

    @property
    def elapsed_seconds(self) -> float:
        if self.end_time is not None:
            return round(self.end_time - self.start_time, 2)
        return round(time.monotonic() - self.start_time, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "user_request": self.user_request,
            "desired_outcome": self.desired_outcome,
            "creation_time": self.creation_time,
            "current_status": self.current_status.value,
            "progress_pct": self.progress_pct,
            "tasks": [t.to_dict() for t in self.tasks],
            "current_step_index": self.current_step_index,
            "output_file_paths": list(self.output_file_paths),
            "errors_and_retry_history": list(self.errors_and_retry_history),
            "verification_results": dict(self.verification_results),
            "cancellation_reason": self.cancellation_reason,
            "final_summary": self.final_summary,
            "project_id": self.project_id,
            "can_resume_on_restart": self.can_resume_on_restart,
            "elapsed_seconds": self.elapsed_seconds,
            "is_terminal": self.is_terminal
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Workflow:
        tasks = [WorkflowTask.from_dict(t) for t in data.get("tasks", [])]
        st_val = data.get("current_status", WorkflowStatus.CREATED.value)
        try:
            status = WorkflowStatus(st_val)
        except ValueError:
            status = WorkflowStatus.CREATED

        wf = cls(
            workflow_id=data["workflow_id"],
            user_request=data["user_request"],
            desired_outcome=data.get("desired_outcome", ""),
            creation_time=data.get("creation_time", time.strftime("%Y-%m-%d %H:%M:%S")),
            current_status=status,
            tasks=tasks,
            current_step_index=data.get("current_step_index", 0),
            output_file_paths=data.get("output_file_paths", []),
            errors_and_retry_history=data.get("errors_and_retry_history", []),
            verification_results=data.get("verification_results", {}),
            cancellation_reason=data.get("cancellation_reason"),
            final_summary=data.get("final_summary", ""),
            project_id=data.get("project_id"),
            can_resume_on_restart=data.get("can_resume_on_restart", True)
        )
        return wf

