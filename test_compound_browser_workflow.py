"""
test_compound_browser_workflow.py - End-to-end verification of compound browser search workflow.

Validates the full pipeline:
1. Receive command (Hinglish, English, variants)
2. Resolve intended action and parameters (browser, platform, query)
3. Clarification if query is missing
4. Validate permissions and security policy
5. Execute browser action using supported tools (ChromeAdapter / AppRegistry)
6. Verify browser launch and process detection
7. Provide structured UI/voice confirmation
8. Handle missing browser, network failures, timeouts honestly without fabrication.
"""

import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.intent_engine import intent_engine
from core.agent_engine import agent_engine
from core.security import security_manager
from core.app_adapters import ChromeAdapter, app_registry


def test_intent_parsing():
    print("\n--- TEST 1: Intent Parsing & Parameter Extraction ---")
    scenarios = [
        ("Alex, Chrome kholo aur YouTube par Python tutorial search karo.", "Chrome", "YouTube", "Python tutorial"),
        ("Chrome kholo aur YouTube par Python tutorial search karo", "Chrome", "YouTube", "Python tutorial"),
        ("Open Chrome and search Python tutorial on YouTube", "Chrome", "YouTube", "Python tutorial"),
        ("open Chrome and search for Python tutorial on YouTube", "Chrome", "YouTube", "Python tutorial"),
        ("Chrome kholo aur YouTube par search karo", "Chrome", "YouTube", ""),
        ("Chrome kholo aur machine learning search karo", "Chrome", "Google", "machine learning"),
    ]

    for raw, exp_browser, exp_platform, exp_query in scenarios:
        res = intent_engine.parse(raw)
        assert res.intent == "COMPOUND_BROWSER_SEARCH", f"Failed intent for: {raw} -> got {res.intent}"
        assert res.is_local_command is True, f"Command must be local for deterministic execution: {raw}"
        browser = res.slots.get("browser", "Chrome")
        platform = res.slots.get("platform", "YouTube")
        query = res.slots.get("query", "").strip()

        assert browser.lower() == exp_browser.lower(), f"Browser mismatch: {browser} != {exp_browser}"
        assert platform.lower() == exp_platform.lower(), f"Platform mismatch: {platform} != {exp_platform}"
        assert query.lower() == exp_query.lower(), f"Query mismatch: {query} != {exp_query}"
        print(f"  [PASS] '{raw}' -> browser={browser}, platform={platform}, query='{query}'")


def test_clarification_on_missing_query():
    print("\n--- TEST 2: Clarification on Missing Query ---")
    res = intent_engine.parse("Alex, Chrome kholo aur YouTube par search karo.")
    executed = intent_engine.execute_local_command(res)
    assert executed.handled is True
    assert "YouTube" in executed.response_text or "search" in executed.response_text.lower()
    print(f"  [PASS] Clarification response: {executed.response_text}")


def test_permission_denial_handling():
    print("\n--- TEST 3: Permission Check & Denial Handling ---")
    # Temporarily set auth to level 0 (guest)
    orig_level = security_manager.get_auth_level()
    try:
        security_manager._auth_level = 0  # guest
        res = intent_engine.parse("Alex, Chrome kholo aur YouTube par Python tutorial search karo.")
        executed = intent_engine.execute_local_command(res)
        assert executed.handled is True
        assert "allowed nahi hai" in executed.response_text or "denied" in executed.response_text.lower()
        print(f"  [PASS] Handled permission rejection: {executed.response_text}")
    finally:
        security_manager._auth_level = orig_level


def test_missing_browser_handling():
    print("\n--- TEST 4: Missing Browser Honest Handling ---")
    out = agent_engine.execute_compound_browser_search(
        browser="NonExistentBrowserXYZ",
        platform="youtube",
        query="Python tutorial",
        lang="hinglish"
    )
    assert out.success is False
    assert "NonExistentBrowserXYZ" in out.summary_message
    assert "nahi mila" in out.summary_message or "not found" in out.summary_message
    print(f"  [PASS] Honest failure response for missing browser: {out.summary_message}")


def test_full_execution_workflow():
    print("\n--- TEST 5: Full Execution & Verification Workflow ---")
    res = intent_engine.parse("Alex, Chrome kholo aur YouTube par Python tutorial search karo.")
    executed = intent_engine.execute_local_command(res)
    assert executed.handled is True
    print(f"  Execution Response: {executed.response_text}")
    assert "Google Chrome" in executed.response_text or "Chrome" in executed.response_text
    assert "Python tutorial" in executed.response_text
    assert "YouTube" in executed.response_text

    # Verify process actually running
    proc_ok, proc_detail = agent_engine.verify_app_running("chrome")
    print(f"  Verification check: {proc_detail}")
    assert proc_ok is True, "Chrome process must be running and verified!"
    print("  [PASS] Full workflow passed with genuine process verification!")


if __name__ == "__main__":
    test_intent_parsing()
    test_clarification_on_missing_query()
    test_permission_denial_handling()
    test_missing_browser_handling()
    test_full_execution_workflow()
    print("\nALL 5 TESTS PASSED SUCCESSFULLY!")
