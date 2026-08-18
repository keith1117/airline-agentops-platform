import json
from datetime import datetime

import app as web_app
from agent_service.agentops import build_agentops_dashboard
from app import app


def _trace_row(
    trace_id,
    *,
    role="customer",
    request_path="tool_routing",
    runtime_mode="bounded_react",
    fallback_reason=None,
    error=None,
    confirmation_required=False,
):
    execution = {
        "request_path": request_path,
        "runtime_mode_used": runtime_mode,
        "router_used": "native",
        "step_count": 2,
        "stop_reason": "completed",
        "confirmation_required": confirmation_required,
        "fallback_reason": fallback_reason,
        "trajectory": [
            {"type": "decision_summary", "content": "Need current inventory before answering."},
            {"type": "action", "tool": "search_flights", "args": {"departure_airport": "SFO"}},
            {"type": "observation", "tool": "search_flights", "content": {"count": 2}},
            {"type": "final_answer", "content": "Two flights are available."},
        ],
    }
    return {
        "id": trace_id,
        "session_id": f"session-{trace_id}",
        "role": role,
        "principal": "user@example.com",
        "user_message": "Find flights from SFO",
        "reasoning": "private internal text\nexecution: " + json.dumps(execution),
        "tool_calls": json.dumps([{"name": "search_flights", "args": {}, "result": {"count": 2}}]),
        "final_answer": "Two flights are available.",
        "latency_ms": 240,
        "error": error,
        "created_at": datetime(2026, 8, 18, 10, 30),
    }


def _metrics():
    return {
        "total_requests": 3,
        "error_count": 1,
        "avg_latency_ms": 120.5,
        "endpoints": {
            "POST /api/agent/customer/chat": {
                "count": 3,
                "error_count": 1,
                "tool_calls": 4,
                "avg_latency_ms": 120.5,
            }
        },
        "roles": {"customer": {"count": 3, "tool_calls": 4, "error_count": 1}},
    }


def test_dashboard_builds_trace_summary_without_exposing_raw_reasoning():
    dashboard = build_agentops_dashboard(
        [
            _trace_row(3),
            _trace_row(2, fallback_reason="native router unavailable"),
            _trace_row(1, error="tool failed", confirmation_required=True),
        ],
        _metrics(),
        limit=25,
    )

    assert dashboard["summary"] == {
        "total_traces": 3,
        "error_count": 1,
        "fallback_count": 1,
        "fallback_rate": 0.333,
        "avg_latency_ms": 240.0,
        "avg_steps": 2.0,
        "confirmation_required_count": 1,
        "request_paths": [{"name": "tool_routing", "count": 3}],
        "routers": [{"name": "native", "count": 3}],
        "tools": [{"name": "search_flights", "count": 3}],
    }
    assert dashboard["metrics"] == _metrics()
    assert dashboard["returned_traces"] == 3
    assert "reasoning" not in dashboard["traces"][0]
    assert "private internal text" not in json.dumps(dashboard)
    assert dashboard["traces"][0]["trajectory"][1]["type"] == "action"
    assert dashboard["traces"][0]["trajectory"][1]["tool"] == "search_flights"
    assert '"departure_airport": "SFO"' in dashboard["traces"][0]["trajectory"][1]["display"]


def test_dashboard_filters_role_path_runtime_and_outcome():
    rows = [
        _trace_row(3),
        _trace_row(2, role="staff", request_path="staff_multi_tool", fallback_reason="json fallback"),
        _trace_row(1, role="staff", request_path="staff_multi_tool", runtime_mode="single_step"),
    ]

    dashboard = build_agentops_dashboard(
        rows,
        _metrics(),
        role="staff",
        request_path="staff_multi_tool",
        runtime_mode="bounded_react",
        outcome="fallback",
        limit=50,
    )

    assert dashboard["returned_traces"] == 1
    assert dashboard["traces"][0]["id"] == 2
    assert dashboard["filter_options"]["roles"] == ["customer", "staff"]
    assert dashboard["filter_options"]["request_paths"] == ["staff_multi_tool", "tool_routing"]
    assert dashboard["filter_options"]["runtime_modes"] == ["bounded_react", "single_step"]


def test_dashboard_handles_legacy_or_corrupt_trace_payloads():
    row = _trace_row(1)
    row["reasoning"] = "legacy trace without execution metadata"
    row["tool_calls"] = "not-json"

    dashboard = build_agentops_dashboard([row], {}, limit=999)

    trace = dashboard["traces"][0]
    assert trace["request_path"] == "unknown"
    assert trace["runtime_mode_used"] == "unknown"
    assert trace["tools_used"] == []
    assert trace["trajectory"] == []
    assert dashboard["filters"]["limit"] == 200


def test_dashboard_infers_action_count_when_legacy_step_count_is_zero():
    row = _trace_row(1)
    execution = json.loads(row["reasoning"].split("\nexecution: ", 1)[1])
    execution["step_count"] = 0
    execution["trajectory"][1] = {"type": "action", "action": "search_flights", "args": {}}
    row["reasoning"] = "legacy\nexecution: " + json.dumps(execution)

    trace = build_agentops_dashboard([row], {}, limit=25)["traces"][0]

    assert trace["step_count"] == 1
    assert trace["trajectory"][1]["tool"] == "search_flights"


def test_staff_agentops_requires_staff_session(monkeypatch):
    monkeypatch.setattr(web_app, "agent_get", lambda *_args, **_kwargs: {})
    client = app.test_client()

    assert client.get("/staff/agentops").status_code == 302

    with client.session_transaction() as flask_session:
        flask_session.update({"role": "customer", "email": "customer@example.com"})
    assert client.get("/staff/agentops").status_code == 302


def test_staff_agentops_renders_filtered_trace_viewer(monkeypatch):
    captured = {}
    dashboard = build_agentops_dashboard([_trace_row(7)], _metrics(), role="customer", limit=25)

    def fake_agent_get(path, params=None):
        captured.update({"path": path, "params": params})
        return dashboard

    monkeypatch.setattr(web_app, "agent_get", fake_agent_get)
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session.update({"role": "staff", "username": "admin", "airline": "United"})

    response = client.get("/staff/agentops?role=customer&limit=25")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert captured["path"] == "/api/agentops/dashboard"
    assert captured["params"]["role"] == "customer"
    assert "AgentOps Dashboard" in html
    assert "Trace #7" in html
    assert "search_flights" in html
    assert "Need current inventory before answering." in html
    assert "private internal text" not in html
