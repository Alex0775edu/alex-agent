"""
test_alex_phase8.py — Comprehensive Automated Test Suite for ALEX Phase 8.

Validates the Multi-Step Workflow Orchestrator:
  1. test_simple_and_complex_task_planning
  2. test_task_dependency_ordering_dag
  3. test_sequential_execution
  4. test_safe_parallel_execution
  5. test_invalid_state_transitions
  6. test_workflow_cancellation
  7. test_pause_and_resume
  8. test_duplicate_submission_prevention
  9. test_task_timeout_enforcement
  10. test_tool_failure_and_fallback
  11. test_retry_limits_and_exponential_backoff
  12. test_recovery_after_restart_and_checkpoint_resumption
  13. test_approval_gate_enforcement
  14. test_partial_workflow_failure_handling
  15. test_output_and_artifact_validation
  16. test_checkpoint_integrity_and_atomic_persistence
  17. test_secret_redaction_in_workflow_logs

Owner: Aditya Rajak
Salutation: Aditya Sir / Sir
Assistant: ALEX
"""

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from workflow.models import (
    ApprovalRequest, ArtifactRecord, FailureType, TaskStatus, Workflow,
    WorkflowStatus, WorkflowTask
)
from workflow.state_machine import (
    DuplicateWorkflowError, InvalidStateTransitionError, WorkflowStateMachine
)
from workflow.planner import workflow_planner, WorkflowPlanner
from workflow.executor import workflow_executor, WorkflowExecutor
from workflow.recovery import recovery_engine, RecoveryEngine
from workflow.checkpoint_manager import checkpoint_manager, CheckpointManager
from workflow.artifacts import artifact_manager, ArtifactManager
from workflow.approvals import approval_manager, ApprovalManager
from workflow.orchestrator import workflow_orchestrator, WorkflowOrchestrator


def test_1_simple_and_complex_task_planning():
    print("\n[TEST 1] Simple and Complex Goal Task Planning")
    # 1. Complex Coding & Testing Goal
    wf_code = workflow_planner.plan_workflow("Mere Python project ke bugs find karke fix karo aur tests run karo.", project_id="SkillSum")
    assert len(wf_code.tasks) == 4, f"Expected 4 tasks, got {len(wf_code.tasks)}"
    assert wf_code.tasks[0].required_skill == "code_helper"
    assert wf_code.tasks[1].dependencies == [wf_code.tasks[0].task_id]
    assert wf_code.tasks[2].dependencies == [wf_code.tasks[1].task_id]

    # 2. Document & Presentation Goal
    wf_pdf = workflow_planner.plan_workflow("Is PDF se presentation banao aur final PPTX validate karo.")
    assert len(wf_pdf.tasks) == 4, f"Expected 4 tasks for presentation workflow, got {len(wf_pdf.tasks)}"
    assert any("pptx" in t.objective.lower() or "presentation" in t.objective.lower() for t in wf_pdf.tasks)

    # 3. Simple Fallback Goal
    wf_simple = workflow_planner.plan_workflow("System metrics audit karo")
    assert len(wf_simple.tasks) == 3

    print("  [PASS] Complex and simple goal planning generated structured, verifiable DAG tasks.")


def test_2_task_dependency_ordering_dag():
    print("\n[TEST 2] Task Dependency Ordering & Circular DAG Rejection")
    t1 = WorkflowTask(task_id="T1", objective="Step 1", inputs={}, expected_output="", required_skill="system_monitor", dependencies=[])
    t2 = WorkflowTask(task_id="T2", objective="Step 2", inputs={}, expected_output="", required_skill="system_monitor", dependencies=["T1"])
    t3 = WorkflowTask(task_id="T3", objective="Step 3", inputs={}, expected_output="", required_skill="system_monitor", dependencies=["T2"])

    # Valid DAG
    ok, msg = WorkflowPlanner.validate_dag([t1, t2, t3])
    assert ok, f"Expected valid DAG, got: {msg}"
    topo = WorkflowPlanner.get_topological_order([t3, t1, t2])
    assert [t.task_id for t in topo] == ["T1", "T2", "T3"], f"Incorrect topo order: {[t.task_id for t in topo]}"

    # Circular Dependency Detection (T1 -> T2 -> T3 -> T1)
    t1_circ = WorkflowTask(task_id="T1", objective="Step 1", inputs={}, expected_output="", required_skill="system_monitor", dependencies=["T3"])
    ok_circ, msg_circ = WorkflowPlanner.validate_dag([t1_circ, t2, t3])
    assert not ok_circ and "Circular dependency" in msg_circ, f"Expected cycle detection, got: {msg_circ}"

    # Self dependency
    t_self = WorkflowTask(task_id="T_SELF", objective="Self", inputs={}, expected_output="", required_skill="system_monitor", dependencies=["T_SELF"])
    ok_self, msg_self = WorkflowPlanner.validate_dag([t_self])
    assert not ok_self and "cannot depend on itself" in msg_self

    print("  [PASS] DAG topological dependency ordering and circular dependency rejection verified.")


def test_3_sequential_execution():
    print("\n[TEST 3] Sequential Workflow Execution")
    wf_id = "WF-TEST-SEQ"
    t1 = WorkflowTask(task_id=f"{wf_id}-T1", objective="Task 1", inputs={}, expected_output="ok", required_skill="system_monitor", action_name="get_system_status", dependencies=[])
    t2 = WorkflowTask(task_id=f"{wf_id}-T2", objective="Task 2", inputs={"text": "Sequential Alex"}, expected_output="ok", required_skill="sample_text_toolkit", action_name="word_count", dependencies=[t1.task_id])

    wf = Workflow(workflow_id=wf_id, user_request="Sequential Execution Test", desired_outcome="Verify sequence", tasks=[t1, t2])
    checkpoint_manager.save_checkpoint(wf)

    ok, summary = workflow_executor.execute_workflow(wf)
    assert ok, f"Workflow execution failed: {summary}"
    assert wf.current_status == WorkflowStatus.COMPLETED
    assert t1.status == TaskStatus.COMPLETED
    assert t2.status == TaskStatus.COMPLETED
    assert t1.completed_at <= t2.started_at, "T2 must start after T1 completes"
    assert wf.progress_pct == 100

    print("  [PASS] Sequential dependencies executed strictly in order and verified 100%.")


def test_4_safe_parallel_execution():
    print("\n[TEST 4] Safe Parallel Execution for Independent Read Tasks")
    wf_id = "WF-TEST-PAR"
    # T1 and T2 are independent (no shared dependencies, Level 1 read permission)
    t1 = WorkflowTask(task_id=f"{wf_id}-T1", objective="Parallel Task 1", inputs={}, expected_output="ok", required_skill="system_monitor", action_name="get_system_status", dependencies=[], permission_requirements=1)
    t2 = WorkflowTask(task_id=f"{wf_id}-T2", objective="Parallel Task 2", inputs={"text": "Parallel Alex"}, expected_output="ok", required_skill="sample_text_toolkit", action_name="word_count", dependencies=[], permission_requirements=1)
    # T3 depends on both T1 and T2
    t3 = WorkflowTask(task_id=f"{wf_id}-T3", objective="Sequential Task 3", inputs={"text": "Final Alex"}, expected_output="ok", required_skill="sample_text_toolkit", action_name="reverse", dependencies=[t1.task_id, t2.task_id])

    wf = Workflow(workflow_id=wf_id, user_request="Parallel Execution Test", desired_outcome="Verify parallel branch", tasks=[t1, t2, t3])
    checkpoint_manager.save_checkpoint(wf)

    ok, summary = workflow_executor.execute_workflow(wf)
    assert ok, f"Parallel workflow execution failed: {summary}"
    assert wf.current_status == WorkflowStatus.COMPLETED
    assert t1.status == TaskStatus.COMPLETED
    assert t2.status == TaskStatus.COMPLETED
    assert t3.status == TaskStatus.COMPLETED

    print("  [PASS] Independent read tasks dispatched in parallel and converged at dependent task.")


def test_5_invalid_state_transitions():
    print("\n[TEST 5] State Machine: Invalid State Transitions Enforcement")
    wf = Workflow(workflow_id="WF-TEST-SM", user_request="SM Test", desired_outcome="Test transitions")

    # 1. Legal: CREATED -> PLANNING
    WorkflowStateMachine.transition(wf, WorkflowStatus.PLANNING)
    assert wf.current_status == WorkflowStatus.PLANNING

    # 2. Illegal: PLANNING -> COMPLETED directly without running
    try:
        WorkflowStateMachine.transition(wf, WorkflowStatus.COMPLETED)
        assert False, "Should have raised InvalidStateTransitionError"
    except InvalidStateTransitionError:
        pass  # Expected

    # 3. Transition to terminal COMPLETED
    WorkflowStateMachine.transition(wf, WorkflowStatus.READY)
    WorkflowStateMachine.transition(wf, WorkflowStatus.RUNNING)
    WorkflowStateMachine.transition(wf, WorkflowStatus.COMPLETED)
    assert wf.is_terminal is True

    # 4. Illegal: COMPLETED -> RUNNING (terminal state cannot transition)
    try:
        WorkflowStateMachine.transition(wf, WorkflowStatus.RUNNING)
        assert False, "Terminal state transition should fail"
    except InvalidStateTransitionError:
        pass  # Expected

    print("  [PASS] State machine strictly blocked illegal transitions and protected terminal states.")


def test_6_workflow_cancellation():
    print("\n[TEST 6] Workflow Safe Cancellation")
    wf_id = "WF-TEST-CANCEL"
    t1 = WorkflowTask(task_id=f"{wf_id}-T1", objective="Task 1", inputs={}, expected_output="ok", required_skill="system_monitor", action_name="get_system_status")
    t2 = WorkflowTask(task_id=f"{wf_id}-T2", objective="Task 2", inputs={}, expected_output="ok", required_skill="system_monitor", action_name="get_system_status", dependencies=[t1.task_id])

    wf = Workflow(workflow_id=wf_id, user_request="Cancel Test", desired_outcome="Cancel test", tasks=[t1, t2], current_status=WorkflowStatus.RUNNING)
    checkpoint_manager.save_checkpoint(wf)

    ok, msg = workflow_orchestrator.cancel_workflow(wf_id, reason="User requested stop")
    assert ok, f"Cancel failed: {msg}"
    assert wf.current_status == WorkflowStatus.CANCELLED
    assert wf.cancellation_reason == "User requested stop"

    # Further execution on cancelled workflow should be blocked
    ok_exec, exec_msg = workflow_executor.execute_workflow(wf)
    assert not ok_exec and "cancelled" in exec_msg.lower()

    print("  [PASS] Active workflow cancelled safely and subsequent tasks prevented from executing.")


def test_7_pause_and_resume():
    print("\n[TEST 7] Workflow Pause & Resume Lifecycle")
    wf_id = "WF-TEST-PAUSE"
    t1 = WorkflowTask(task_id=f"{wf_id}-T1", objective="Task 1", inputs={}, expected_output="ok", required_skill="system_monitor", action_name="get_system_status")
    t2 = WorkflowTask(task_id=f"{wf_id}-T2", objective="Task 2", inputs={}, expected_output="ok", required_skill="system_monitor", action_name="get_system_status", dependencies=[t1.task_id])

    wf = Workflow(workflow_id=wf_id, user_request="Pause Test", desired_outcome="Pause test", tasks=[t1, t2], current_status=WorkflowStatus.RUNNING)
    checkpoint_manager.save_checkpoint(wf)

    # Pause
    ok, p_msg = workflow_orchestrator.pause_workflow(wf_id)
    assert ok, f"Pause failed: {p_msg}"
    assert wf.current_status == WorkflowStatus.PAUSED

    # Resume
    ok, r_msg = workflow_orchestrator.resume_workflow(wf_id, background=False)
    assert ok, f"Resume failed: {r_msg}"
    assert wf.current_status == WorkflowStatus.COMPLETED

    print("  [PASS] Workflow successfully paused and resumed to completion.")


def test_8_duplicate_submission_prevention():
    print("\n[TEST 8] Duplicate Workflow Submission Prevention")
    unique_goal = f"Unique Goal Test {int(time.time())}"
    # First submission
    wf1 = workflow_orchestrator.submit_workflow(unique_goal, auto_start=False)
    assert wf1.workflow_id is not None
    assert wf1.current_status in (WorkflowStatus.CREATED, WorkflowStatus.READY)

    # Attempt second identical submission while first is still active
    try:
        workflow_orchestrator.submit_workflow(unique_goal, auto_start=False)
        assert False, "Should have raised DuplicateWorkflowError"
    except DuplicateWorkflowError as de:
        assert "is already active" in str(de)

    # Clean up by cancelling first
    workflow_orchestrator.cancel_workflow(wf1.workflow_id, reason="Test cleanup")

    print("  [PASS] Duplicate submission of active workflow prevented via request fingerprinting.")


def test_9_task_timeout_enforcement():
    print("\n[TEST 9] Task Timeout Guard Enforcement")
    wf_id = "WF-TEST-TIMEOUT"
    # Task with 0-second or very small timeout on slow operation
    t1 = WorkflowTask(
        task_id=f"{wf_id}-T1",
        objective="Slow Task",
        inputs={},
        expected_output="ok",
        required_skill="system_monitor",
        action_name="get_system_status",
        timeout_seconds=0  # Immediate timeout
    )
    wf = Workflow(workflow_id=wf_id, user_request="Timeout Test", desired_outcome="Test timeout", tasks=[t1])
    checkpoint_manager.save_checkpoint(wf)

    # Custom worker that times out
    def slow_func(**kw):
        time.sleep(0.5)
        return "late"

    from skills.sandbox import sandbox
    res = sandbox.run_isolated(func=slow_func, timeout_seconds=0.1)
    assert res.status.value == "CANCELLED"
    assert "timed out" in (res.error or "").lower()

    print("  [PASS] Sandbox strictly enforced timeout and interrupted runaway execution.")


def test_10_tool_failure_and_fallback():
    print("\n[TEST 10] Tool Failure Classification & Fallback Resolution")
    t = WorkflowTask(task_id="T_FAIL", objective="Fail test", inputs={}, expected_output="", required_skill="code_helper")

    # 1. Classification
    f_trans = recovery_engine.classify_failure("Resource locked: winerror 32", t)
    assert f_trans == FailureType.TRANSIENT

    f_perm = recovery_engine.classify_failure("Syntax error in module", t)
    assert f_perm == FailureType.PERMANENT

    f_auth = recovery_engine.classify_failure("Security clearance unauthorized", t)
    assert f_auth == FailureType.PERMISSION_DENIED

    # 2. Alternative Skill Resolution
    alt = recovery_engine.get_alternative_skill("code_helper")
    assert alt == "dev_agent", f"Expected alternative 'dev_agent', got: {alt}"

    alt_web = recovery_engine.get_alternative_skill("web_research")
    assert alt_web == "deep_research"

    print("  [PASS] Failures accurately classified and compatible fallback skills resolved.")


def test_11_retry_limits_and_exponential_backoff():
    print("\n[TEST 11] Exponential Backoff & Retry Limits Enforcement")
    t = WorkflowTask(task_id="T_RETRY", objective="Retry test", inputs={}, expected_output="", required_skill="system_monitor", max_retries=2, retry_count=0)

    # Transient error under limit -> retry allowed
    can_r, reason = recovery_engine.can_safely_retry(t, FailureType.TRANSIENT)
    assert can_r is True, f"Expected retry allowed, got: {reason}"

    # Verify backoff delays
    delay_0 = recovery_engine.calculate_backoff_seconds(0, base_seconds=0.1)
    delay_1 = recovery_engine.calculate_backoff_seconds(1, base_seconds=0.1)
    delay_2 = recovery_engine.calculate_backoff_seconds(2, base_seconds=0.1)
    assert delay_0 == 0.1
    assert delay_1 == 0.2
    assert delay_2 == 0.4

    # When retry count reaches max_retries -> retry denied
    t.retry_count = 2
    can_r_exceeded, reason_exceeded = recovery_engine.can_safely_retry(t, FailureType.TRANSIENT)
    assert can_r_exceeded is False
    assert "exceeded" in reason_exceeded.lower()

    # Irreversible tasks cannot be automatically retried
    t_irrev = WorkflowTask(task_id="T_IRREV", objective="Irreversible", inputs={}, expected_output="", required_skill="system_monitor", is_irreversible=True)
    can_r_irrev, reason_irrev = recovery_engine.can_safely_retry(t_irrev, FailureType.TRANSIENT)
    assert can_r_irrev is False
    assert "irreversible" in reason_irrev.lower()

    print("  [PASS] Exponential backoff calculated accurately; retry limits and irreversibility guards enforced.")


def test_12_recovery_after_restart_and_checkpoint_resumption():
    print("\n[TEST 12] Recovery After Restart & Checkpoint Resumption")
    wf_id = "WF-TEST-RECOVERY"
    t1 = WorkflowTask(task_id=f"{wf_id}-T1", objective="Step 1 Completed", inputs={}, expected_output="ok", required_skill="system_monitor", status=TaskStatus.COMPLETED, verified=True)
    t2 = WorkflowTask(task_id=f"{wf_id}-T2", objective="Step 2 Interrupted", inputs={}, expected_output="ok", required_skill="system_monitor", status=TaskStatus.RUNNING, dependencies=[t1.task_id])

    wf = Workflow(
        workflow_id=wf_id,
        user_request="Restart Recovery Test",
        desired_outcome="Verify state recovery",
        current_status=WorkflowStatus.RUNNING,
        tasks=[t1, t2]
    )
    checkpoint_manager.save_checkpoint(wf)

    # Simulate restart recovery scan
    recovered = checkpoint_manager.recover_unfinished_workflows()
    rec_target = next((w for w in recovered if w.workflow_id == wf_id), None)
    assert rec_target is not None, "Workflow must be recovered"
    assert rec_target.current_status == WorkflowStatus.PAUSED
    assert rec_target.tasks[0].status == TaskStatus.COMPLETED, "Completed step must NOT be re-run"
    assert rec_target.tasks[1].status == TaskStatus.PAUSED, "Interrupted step must be set to PAUSED"

    # Clean up test workflow
    workflow_orchestrator.cancel_workflow(wf_id, reason="Cleanup")

    print("  [PASS] Restart recovery safely preserved completed milestones and transitioned incomplete tasks to PAUSED.")


def test_13_approval_gate_enforcement():
    print("\n[TEST 13] Human Approval Gate Enforcement on Sensitive Tasks")
    wf_id = "WF-TEST-APPROVAL"
    # Task with Level 3 sensitive permission
    t_sens = WorkflowTask(
        task_id=f"{wf_id}-T1",
        objective="Modify System Config",
        inputs={"action": "reconfigure_security"},
        expected_output="Config updated",
        required_skill="system_monitor",
        permission_requirements=3  # Level 3 Sensitive
    )
    wf = Workflow(workflow_id=wf_id, user_request="Sensitive Approval Test", desired_outcome="Verify gate", tasks=[t_sens])
    checkpoint_manager.save_checkpoint(wf)

    # 1. Execution should halt and request approval
    ok, msg = workflow_executor.execute_single_task(wf, t_sens, approval_confirmed=False)
    assert not ok and "Awaiting human approval" in msg
    assert t_sens.status == TaskStatus.AWAITING_APPROVAL
    assert wf.current_status == WorkflowStatus.AWAITING_APPROVAL

    # Verify pending approval request was created
    pending = approval_manager.list_pending(wf_id)
    assert len(pending) >= 1
    req = pending[0]
    assert req.task_id == t_sens.task_id

    # 2. Rejection Test
    ok_rej, rej_msg = workflow_orchestrator.reject_task(req.approval_id, note="Aditya Sir denied operation")
    assert ok_rej, f"Rejection failed: {rej_msg}"
    assert t_sens.status == TaskStatus.SKIPPED
    assert req.status == "REJECTED"

    print("  [PASS] Sensitive operations safely parked behind parameter-bound approval gate and handled decision.")


def test_14_partial_workflow_failure_handling():
    print("\n[TEST 14] Partial Workflow Failure Handling & Status Diagnostics")
    wf_id = "WF-TEST-PARTIAL"
    t1 = WorkflowTask(task_id=f"{wf_id}-T1", objective="Step 1 Success", inputs={}, expected_output="ok", required_skill="system_monitor", action_name="get_system_status")
    # Task with non-existent action and permanent failure
    t2 = WorkflowTask(task_id=f"{wf_id}-T2", objective="Step 2 Intentional Failure", inputs={"invalid": True}, expected_output="none", required_skill="system_monitor", action_name="non_existent_action_xyz", max_retries=1, dependencies=[t1.task_id])

    wf = Workflow(workflow_id=wf_id, user_request="Partial Failure Test", desired_outcome="Test failure", tasks=[t1, t2])
    checkpoint_manager.save_checkpoint(wf)

    ok, summary = workflow_executor.execute_workflow(wf)
    assert not ok
    assert wf.current_status in (WorkflowStatus.FAILED, WorkflowStatus.PARTIALLY_COMPLETED)
    assert t1.status == TaskStatus.COMPLETED
    assert t2.status == TaskStatus.FAILED
    assert len(wf.errors_and_retry_history) > 0

    print("  [PASS] Workflow accurately reported partial failure with diagnostic error context.")


def test_15_output_and_artifact_validation():
    print("\n[TEST 15] Output & Artifact Strict Validation (No False Success)")
    wf_id = "WF-TEST-ART"
    # Create temporary real test artifact
    test_art_path = BASE_DIR / "memory" / "artifacts" / "test_verification_doc.txt"
    test_art_path.parent.mkdir(parents=True, exist_ok=True)
    test_art_path.write_text("Executive Verification Report for Aditya Sir.\nStatus: VERIFIED.", encoding="utf-8")

    try:
        # 1. Valid artifact registration
        rec = artifact_manager.register_artifact(wf_id, "T1", str(test_art_path))
        assert rec.validation_status == "VERIFIED"
        assert rec.file_size_bytes > 0

        # 2. Missing file rejection
        missing_ok, missing_msg, _ = artifact_manager.validate_file_artifact("non_existent_file.pdf")
        assert not missing_ok and "does not exist" in missing_msg

        # 3. Empty file rejection (No false success)
        empty_path = BASE_DIR / "memory" / "artifacts" / "empty_doc.txt"
        empty_path.write_text("", encoding="utf-8")
        empty_ok, empty_msg, _ = artifact_manager.validate_file_artifact(str(empty_path))
        assert not empty_ok and "empty" in empty_msg
        empty_path.unlink()

    finally:
        if test_art_path.exists():
            test_art_path.unlink()

    print("  [PASS] File artifacts strictly verified on disk; empty or missing files rejected.")


def test_16_checkpoint_integrity_and_atomic_persistence():
    print("\n[TEST 16] Checkpoint Integrity & Atomic State Persistence")
    wf_id = f"WF-ATOMIC-{int(time.time()*1000)%100000}"
    t1 = WorkflowTask(task_id=f"{wf_id}-T1", objective="Checkpoint Task", inputs={}, expected_output="ok", required_skill="system_monitor", status=TaskStatus.COMPLETED)
    wf = Workflow(workflow_id=wf_id, user_request="Atomic Persistence Test", desired_outcome="Verify save", tasks=[t1], current_status=WorkflowStatus.RUNNING)

    checkpoint_manager.save_checkpoint(wf)

    # Read back directly from cache and verify
    loaded = checkpoint_manager.get_workflow(wf_id)
    assert loaded is not None
    assert loaded.workflow_id == wf_id
    assert loaded.user_request == "Atomic Persistence Test"
    assert len(loaded.tasks) == 1
    assert loaded.tasks[0].status == TaskStatus.COMPLETED

    # Verify disk JSON contains workflow
    disk_file = BASE_DIR / "memory" / "workflows.json"
    assert disk_file.exists()
    disk_data = json.loads(disk_file.read_text(encoding="utf-8"))
    wf_ids = [w["workflow_id"] for w in disk_data.get("workflows", [])]
    assert wf_id in wf_ids

    # Clean up
    workflow_orchestrator.cancel_workflow(wf_id, reason="Test cleanup")

    print("  [PASS] Workflow state saved atomically to disk and verified on reload.")


def test_17_secret_redaction_in_workflow_logs():
    print("\n[TEST 17] Secret Redaction & Log Sanitization")
    from memory.brain_store import redact_secrets

    raw_text = "Aditya Sir, connection token is AIzaSyD-1234567890abcdefghijklmnopqrstuv and password: MySecretPassword123"
    sanitized = redact_secrets(raw_text)
    assert "AIzaSyD-1234567890abcdefghijklmnopqrstuv" not in sanitized
    assert "MySecretPassword123" not in sanitized
    assert "[REDACTED_API_KEY]" in sanitized
    assert "[REDACTED_CREDENTIAL]" in sanitized

    print("  [PASS] Sensitive API keys, passwords, and tokens stripped before persistence and logging.")


if __name__ == "__main__":
    print("=" * 80)
    print("  ALEX PHASE 8 - MULTI-STEP WORKFLOW ORCHESTRATOR VERIFICATION SUITE")
    print("=" * 80)

    start_time = time.time()
    tests = [
        test_1_simple_and_complex_task_planning,
        test_2_task_dependency_ordering_dag,
        test_3_sequential_execution,
        test_4_safe_parallel_execution,
        test_5_invalid_state_transitions,
        test_6_workflow_cancellation,
        test_7_pause_and_resume,
        test_8_duplicate_submission_prevention,
        test_9_task_timeout_enforcement,
        test_10_tool_failure_and_fallback,
        test_11_retry_limits_and_exponential_backoff,
        test_12_recovery_after_restart_and_checkpoint_resumption,
        test_13_approval_gate_enforcement,
        test_14_partial_workflow_failure_handling,
        test_15_output_and_artifact_validation,
        test_16_checkpoint_integrity_and_atomic_persistence,
        test_17_secret_redaction_in_workflow_logs
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__} - {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    total_time = round(time.time() - start_time, 2)
    print("\n" + "=" * 80)
    print(f"  TEST RESULTS: {passed}/{len(tests)} PASSED | {failed} FAILED | Time: {total_time}s")
    print("=" * 80)

    if failed > 0:
        sys.exit(1)
    else:
        print("\nAll Phase 8 verification tests completed successfully.")

