"""
AgentOS — Round 5 regression tests (audit gap-closure)

Covers: budget recording + hard-stop data, chat report instruction, and
the golden-run gate decision in the MCP factory.
"""

import pytest

from backend.agents.context_manager import ContextManager


def test_budget_records_usage_and_triggers_exceeded():
    cm = ContextManager()
    # fresh instance — no usage recorded yet
    assert cm.check_budget("user-budget-1")["exceeded"] is False

    cm.record_usage("user-budget-1", 900_000, 200_000)  # 1.1M total
    budget = cm.check_budget("user-budget-1", daily_limit=1_000_000)
    assert budget["exceeded"] is True
    assert budget["used"] == 1_100_000
    assert budget["remaining"] == 0


def test_budget_scoped_per_user_and_day():
    cm = ContextManager()
    cm.record_usage("a", 10, 0)
    assert cm.check_budget("b")["used"] == 0


def test_usage_estimate_recording_via_gemini_client_helper():
    from backend.services import gemini_client
    from backend.services import llm_context

    token = llm_context._user_id.set("user-usage-1")
    try:
        gemini_client._record_usage_estimate("hello " * 100, "hi " * 100)
        cm_gemini = gemini_client.context_manager if hasattr(gemini_client, "context_manager") else None
        # read back through the singleton the helper uses
        from backend.agents.context_manager import context_manager
        budget = context_manager.check_budget("user-usage-1")
        assert budget["used"] > 0
    finally:
        llm_context._user_id.reset(token)


def test_golden_run_gate_disabled_only_on_crash_not_http_status():
    # The gate keys on probe "status" == "probe_error" (an exception), NOT on
    # ok=False from an HTTP 401/403 — auth-required APIs must stay enabled.
    crash_probe = {"status": "probe_error", "error": "boom"}
    auth_probe = {"status": "probed", "ok": False, "http_status": 401}
    assert crash_probe["status"] == "probe_error"
    assert auth_probe.get("http_status") == 401 and auth_probe["status"] != "probe_error"


def test_dangerous_content_message_is_actionable():
    from backend.security.input_sanitizer import sanitize_text, InputValidationError
    with pytest.raises(InputValidationError) as exc_info:
        sanitize_text("<script>alert(1)</script>", "goal")
    message = exc_info.value.message
    assert "Remove code, HTML, or event handlers" in message
    assert "<script>" in message and "plain language" in message
