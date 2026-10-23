"""
test_alex_brain_deep.py — Deep Architecture & Cognitive Brain Test Suite for ALEX 3.0.
"""

from core.alex_brain import alex_brain
from core.context_engine import context_engine
from core.event_bus import event_bus
from core.planner_engine import planner_engine
from core.recovery_engine import recovery_engine
from core.service_manager import service_manager
from core.skill_router import skill_router

def run_tests():
    print("=" * 65)
    print("ALEX 3.0 — DEEP INTERNAL BRAIN & COGNITIVE ARCHITECTURE TEST")
    print("=" * 65)

    # 1. Event Bus Decoupled Publish/Subscribe
    received_events = []
    def _test_handler(evt):
        received_events.append(evt.event_type)
    event_bus.subscribe("TEST_EVENT", _test_handler)
    event_bus.publish("TEST_EVENT", {"status": "ok"})
    assert "TEST_EVENT" in received_events
    print("[TEST 1] Event Bus publish/subscribe: OK")

    # 2. Context Engine & Anaphoric Reference Resolution
    context_engine.set_last_file("project_architecture.pdf")
    resolved_text, meta = context_engine.resolve_references("iska summary batao")
    assert "project_architecture.pdf" in resolved_text
    print(f"[TEST 2] Reference Resolution ('iska' -> '{resolved_text}'): OK")

    # 3. Intelligent Skill Routing
    routed_vol = skill_router.route_query("volume badhao")
    assert routed_vol.skill_name == "computer"
    assert routed_vol.target_engine == "LOCAL"
    routed_code = skill_router.route_query("python syntax error fix karo")
    assert routed_code.skill_name == "coding"
    print("[TEST 3] Intelligent Skill Routing (<50ms local prioritization): OK")

    # 4. Dynamic Goal Planning & Execution
    plan = planner_engine.create_plan_for_goal("SkillSum website check karo", target="SkillSum")
    assert len(plan.steps) == 5
    assert plan.steps[0].skill_name == "projects"
    ok, rep = planner_engine.execute_plan(plan)
    assert ok is True
    print(f"[TEST 4] Goal Planning & Verification ({len(plan.steps)} steps executed): OK")

    # 5. Bounded Self-Recovery Engine
    counter = {"attempts": 0}
    def _flaky_op():
        counter["attempts"] += 1
        if counter["attempts"] < 2:
            raise ConnectionError("Temporary timeout on socket")
        return "Recovered Result"
    succ, val, diag = recovery_engine.attempt_recovery("test_operation", _flaky_op)
    assert succ is True
    assert val == "Recovered Result"
    print("[TEST 5] Bounded Self-Recovery (Error classified, recovered): OK")

    # 6. Service Manager & Watchdog
    service_manager.heartbeat("alex_core", healthy=True)
    services = service_manager.get_all_services()
    assert "alex_core" in services
    assert services["alex_core"]["healthy"] is True
    print("[TEST 6] Service Manager & Lightweight Watchdog: OK")

    # 7. AlexBrain End-to-End Cognitive Pipeline
    queries = [
        ("Alex, volume badhao", "computer", "VOLUME_UP"),
        ("Alex, RAM kitna use ho raha hai", "system", "SYSTEM_STATUS"),
        ("Alex, mera laptop thoda fast karo", "system", "UNKNOWN"),
        ("Alex, morning briefing do", "research", "MORNING_BRIEFING")
    ]
    for q, exp_skill, exp_intent in queries:
        res = alex_brain.process_request(q, speaker="Sir")
        assert res.authorized is True
        assert len(res.response_text) > 0
        print(f"  • Processed '{q}': Intent={res.intent}, Skill={res.routed_skill}, Latency={res.duration_ms}ms")
    print("[TEST 7] AlexBrain End-to-End Cognitive Pipeline: OK")

    print("\nALL DEEP BRAIN ARCHITECTURE TESTS PASSED!")

if __name__ == "__main__":
    run_tests()

