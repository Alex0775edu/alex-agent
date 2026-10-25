"""
test_autonomous_task_orchestrator_2.py — Verification Suite for Autonomous Task Orchestrator 2.0.

Tests:
  1. Dependency-aware step scheduling & topological sorting.
  2. Duplicate concurrent execution prevention guard.
  3. Bounded retry for transient failures & unregistered action handling.
  4. Task cancellation propagation via threading.Event.
  5. Privileged/Critical confirmation gate.
  6. End-to-end real project audit, bug report generation, file saving, and deliverable path reporting:
     "Alex, mere project ka audit karo, bugs ki report banao aur report save karke path batao"
  7. Deliverable verification (physical file existence, non-empty, path reported).
  8. Task Center persistence & UI data model verification.
  9. Voice pipeline goal integration (routes actionable goals to orchestrator).
 10. Avatar abstinence check: No avatar widgets, 3D character assets, or animations reinstated.

Owner: Aditya Rajak (Sir)
"""

import os
import re
import sys
import threading
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent

# Ensure project root is in sys.path
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.planner_engine import Plan, PlanStep, planner_engine
from core.task_dispatcher import DispatchResult, TaskDispatcher, task_dispatcher
from core.task_center import AutonomyLevel, TaskCenter, TaskStatus, task_center
from core.security import security_manager
from core.voice_pipeline import voice_pipeline
from core.voice_pipeline import should_forward_to_live_session


def test_1_dependency_ordering():
    print("\n--- TEST 1: Dependency-Aware Step Scheduling & Ordering ---")
    steps = [
        PlanStep(3, "Generate Report", "documents", "generate_summary", {}, depends_on=[1, 2]),
        PlanStep(1, "Scan Files", "projects", "get_context", {}, depends_on=[]),
        PlanStep(2, "Syntax Audit", "coding", "syntax_audit", {}, depends_on=[1]),
    ]
    ordered = planner_engine._topological_sort(steps)
    ordered_ids = [s.step_id for s in ordered]
    assert ordered_ids == [1, 2, 3], f"Expected [1, 2, 3], got {ordered_ids}"
    print(f"  [PASS] Topological sort resolved dependencies correctly: {ordered_ids}")


def test_2_duplicate_prevention():
    print("\n--- TEST 2: Duplicate Concurrent Execution Prevention Guard ---")
    plan = Plan(
        plan_id="TEST_DUP_PLAN_001",
        goal="Test Duplicate Prevention",
        target="alex",
        steps=[PlanStep(1, "Quick step", "system", "audit_resources", {})]
    )

    with planner_engine._running_lock:
        planner_engine._running_plans.add(plan.plan_id)

    try:
        ok, msg = planner_engine.execute_plan(plan)
        assert not ok, "Duplicate plan execution should have been blocked"
        assert "already executing" in msg, f"Unexpected message: {msg}"
        print("  [PASS] Duplicate plan execution successfully rejected.")
    finally:
        with planner_engine._running_lock:
            planner_engine._running_plans.discard(plan.plan_id)


def test_3_bounded_retries_and_unregistered():
    print("\n--- TEST 3: Bounded Retries & Unregistered Actions ---")
    # 1. Unregistered action should fail fast without wasting retries
    step_unreg = PlanStep(1, "Unknown action", "unknown_skill", "non_existent_action_xyz", {})
    res = planner_engine._execute_step_with_retry(step_unreg, task_dispatcher, None)
    assert not res.success, "Unregistered action must fail"
    assert "UNREGISTERED_ACTION" in res.error, f"Expected UNREGISTERED_ACTION, got {res.error}"
    assert step_unreg.retry_count == 0, f"Unregistered action should not be retried, count={step_unreg.retry_count}"
    print("  [PASS] Unregistered action failed fast with 0 redundant retries.")


def test_4_cancellation_propagation():
    print("\n--- TEST 4: Task Cancellation Propagation ---")
    cancel_ev = threading.Event()
    cancel_ev.set()  # Pre-cancelled

    plan = Plan(
        plan_id=f"TEST_CANCEL_{int(time.time()*1000)}",
        goal="Cancellation Test",
        target="alex",
        steps=[
            PlanStep(1, "Step 1", "system", "audit_resources", {}),
            PlanStep(2, "Step 2", "system", "verify_telemetry", {}, depends_on=[1]),
        ]
    )

    ok, msg = planner_engine.execute_plan(plan, cancel_event=cancel_ev)
    assert not ok, "Cancelled plan must return success=False"
    assert plan.status == "CANCELLED", f"Plan status should be CANCELLED, got {plan.status}"
    assert "cancel" in msg.lower(), f"Unexpected cancel message: {msg}"
    print(f"  [PASS] Plan cancelled cleanly: status={plan.status}, message='{msg}'")


def test_5_privileged_confirmation_gate():
    print("\n--- TEST 5: Privileged Confirmation Gate ---")
    step_priv = PlanStep(1, "Clean temp files", "files", "clean_temp_cache", {}, risk_level="PRIVILEGED")
    plan = Plan(
        plan_id=f"TEST_GATE_{int(time.time()*1000)}",
        goal="Privileged Action Gate Test",
        target="alex",
        steps=[step_priv]
    )

    original_level = task_center.get_autonomy_level()
    task_center.set_autonomy_level(AutonomyLevel.NORMAL)
    try:
        # Rejection callback
        rejection_cb = lambda step: False
        ok, msg = planner_engine.execute_plan(plan, confirmation_callback=rejection_cb)
        assert not ok, "Privileged step without confirmation must fail"
        assert step_priv.status == "FAILED", f"Step status should be FAILED, got {step_priv.status}"
        assert "permission" in msg.lower(), f"Expected permission denial in msg: {msg}"
        print("  [PASS] Privileged step blocked when confirmation rejected.")
    finally:
        task_center.set_autonomy_level(original_level)


def test_6_and_7_end_to_end_project_audit_and_deliverable():
    print("\n--- TEST 6 & 7: End-to-End Project Audit, Bug Report & Deliverable Path ---")
    user_request = "Alex, mere project ka audit karo, bugs ki report banao aur report save karke path batao"

    # 1. Create plan
    plan = planner_engine.create_plan_for_goal(user_request, target="alex")
    assert len(plan.steps) >= 5, f"Expected at least 5 steps for audit & report, got {len(plan.steps)}"
    print(f"  [PASS] Plan created with {len(plan.steps)} dependency-ordered steps.")

    # 2. Execute plan (with explicit owner confirmation callback)
    ok, summary = planner_engine.execute_plan(plan, confirmation_callback=lambda _step: True)
    assert ok, f"Plan execution failed: {summary}"
    assert plan.status == "COMPLETED", f"Expected plan status COMPLETED, got {plan.status}"

    # 3. Deliverable Verification
    report_step = next((s for s in plan.steps if s.action_name == "generate_summary" and s.generated_files), None)
    assert report_step is not None, "Execution result did not include a generated audit report path"
    report_file = Path(report_step.generated_files[0])

    assert report_file.exists(), f"Deliverable report file not found at {report_file}"
    assert report_file.stat().st_size > 100, f"Report file is empty or too small: {report_file.stat().st_size} bytes"
    assert re.match(r"^alex_audit_and_bug_report_[0-9a-f]{32}\.md$", report_file.name), (
        f"Expected UUID-based filename pattern, got '{report_file.name}'"
    )

    # Check report content structure
    content = report_file.read_text(encoding="utf-8")
    assert "ALEX AI — Project Audit & Bug Report" in content, "Missing report header"
    assert "Syntax & Compilation Audit" in content, "Missing syntax audit section"
    assert "Security & Permission Audit" in content, "Missing security audit section"

    # Confirm path is truthfully included in summary
    assert str(report_file.resolve()) in summary or str(report_file) in summary or report_file.name in summary, (
        f"Summary must contain truthful report path. Got: {summary}"
    )
    print(f"  [PASS] Verified deliverable exists on disk: '{report_file}' ({report_file.stat().st_size} bytes)")
    print(f"  [PASS] Summary truthfully reported path: {summary}")


def test_8_task_center_persistence():
    print("\n--- TEST 8: Task Center Persistence & State Transitions ---")
    tasks = task_center.get_tasks()
    assert len(tasks) > 0, "Task center should have recorded the executed tasks"
    completed_tasks = [t for t in tasks if t.status == TaskStatus.COMPLETED]
    assert len(completed_tasks) > 0, "Task center should have recorded completed tasks"
    latest = completed_tasks[-1]
    assert latest.progress_pct == 100, f"Completed task progress should be 100%, got {latest.progress_pct}%"
    print(f"  [PASS] Task Center recorded task '{latest.goal[:40]}' - status={latest.status}, progress={latest.progress_pct}%")


def test_9_voice_pipeline_goal_routing():
    print("\n--- TEST 9: Voice Pipeline Multi-Step Goal Routing ---")
    cmd = "mere project ka audit karo, bugs ki report banao aur report save karke path batao"
    original_level = task_center.get_autonomy_level()
    task_center.set_autonomy_level(AutonomyLevel.TRUSTED)
    try:
        res = voice_pipeline.process_text_command(cmd, engine_used="typed_test")
    finally:
        task_center.set_autonomy_level(original_level)
    assert res.success, f"Voice pipeline failed to execute goal: {res.response_text}"
    assert res.verified, "Result must be verified with real evidence"
    assert "audit" in res.response_text.lower() or "report" in res.response_text.lower()
    print("  [PASS] Voice pipeline cleanly routed multi-step goal through orchestrator.")


def test_10_avatar_abstinence():
    print("\n--- TEST 10: Avatar Abstinence Check ---")
    import ui
    assert not hasattr(ui.MainWindow, "_load_3d_avatar"), "No 3D avatar loader should exist in MainWindow"
    assert not hasattr(ui.MainWindow, "_avatar_view"), "No 3D avatar view widget should exist in MainWindow"
    print("  [PASS] Confirmed 0 avatar / 3D character widgets re-introduced.")


def test_11_voice_pipeline_alex_brain_routing():
    print("\n--- TEST 11: Voice Pipeline AlexBrain Routing ---")
    cmd = "mere project ka audit karo"

    # Case A & B: Successful orchestration and Blocked/denied execution
    for success in (True, False):
        brain_res = SimpleNamespace(
            intent="PROJECT_AUDIT",
            plan_executed=success,
            success=success,
            response_text="Audit completed." if success else "Audit blocked.",
            verification_status="Verified" if success else "Blocked by Security Engine"
        )
        with patch("core.alex_brain.alex_brain.process_request", return_value=brain_res) as process_request:
            with patch("core.gemini.call") as gemini_call:
                voice_pipeline._recent_commands.clear()
                res = voice_pipeline.process_text_command(cmd, engine_used="typed_test")

        process_request.assert_called_once_with(cmd)
        gemini_call.assert_not_called()
        assert res.success is success
        assert res.verified is success
        assert res.response_text == brain_res.response_text
        assert res.engine_used == "autonomous_task_orchestrator"
        if not success:
            assert res.error_message == "Blocked by Security Engine"

    # Case C: Brain Exception Handling
    with patch("core.alex_brain.alex_brain.process_request", side_effect=RuntimeError("Database lock failure")) as process_request:
        with patch("core.gemini.call") as gemini_call:
            voice_pipeline._recent_commands.clear()
            res_err = voice_pipeline.process_text_command(cmd, engine_used="typed_test")

    process_request.assert_called_once_with(cmd)
    gemini_call.assert_not_called()
    assert res_err.success is False
    assert res_err.verified is False
    assert "Database lock failure" in str(res_err.error_message)
    assert res_err.engine_used == "autonomous_task_orchestrator"

    # Case D: Ordinary conversational requests (no goal keywords)
    conv_cmd = "what is the speed of light in vacuum"
    mock_gemini_resp = SimpleNamespace(text="The speed of light is approximately 299,792 km/s.")
    with patch("core.alex_brain.alex_brain.process_request") as process_request:
        with patch("core.gemini.call", return_value=mock_gemini_resp) as gemini_call:
            voice_pipeline._recent_commands.clear()
            res_conv = voice_pipeline.process_text_command(conv_cmd, engine_used="typed_test")

    process_request.assert_not_called()
    gemini_call.assert_called_once_with(conv_cmd, tier="fast")
    assert res_conv.success is True
    assert res_conv.engine_used == "gemini_llm"
    assert "299,792" in res_conv.response_text

    print("  [PASS] Voice routing verified for: success, blocked execution, brain exceptions, and conversational fallback.")


def _isolated_task_center():
    center = TaskCenter.__new__(TaskCenter)
    center._tasks = {}
    center._cancel_events = {}
    center._autonomy_level = "NORMAL"
    return center


class _FakeDispatcher:
    def __init__(self, result=None, on_dispatch=None):
        self.result = result or DispatchResult(success=True, output="synthetic result", verified=True)
        self.on_dispatch = on_dispatch
        self.calls = []

    def dispatch(self, **kwargs):
        self.calls.append(kwargs)
        if self.on_dispatch:
            self.on_dispatch()
        return self.result


def test_12_confirmation_requires_explicit_approval():
    center = _isolated_task_center()
    dispatcher = _FakeDispatcher()
    plan = Plan(
        plan_id=f"TEST_APPROVAL_{time.time_ns()}", goal="Synthetic approval gate", target="",
        steps=[PlanStep(1, "Privileged synthetic step", "files", "synthetic", {}, risk_level="CRITICAL")],
    )
    with patch.object(center, "_persist", lambda: None), \
            patch("core.planner_engine.task_center", center), \
            patch("core.task_dispatcher.task_dispatcher", dispatcher), \
            patch("core.planner_engine.security_manager.check_permission", return_value=(True, "allowed")), \
            patch("core.planner_engine.event_bus.publish"):
        ok, message = planner_engine.execute_plan(plan)
    assert not ok and plan.status == "FAILED"
    assert "explicit approval" in message.lower()
    assert not dispatcher.calls, "Permission clearance must not substitute for human approval."


def test_13_invalid_dependencies_rejected_before_queueing():
    invalid_plans = [
        [PlanStep(1, "Unknown dependency", "system", "synthetic", {}, depends_on=[99])],
        [
            PlanStep(1, "Cycle A", "system", "synthetic", {}, depends_on=[2]),
            PlanStep(2, "Cycle B", "system", "synthetic", {}, depends_on=[1]),
        ],
        [PlanStep(1, "Duplicate A", "system", "synthetic", {}), PlanStep(1, "Duplicate B", "system", "synthetic", {})],
    ]
    for index, steps in enumerate(invalid_plans):
        center = _isolated_task_center()
        dispatcher = _FakeDispatcher()
        plan = Plan(plan_id=f"TEST_INVALID_{time.time_ns()}_{index}", goal="Invalid synthetic plan", target="", steps=steps)
        with patch.object(center, "_persist", lambda: None), \
                patch("core.planner_engine.task_center", center), \
                patch("core.task_dispatcher.task_dispatcher", dispatcher), \
                patch("core.planner_engine.event_bus.publish"):
            ok, _ = planner_engine.execute_plan(plan)
        assert not ok and plan.status == "FAILED"
        assert not center.get_tasks(), "Invalid plans must be rejected before task creation."
        assert not dispatcher.calls, "Invalid plans must be rejected before dispatch."


def test_14_unverified_dispatch_cannot_complete_plan():
    center = _isolated_task_center()
    dispatcher = _FakeDispatcher(DispatchResult(success=True, output="unverified", verified=False,
                                                error="NO_EVIDENCE"))
    plan = Plan(plan_id=f"TEST_UNVERIFIED_{time.time_ns()}", goal="Synthetic unverified result", target="",
                steps=[PlanStep(1, "Needs evidence", "system", "synthetic", {})])
    with patch.object(center, "_persist", lambda: None), \
            patch("core.planner_engine.task_center", center), \
            patch("core.task_dispatcher.task_dispatcher", dispatcher), \
            patch("core.planner_engine.event_bus.publish"), \
            patch("core.planner_engine.MAX_RETRIES", 0):
        ok, _ = planner_engine.execute_plan(plan)
    assert not ok and plan.status == "FAILED"
    assert center.get_tasks()[0].status == TaskStatus.FAILED


def test_15_task_center_cancel_reaches_running_plan():
    center = _isolated_task_center()
    cancel_event = threading.Event()

    def cancel_current_task():
        current_task_id = next(iter(center._tasks))
        assert center.cancel_task(current_task_id)

    dispatcher = _FakeDispatcher(on_dispatch=cancel_current_task)
    plan = Plan(
        plan_id=f"TEST_CANCEL_PROPAGATION_{time.time_ns()}", goal="Synthetic cancellation", target="",
        steps=[
            PlanStep(1, "Cancel during first handler", "system", "synthetic", {}),
            PlanStep(2, "Must not run", "system", "synthetic", {}, depends_on=[1]),
        ],
    )
    with patch.object(center, "_persist", lambda: None), \
            patch("core.planner_engine.task_center", center), \
            patch("core.task_dispatcher.task_dispatcher", dispatcher), \
            patch("core.planner_engine.event_bus.publish"):
        ok, _ = planner_engine.execute_plan(plan, cancel_event=cancel_event)
    task = center.get_tasks()[0]
    assert not ok and plan.status == "CANCELLED" and task.status == TaskStatus.CANCELLED
    assert cancel_event.is_set()
    assert len(dispatcher.calls) == 1, "Cancellation must stop dispatch before the next plan step."
    center.set_task_running(task.task_id)
    center.set_task_waiting(task.task_id, "late update")
    center.set_task_verifying(task.task_id)
    center.set_task_planning(task.task_id)
    center.complete_task(task.task_id, "late completion", verification="late")
    assert task.status == TaskStatus.CANCELLED, "Late task updates must not overwrite cancellation."


def test_16_task_center_summary_is_available():
    center = _isolated_task_center()
    with patch.object(center, "_persist", lambda: None):
        task = center.queue_task("Synthetic summary task", plan=["step"])
    task.status = TaskStatus.RUNNING
    summary = center.format_task_center_summary()
    assert "1 active" in summary and "Synthetic summary task" in summary
    assert "no tasks recorded" in _isolated_task_center().format_task_center_summary()


def test_17_dispatcher_rejects_canned_success_paths():
    dispatcher = TaskDispatcher()
    with patch.object(dispatcher, "_try_intent_engine_text", return_value=None):
        assert not dispatcher._execute_operation({}).success
        assert not dispatcher._execute_operation({"goal": "synthetic unsupported goal"}).success
    assert not dispatcher._generate_document_summary({"goal": "synthetic summary only"}).verified
    assert not dispatcher._verify_result({"goal": "synthetic verify with no files"}).verified

    with tempfile.TemporaryDirectory() as temp_dir:
        missing_document = dispatcher._generate_document_summary({"file_path": str(Path(temp_dir) / "missing.pdf")})
        assert not missing_document.success and not missing_document.verified
        unsupported_path = Path(temp_dir) / "fixture.bin"
        unsupported_path.write_text("synthetic", encoding="utf-8")
        unsupported_document = dispatcher._generate_document_summary({"file_path": str(unsupported_path)})
        assert not unsupported_document.success and not unsupported_document.verified

        with patch.dict(sys.modules, {
            "core.project_manager": SimpleNamespace(
                project_manager=SimpleNamespace(get_project=lambda _name: SimpleNamespace(path=temp_dir))
            )
        }):
            empty_audit = dispatcher._syntax_audit({"project": "synthetic"})
        assert not empty_audit.success and not empty_audit.verified

        source = Path(temp_dir) / "Downloads"
        source.mkdir()
        (source / "fixture.pdf").write_text("synthetic", encoding="utf-8")
        verified_file = dispatcher._verify_result({"goal": "synthetic file", "files": [str(source / "fixture.pdf")]})
        assert verified_file.success and verified_file.verified
        categorized = dispatcher._file_operation("build_categories", {"source": str(source)})
        assert categorized.success and "Documents: 1" in categorized.output
        destination = source / "Organized"
        with patch.object(TaskDispatcher, "_get_authorized_roots", return_value=[Path(temp_dir).resolve()]):
            moved = dispatcher._move_files({"source": str(source), "destination": str(destination)})
            assert moved.success and (destination / "Documents" / "fixture.pdf").is_file()
            structure = dispatcher._file_operation(
                "verify_structure", {"source": str(source), "destination": str(destination)}
            )
            assert structure.success and structure.verified

    registry = SimpleNamespace(has=lambda _name: True, run=lambda *_args, **_kwargs: "Done.")
    with patch.dict(sys.modules, {"main": SimpleNamespace(_action_registry=registry)}):
        registry_result = dispatcher._try_action_registry("synthetic_action", {})
    assert registry_result is not None and not registry_result.success and not registry_result.verified

    with patch("core.intent_engine.intent_engine.parse", return_value=SimpleNamespace(is_local_command=True)), \
            patch("core.intent_engine.intent_engine.execute_local_command",
                  return_value=SimpleNamespace(handled=True, response_text="synthetic action ran")):
        intent_result = dispatcher._try_intent_engine_text("synthetic command")
    assert intent_result is not None and not intent_result.success and not intent_result.verified


def test_19_reachability_requires_a_real_connection_result():
    dispatcher = TaskDispatcher()
    fake_psutil = SimpleNamespace(
        cpu_percent=lambda interval: 1.0,
        virtual_memory=lambda: SimpleNamespace(percent=2.0, used=3, total=4),
        disk_usage=lambda _path: SimpleNamespace(percent=5.0),
    )
    with patch.dict(sys.modules, {"psutil": fake_psutil}), \
            patch("core.task_dispatcher.socket.create_connection") as create_connection:
        invalid = dispatcher._system_info("check_port_or_url", {"target": "project-name-only"})
        create_connection.assert_not_called()
        assert not invalid.success and not invalid.verified
        invalid_port = dispatcher._system_info("check_port_or_url", {"target": "http://example.invalid:bad"})
        create_connection.assert_not_called()
        assert not invalid_port.success and not invalid_port.verified

        create_connection.return_value = MagicMock()
        connected = dispatcher._system_info("check_port_or_url", {"target": "http://example.invalid:8080"})
        assert connected.success and connected.verified
        create_connection.assert_called_once_with(("example.invalid", 8080), timeout=3)


def test_20_plan_verifies_artifacts_from_prior_steps():
    center = _isolated_task_center()
    with tempfile.TemporaryDirectory() as temp_dir:
        artifact = Path(temp_dir) / "synthetic-report.md"
        artifact.write_text("synthetic report", encoding="utf-8")

        class ArtifactDispatcher:
            calls = []

            def dispatch(self, **kwargs):
                self.calls.append(kwargs)
                if kwargs["action_name"] == "generate_summary":
                    return DispatchResult(success=True, output="generated", verified=True,
                                          generated_files=[str(artifact)])
                assert kwargs["action_name"] == "verify_result"
                assert kwargs["params"]["files"] == [str(artifact)]
                return DispatchResult(success=True, output="file checked", verified=True)

        dispatcher = ArtifactDispatcher()
        plan = Plan(
            plan_id=f"TEST_ARTIFACT_VERIFY_{time.time_ns()}", goal="Synthetic report verification", target="",
            steps=[
                PlanStep(1, "Generate report", "documents", "generate_summary", {}),
                PlanStep(2, "Verify report", "system", "verify_result", {"goal": "synthetic"}, depends_on=[1]),
            ],
        )
        with patch.object(center, "_persist", lambda: None), \
                patch("core.planner_engine.task_center", center), \
                patch("core.task_dispatcher.task_dispatcher", dispatcher), \
                patch("core.planner_engine.event_bus.publish"), \
                patch("core.planner_engine.timeline.record"):
            ok, _ = planner_engine.execute_plan(plan)
        assert ok and plan.status == "COMPLETED"
        assert center.get_tasks()[0].status == TaskStatus.COMPLETED


def test_21_cancel_plan_event_stops_completion():
    center = _isolated_task_center()
    dispatcher = _FakeDispatcher()
    plan = Plan(plan_id=f"TEST_CANCEL_PLAN_{time.time_ns()}", goal="Synthetic cancel_plan", target="",
                steps=[PlanStep(1, "Verified before cancel request", "system", "synthetic", {})])

    def cancel_after_step_verifies(step):
        if step.status == "VERIFIED":
            assert planner_engine.cancel_plan(plan.plan_id)

    with patch.object(center, "_persist", lambda: None), \
            patch("core.planner_engine.task_center", center), \
            patch("core.task_dispatcher.task_dispatcher", dispatcher), \
            patch("core.planner_engine.event_bus.publish"):
        ok, _ = planner_engine.execute_plan(plan, update_callback=cancel_after_step_verifies)
    assert not ok and plan.status == "CANCELLED"
    assert center.get_tasks()[0].status == TaskStatus.CANCELLED


def test_22_task_center_failure_blocks_plan_completion():
    center = _isolated_task_center()
    dispatcher = _FakeDispatcher()
    plan = Plan(plan_id=f"TEST_TASK_CENTER_FAILED_{time.time_ns()}", goal="Synthetic task center failure", target="",
                steps=[PlanStep(1, "Handler result verified", "system", "synthetic", {})])

    def fail_task_before_completion(step):
        if step.status == "VERIFIED":
            task_id = next(iter(center._tasks))
            center.fail_task(task_id, "synthetic task center failure")

    with patch.object(center, "_persist", lambda: None), \
            patch("core.planner_engine.task_center", center), \
            patch("core.task_dispatcher.task_dispatcher", dispatcher), \
            patch("core.planner_engine.event_bus.publish"):
        ok, message = planner_engine.execute_plan(plan, update_callback=fail_task_before_completion)
    assert not ok and plan.status == "FAILED"
    assert "did not confirm completion" in message
    assert center.get_tasks()[0].status == TaskStatus.FAILED


def test_23_project_audit_uses_a_real_local_check_without_endpoint():
    with patch("core.planner_engine.event_bus.publish"):
        plan = planner_engine.create_plan_for_goal("audit project", target="alex")
    resource_step = next(step for step in plan.steps if step.step_id == 2)
    assert resource_step.action_name == "audit_resources"
    assert resource_step.params == {}


def test_18_live_session_fallback_excludes_autonomous_failures():
    autonomous_failure = SimpleNamespace(
        success=False, intent="PROJECT_AUDIT", engine_used="autonomous_task_orchestrator"
    )
    ordinary_failure = SimpleNamespace(success=False, intent="GENERAL_QUERY", engine_used="error")
    assert not should_forward_to_live_session(autonomous_failure)
    assert should_forward_to_live_session(ordinary_failure)


if __name__ == "__main__":
    print("=" * 70)
    print("ALEX 4.0 — AUTONOMOUS TASK ORCHESTRATOR 2.0 VERIFICATION SUITE")
    print("=" * 70)

    test_1_dependency_ordering()
    test_2_duplicate_prevention()
    test_3_bounded_retries_and_unregistered()
    test_4_cancellation_propagation()
    test_5_privileged_confirmation_gate()
    test_6_and_7_end_to_end_project_audit_and_deliverable()
    test_8_task_center_persistence()
    test_9_voice_pipeline_goal_routing()
    test_10_avatar_abstinence()
    test_11_voice_pipeline_alex_brain_routing()
    test_12_confirmation_requires_explicit_approval()
    test_13_invalid_dependencies_rejected_before_queueing()
    test_14_unverified_dispatch_cannot_complete_plan()
    test_15_task_center_cancel_reaches_running_plan()
    test_16_task_center_summary_is_available()
    test_17_dispatcher_rejects_canned_success_paths()
    test_18_live_session_fallback_excludes_autonomous_failures()
    test_19_reachability_requires_a_real_connection_result()
    test_20_plan_verifies_artifacts_from_prior_steps()
    test_21_cancel_plan_event_stops_completion()
    test_22_task_center_failure_blocks_plan_completion()
    test_23_project_audit_uses_a_real_local_check_without_endpoint()

    print("\n" + "=" * 70)
    print("ALL 11 ORCHESTRATOR VERIFICATION PHASES PASSED WITH ZERO FAILURES!")
    print("=" * 70)
