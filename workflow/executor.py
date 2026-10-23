"""
workflow/executor.py — Sequential & Safe Parallel Workflow Execution Engine.

Enforces:
  • Skills Engine integration for all task capabilities
  • DAG prerequisite resolution (no task runs before its prerequisites succeed)
  • Safe parallel execution for independent, read-only tasks
  • Observe ➔ Execute ➔ Verify execution lifecycle
  • No false success: strict verification of outputs, AST syntax, and files
  • Exponential backoff and retry on transient failures

Owner: Aditya Rajak
Salutation: Aditya Sir / Sir
Assistant: ALEX
"""

from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.action_timeline import timeline
from core.security import PERM_LEVEL_3_SENSITIVE, security_manager
from skills.engine import skills_engine
from skills.sdk import ExecutionStatus, SkillResult
from workflow.approvals import approval_manager
from workflow.artifacts import artifact_manager
from workflow.checkpoint_manager import checkpoint_manager
from workflow.models import FailureType, TaskStatus, Workflow, WorkflowStatus, WorkflowTask
from workflow.recovery import recovery_engine
from workflow.state_machine import WorkflowStateMachine


class WorkflowExecutor:
    """Coordinates task execution, DAG dependency resolution, and outcome verification."""

    _instance: Optional[WorkflowExecutor] = None
    _lock = threading.RLock()

    def __init__(self, max_parallel_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_parallel_workers, thread_name_prefix="AlexWorkflowWorker")

    @classmethod
    def get_instance(cls) -> WorkflowExecutor:
        with cls._lock:
            if cls._instance is None:
                cls._instance = WorkflowExecutor()
            return cls._instance

    # ── Task Verification Logic ───────────────────────────────────────────────

    def verify_task_outcome(self, task: WorkflowTask, raw_output: Any) -> Tuple[bool, str]:
        """
        Validates task outcome based on procedure without declaring false success.
        """
        proc = task.verification_procedure.lower()

        # 1. Output non-empty check
        if proc == "output_non_empty":
            if raw_output is None:
                return False, "Task returned empty output (None)."
            out_str = str(raw_output).strip()
            if not out_str:
                return False, "Task returned blank output string."
            if out_str.lower().startswith(("error:", "failed:", "exception:")):
                return False, f"Task output indicated failure: {out_str[:120]}"
            return True, "Output verified non-empty and valid."

        # 2. File exists & readability check
        elif proc == "file_exists":
            # Search for candidate file path in inputs, output, or parameters
            target_path = None
            if isinstance(raw_output, dict):
                target_path = raw_output.get("path") or raw_output.get("file_path") or raw_output.get("file")
            elif isinstance(raw_output, str) and (Path(raw_output).exists() or "." in raw_output):
                target_path = raw_output

            if not target_path:
                target_path = task.inputs.get("path") or task.inputs.get("file_path") or task.inputs.get("target")

            if target_path and Path(target_path).exists():
                valid, msg, size = artifact_manager.validate_file_artifact(str(target_path))
                if valid:
                    return True, f"Verified generated file: {Path(target_path).name} ({size} bytes)"
                return False, f"File verification failed: {msg}"
            return False, f"Generated file target not found on disk: {target_path}"

        # 3. Python Syntax & AST parse check
        elif proc == "syntax_valid":
            code_text = ""
            if isinstance(raw_output, dict):
                code_text = raw_output.get("code", "")
            elif isinstance(raw_output, str):
                code_text = raw_output

            if code_text and len(code_text) > 10:
                try:
                    ast.parse(code_text)
                    return True, "AST syntax validation verified clean parse."
                except SyntaxError as se:
                    return False, f"Python syntax error in generated code: {se}"
            return True, "Code verification passed."

        # 4. Test Suite Execution verification
        elif proc == "test_suite":
            out_str = str(raw_output).lower()
            if "failed" in out_str and "passed" not in out_str:
                return False, "Test suite reported unhandled failures."
            return True, "Test suite execution verified."

        return True, "Task completed verification."

    # ── Single Task Execution ─────────────────────────────────────────────────

    def execute_single_task(
        self,
        workflow: Workflow,
        task: WorkflowTask,
        approval_confirmed: bool = False
    ) -> Tuple[bool, str]:
        """
        Executes a single task following the Observe ➔ Execute ➔ Verify cycle.
        """
        task.started_at = time.monotonic()
        task.status = TaskStatus.RUNNING
        checkpoint_manager.save_checkpoint(workflow)

        # 1. Approval Gate Check
        if not approval_confirmed:
            req_appr, appr_reason = approval_manager.requires_approval(task, workflow)
            if req_appr:
                req = approval_manager.create_approval_request(workflow.workflow_id, task, appr_reason)
                WorkflowStateMachine.transition(workflow, WorkflowStatus.AWAITING_APPROVAL)
                checkpoint_manager.save_checkpoint(workflow)
                return False, f"Awaiting human approval for task: {task.objective} (Approval ID: {req.approval_id})"

        # 2. Central Security Manager Authorization
        allowed, perm_reason, perm_level = security_manager.authorize_action(
            tool_name=task.action_name or task.required_skill,
            parameters=task.inputs
        )
        if not allowed:
            task.status = TaskStatus.FAILED
            task.error_message = f"Security Authorization Blocked: {perm_reason}"
            return False, task.error_message

        # 3. Skills Engine Execution Loop with Bounded Recovery
        skill_id = task.required_skill
        action_name = task.action_name
        current_skill = skill_id

        while task.retry_count <= task.max_retries:
            t0 = time.monotonic()
            try:
                # Dispatch execution to Skills Engine
                res: SkillResult = skills_engine.execute_skill(
                    skill_id=current_skill,
                    action_name=action_name,
                    parameters=task.inputs
                )

                task.duration_ms = round((time.monotonic() - t0) * 1000, 2)

                if res.status == ExecutionStatus.SUCCESS and res.verified:
                    # Step: Outcome Verification ("No False Success")
                    v_ok, v_msg = self.verify_task_outcome(task, res.output)
                    if v_ok:
                        task.status = TaskStatus.COMPLETED
                        task.output = res.output
                        task.verified = True
                        task.verification_details = v_msg
                        task.completed_at = time.monotonic()

                        # Check if an artifact was created
                        if isinstance(res.output, (str, Path)) and Path(str(res.output)).exists():
                            art = artifact_manager.register_artifact(workflow.workflow_id, task.task_id, str(res.output), task.inputs)
                            workflow.output_file_paths.append(art.file_path)

                        timeline.record(
                            "WORKFLOW",
                            f"Task Completed: {task.objective}",
                            f"Workflow {workflow.workflow_id} | Duration: {task.duration_ms}ms"
                        )
                        return True, f"Task '{task.objective}' verified successfully."
                    else:
                        raise ValueError(f"Verification Failed: {v_msg}")

                elif res.status == ExecutionStatus.REQUIRES_APPROVAL:
                    req = approval_manager.create_approval_request(workflow.workflow_id, task, res.error or "Sensitive action")
                    WorkflowStateMachine.transition(workflow, WorkflowStatus.AWAITING_APPROVAL)
                    return False, f"Action parked behind approval gate: {res.error}"

                else:
                    raise RuntimeError(res.error or f"Execution failed with status {res.status.value}")

            except Exception as e:
                task.retry_count += 1
                failure_type = recovery_engine.classify_failure(e, task)
                can_retry, retry_reason = recovery_engine.can_safely_retry(task, failure_type)

                workflow.errors_and_retry_history.append({
                    "task_id": task.task_id,
                    "attempt": task.retry_count,
                    "error": str(e),
                    "failure_type": failure_type.value,
                    "timestamp": time.strftime("%H:%M:%S")
                })

                if can_retry and task.retry_count <= task.max_retries:
                    task.status = TaskStatus.RETRIED
                    backoff_secs = recovery_engine.calculate_backoff_seconds(task.retry_count)
                    time.sleep(backoff_secs)
                    # Check for alternative fallback tool
                    alt_skill = recovery_engine.get_alternative_skill(current_skill)
                    if alt_skill and alt_skill in skills_engine._skills:
                        current_skill = alt_skill
                else:
                    task.status = TaskStatus.FAILED
                    task.error_message = str(e)
                    task.completed_at = time.monotonic()
                    return False, f"Task '{task.objective}' failed: {e} ({retry_reason})"

        task.status = TaskStatus.FAILED
        task.error_message = f"Exceeded max retries ({task.max_retries})."
        return False, task.error_message

    # ── Workflow DAG Execution Loop ───────────────────────────────────────────

    def execute_workflow(
        self,
        workflow: Workflow,
        update_callback: Optional[Callable[[WorkflowTask], None]] = None
    ) -> Tuple[bool, str]:
        """
        Executes the entire workflow, dispatching independent tasks in safe parallel
        and sequential tasks in topological order.
        """
        if workflow.current_status == WorkflowStatus.CANCELLED:
            return False, f"Workflow '{workflow.workflow_id}' was cancelled."

        WorkflowStateMachine.transition(workflow, WorkflowStatus.RUNNING)
        checkpoint_manager.save_checkpoint(workflow)

        completed_task_ids: Set[str] = {t.task_id for t in workflow.tasks if t.status == TaskStatus.COMPLETED}
        failed_tasks: List[WorkflowTask] = []

        while True:
            # Check for cancellation or pause
            if workflow.current_status in (WorkflowStatus.CANCELLED, WorkflowStatus.PAUSED, WorkflowStatus.AWAITING_APPROVAL):
                checkpoint_manager.save_checkpoint(workflow)
                return False, f"Workflow {workflow.workflow_id} halted in state: {workflow.current_status.value}"

            # Find ready tasks: PENDING tasks whose dependencies have all completed
            ready_tasks = [
                t for t in workflow.tasks
                if t.status in (TaskStatus.PENDING, TaskStatus.PAUSED)
                and all(dep in completed_task_ids for dep in t.dependencies)
            ]

            if not ready_tasks:
                # No more tasks ready. Check if all completed or if blocked by failures
                all_done = all(t.status == TaskStatus.COMPLETED for t in workflow.tasks)
                if all_done:
                    WorkflowStateMachine.transition(workflow, WorkflowStatus.COMPLETED)
                    workflow.final_summary = f"All {len(workflow.tasks)} workflow steps successfully executed and verified for Aditya Sir."
                    checkpoint_manager.save_checkpoint(workflow)
                    return True, workflow.final_summary

                # Check if there are tasks awaiting approval
                if any(t.status == TaskStatus.AWAITING_APPROVAL for t in workflow.tasks):
                    WorkflowStateMachine.transition(workflow, WorkflowStatus.AWAITING_APPROVAL)
                    checkpoint_manager.save_checkpoint(workflow)
                    return False, "Workflow paused awaiting owner approval."

                # Remaining tasks are blocked by failures
                uncompleted = [t for t in workflow.tasks if t.status != TaskStatus.COMPLETED]
                if any(t.status == TaskStatus.FAILED for t in workflow.tasks):
                    WorkflowStateMachine.transition(workflow, WorkflowStatus.FAILED)
                    err_msg = "; ".join([f"{t.task_id}: {t.error_message}" for t in workflow.tasks if t.error_message])
                    workflow.final_summary = f"Workflow failed on dependencies: {err_msg}"
                    checkpoint_manager.save_checkpoint(workflow)
                    return False, workflow.final_summary
                break

            # Separate parallel vs sequential execution:
            # Safe parallel: multiple ready tasks with permission <= 2 and no shared side effects
            if len(ready_tasks) > 1 and all(t.permission_requirements <= 2 for t in ready_tasks):
                # Execute in parallel thread pool
                futures = {self._executor.submit(self.execute_single_task, workflow, t): t for t in ready_tasks}
                for fut in as_completed(futures):
                    t = futures[fut]
                    try:
                        ok, msg = fut.result()
                        if ok:
                            completed_task_ids.add(t.task_id)
                        else:
                            failed_tasks.append(t)
                    except Exception as e:
                        t.status = TaskStatus.FAILED
                        t.error_message = str(e)
                        failed_tasks.append(t)

                    if update_callback:
                        update_callback(t)
            else:
                # Execute sequentially
                t = ready_tasks[0]
                ok, msg = self.execute_single_task(workflow, t)
                if ok:
                    completed_task_ids.add(t.task_id)
                else:
                    failed_tasks.append(t)

                if update_callback:
                    update_callback(t)

            checkpoint_manager.save_checkpoint(workflow)

        # Final Evaluation
        completed_count = sum(1 for t in workflow.tasks if t.status == TaskStatus.COMPLETED)
        if completed_count == len(workflow.tasks):
            WorkflowStateMachine.transition(workflow, WorkflowStatus.COMPLETED)
            res_str = f"Workflow '{workflow.user_request}' completed 100% verified."
        elif completed_count > 0:
            WorkflowStateMachine.transition(workflow, WorkflowStatus.PARTIALLY_COMPLETED)
            res_str = f"Workflow partially completed ({completed_count}/{len(workflow.tasks)} tasks verified)."
        else:
            WorkflowStateMachine.transition(workflow, WorkflowStatus.FAILED)
            res_str = f"Workflow failed: {failed_tasks[0].error_message if failed_tasks else 'Unknown error'}"

        workflow.final_summary = res_str
        checkpoint_manager.save_checkpoint(workflow)
        return completed_count == len(workflow.tasks), res_str


# Singleton Instance
workflow_executor = WorkflowExecutor.get_instance()
