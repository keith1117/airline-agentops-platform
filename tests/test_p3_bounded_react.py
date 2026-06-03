from agent_service.config import Settings
from agent_service.rag import PolicyRAG
from agent_service.react_agent import ReActAgent
from agent_service.tool_registry import Tool, ToolRegistry


class NoopRouter:
    def enabled(self):
        return False


def make_agent(settings=None):
    settings = settings or Settings(agent_runtime_mode="bounded_react", agent_router_mode="deterministic")
    agent = ReActAgent(PolicyRAG("docs/policies/airline_policy.md", settings=settings), settings=settings)
    agent.native_router = NoopRouter()
    agent.router = NoopRouter()
    return agent


def test_tool_registry_records_tool_risk_categories():
    registry = ToolRegistry()
    registry.register(Tool("read_tool", "Read", ["customer"], lambda: {}, risk="safe_read"))
    registry.register(Tool("write_tool", "Write", ["customer"], lambda: {}, risk="controlled_write"))

    assert registry.risk_for("read_tool") == "safe_read"
    assert registry.risk_for("write_tool") == "controlled_write"


def test_bounded_react_booking_preparation_searches_then_returns_bookable_selection(monkeypatch):
    agent = make_agent()
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)
    calls = []

    def fake_call(role, tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        if tool_name == "search_flights":
            return {
                "count": 2,
                "flights": [
                    {
                        "airline_name": "United",
                        "flight_number": "UA999",
                        "departure_airport": "SFO",
                        "arrival_airport": "LAX",
                        "departure_date_time": "2026-07-08 09:30:00",
                        "arrival_date_time": "2026-07-08 11:05:00",
                        "base_price": 520.0,
                        "seats_left": 4,
                        "status": "ON_TIME",
                    },
                    {
                        "airline_name": "United",
                        "flight_number": "P0206",
                        "departure_airport": "SFO",
                        "arrival_airport": "LAX",
                        "departure_date_time": "2026-07-09 09:30:00",
                        "arrival_date_time": "2026-07-09 11:05:00",
                        "base_price": 420.0,
                        "seats_left": 8,
                        "status": "ON_TIME",
                    },
                ],
            }
        raise AssertionError(f"unexpected tool call {tool_name}")

    monkeypatch.setattr(agent.registry, "call", fake_call)

    resp = agent.customer_chat(
        "bounded-booking",
        "testcustomer@nyu.edu",
        "Find the cheapest United flight from SFO to LAX next month and prepare a booking.",
    )

    assert [name for name, _ in calls] == ["search_flights"]
    assert resp["pending_confirmation"] is None
    assert resp["pending_booking_search"]["flight_number"] == "P0206"
    assert resp["execution"]["runtime_mode_used"] == "bounded_react"
    assert resp["execution"]["stop_reason"] == "booking_search_ready"
    assert resp["execution"]["confirmation_required"] is False
    assert [step["type"] for step in resp["execution"]["trajectory"]] == [
        "decision_summary",
        "action",
        "observation",
        "final_answer",
    ]
    assert all(step["type"] != "reasoning_summary" for step in resp["execution"]["trajectory"])


def test_bounded_react_month_request_filters_before_selecting_cheapest(monkeypatch):
    agent = make_agent()
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)
    calls = []

    def fake_call(role, tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        if tool_name == "search_flights":
            assert kwargs["departure_airport"] == "JFK"
            assert kwargs["arrival_airport"] == "ORD"
            assert kwargs["month"] == "2026-08"
            return {
                "count": 2,
                "flights": [
                    {
                        "airline_name": "United",
                        "flight_number": "SYN00014",
                        "departure_airport": "JFK",
                        "arrival_airport": "ORD",
                        "departure_date_time": "2026-08-03 12:00:00",
                        "arrival_date_time": "2026-08-03 20:00:00",
                        "base_price": 859.99,
                        "seats_left": 119,
                        "status": "ON_TIME",
                    },
                    {
                        "airline_name": "United",
                        "flight_number": "SYN00002",
                        "departure_airport": "JFK",
                        "arrival_airport": "ORD",
                        "departure_date_time": "2026-08-03 12:00:00",
                        "arrival_date_time": "2026-08-03 23:30:00",
                        "base_price": 1035.96,
                        "seats_left": 178,
                        "status": "ON_TIME",
                    },
                ],
            }
        raise AssertionError(f"unexpected tool call {tool_name}")

    monkeypatch.setattr(agent.registry, "call", fake_call)

    resp = agent.customer_chat(
        "bounded-month",
        "testcustomer@nyu.edu",
        "Find the cheapest United flight from JFK to ORD on August and prepare a booking.",
    )

    assert [name for name, _ in calls] == ["search_flights"]
    assert resp["pending_booking_search"]["flight_number"] == "SYN00014"
    assert "SYN00014" in resp["answer"]
    assert resp["pending_confirmation"] is None


def test_bounded_react_this_year_request_uses_period_before_selecting_cheapest(monkeypatch):
    agent = make_agent()
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)
    calls = []

    def fake_call(role, tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        if tool_name == "search_flights":
            assert kwargs["departure_airport"] == "JFK"
            assert kwargs["arrival_airport"] == "ORD"
            assert kwargs["period"] == "this_year"
            assert kwargs.get("month") is None
            return {
                "count": 2,
                "flights": [
                    {
                        "airline_name": "United",
                        "flight_number": "SYN00038",
                        "departure_airport": "JFK",
                        "arrival_airport": "ORD",
                        "departure_date_time": "2026-06-17 12:00:00",
                        "arrival_date_time": "2026-06-17 19:00:00",
                        "base_price": 890.18,
                        "seats_left": 119,
                        "status": "ON_TIME",
                    },
                    {
                        "airline_name": "United",
                        "flight_number": "SYN00002",
                        "departure_airport": "JFK",
                        "arrival_airport": "ORD",
                        "departure_date_time": "2026-08-03 12:00:00",
                        "arrival_date_time": "2026-08-03 23:30:00",
                        "base_price": 1035.96,
                        "seats_left": 178,
                        "status": "ON_TIME",
                    },
                ],
            }
        raise AssertionError(f"unexpected tool call {tool_name}")

    monkeypatch.setattr(agent.registry, "call", fake_call)

    resp = agent.customer_chat(
        "bounded-this-year",
        "testcustomer@nyu.edu",
        "Find the cheapest United flight from JFK to ORD this year and prepare a booking.",
    )

    assert [name for name, _ in calls] == ["search_flights"]
    assert resp["pending_booking_search"]["flight_number"] == "SYN00038"
    assert "SYN00038" in resp["answer"]
    assert resp["pending_confirmation"] is None


def test_bounded_react_explicit_flight_number_uses_flight_filter_and_returns_bookable_result(monkeypatch):
    agent = make_agent()
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)
    calls = []

    def fake_call(role, tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        if tool_name == "search_flights":
            assert kwargs["flight_number"] == "SYN00058"
            assert kwargs["travel_date"] == "2026-07-23"
            return {
                "count": 1,
                "flights": [
                    {
                        "airline_name": "United",
                        "flight_number": "SYN00058",
                        "departure_airport": "LAS",
                        "arrival_airport": "LAX",
                        "departure_date_time": "2026-07-23 16:00:00",
                        "arrival_date_time": "2026-07-24 02:45:00",
                        "base_price": 97.23,
                        "seats_left": 179,
                        "status": "ON_TIME",
                    }
                ],
            }
        raise AssertionError(f"unexpected tool call {tool_name}")

    monkeypatch.setattr(agent.registry, "call", fake_call)

    resp = agent.customer_chat(
        "bounded-explicit-flight",
        "testcustomer@nyu.edu",
        "purchase flight of SYN00058 on 2026-07-23",
    )

    assert [name for name, _ in calls] == ["search_flights"]
    assert resp["pending_booking_search"]["flight_number"] == "SYN00058"
    assert resp["pending_booking_search"]["departure_date_time"] == "2026-07-23 16:00:00"
    assert resp["pending_confirmation"] is None


def test_bounded_react_alphanumeric_suffix_flight_number_uses_exact_filter(monkeypatch):
    agent = make_agent()
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)
    calls = []

    def fake_call(role, tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        if tool_name == "search_flights":
            assert kwargs["flight_number"] == "P0DLY"
            return {
                "count": 1,
                "flights": [
                    {
                        "airline_name": "United",
                        "flight_number": "P0DLY",
                        "departure_airport": "SFO",
                        "arrival_airport": "LAX",
                        "departure_date_time": "2026-07-11 15:00:00",
                        "arrival_date_time": "2026-07-11 17:00:00",
                        "base_price": 500.0,
                        "seats_left": 8,
                        "status": "DELAYED",
                    }
                ],
            }
        raise AssertionError(f"unexpected tool call {tool_name}")

    monkeypatch.setattr(agent.registry, "call", fake_call)

    resp = agent.customer_chat(
        "bounded-explicit-alphanumeric-flight",
        "testcustomer@nyu.edu",
        "I want to book flight P0DLY",
    )

    assert [name for name, _ in calls] == ["search_flights"]
    assert resp["pending_booking_search"]["flight_number"] == "P0DLY"
    assert resp["pending_confirmation"] is None
    assert "P0DLY" in resp["answer"]


def test_bounded_react_no_flights_does_not_create_booking_intent(monkeypatch):
    agent = make_agent()
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)
    calls = []

    def fake_call(role, tool_name, **kwargs):
        calls.append(tool_name)
        if tool_name == "search_flights":
            return {"count": 0, "flights": []}
        raise AssertionError(f"unexpected tool call {tool_name}")

    monkeypatch.setattr(agent.registry, "call", fake_call)

    resp = agent.customer_chat(
        "bounded-no-flights",
        "testcustomer@nyu.edu",
        "Find the cheapest United flight from SFO to LAX next month and prepare a booking.",
    )

    assert calls == ["search_flights"]
    assert resp["pending_confirmation"] is None
    assert resp["execution"]["stop_reason"] == "no_flights"
    assert "could not find" in resp["answer"].lower()


def test_bounded_react_cancel_request_returns_preview_not_direct_cancellation(monkeypatch):
    agent = make_agent()
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)
    calls = []

    def fake_call(role, tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        if tool_name == "preview_customer_ticket_cancellation":
            return {
                "preview": True,
                "confirmation_required": True,
                "ticket_id": 900090,
                "airline_name": "United",
                "flight_number": "P0206",
                "departure_airport": "SFO",
                "arrival_airport": "LAX",
                "departure_date_time": "2026-06-08 09:30:00",
                "flight_status": "ON_TIME",
                "base_price": 420.0,
                "cancellation_fee": 252.0,
                "refund_amount": 168.0,
                "policy_code": "STANDARD_ON_TIME",
                "message": "Cancellation preview ready.",
            }
        raise AssertionError(f"unexpected tool call {tool_name}")

    monkeypatch.setattr(agent.registry, "call", fake_call)

    resp = agent.customer_chat("bounded-cancel", "testcustomer@nyu.edu", "please cancel my ticket #900090")

    assert [name for name, _ in calls] == ["preview_customer_ticket_cancellation"]
    assert not any(call["name"] == "cancel_customer_ticket" for call in resp["tool_calls"])
    assert resp["pending_cancellation"]["ticket_id"] == 900090
    assert resp["execution"]["stop_reason"] == "cancellation_confirmation_required"
    assert "confirm" in resp["answer"].lower()


def test_booking_this_one_uses_recent_single_flight_result_without_creating_intent(monkeypatch):
    agent = make_agent()
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        agent,
        "_recent_search_flights",
        lambda session_id: [
            {
                "airline_name": "United",
                "flight_number": "SYN00058",
                "departure_airport": "LAS",
                "arrival_airport": "LAX",
                "departure_date_time": "2026-07-23 16:00:00",
                "arrival_date_time": "2026-07-24 02:45:00",
                "base_price": 97.23,
                "seats_left": 179,
                "status": "ON_TIME",
            }
        ],
    )
    calls = []

    def fake_call(role, tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        raise AssertionError(f"unexpected tool call {tool_name}")

    monkeypatch.setattr(agent.registry, "call", fake_call)

    resp = agent.customer_chat("bounded-book-this-one", "testcustomer@nyu.edu", "book this one")

    assert calls == []
    assert resp["pending_booking_search"]["flight_number"] == "SYN00058"
    assert resp["pending_confirmation"] is None


def test_bounded_react_respects_max_agent_steps(monkeypatch):
    agent = make_agent(Settings(agent_runtime_mode="bounded_react", agent_router_mode="deterministic", max_agent_steps=1))
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)

    resp = agent.customer_chat(
        "bounded-max-steps",
        "testcustomer@nyu.edu",
        "Find the cheapest United flight from SFO to LAX next month and prepare a booking.",
    )

    assert resp["tool_calls"] == []
    assert resp["execution"]["stop_reason"] == "max_steps_reached"
    assert "at least two bounded steps" in resp["answer"]


def test_bounded_runtime_rejects_confirm_booking_tool(monkeypatch):
    agent = make_agent()
    execution = agent._execution()
    tool_calls = []

    try:
        agent._bounded_call(
            "customer",
            "confirm_booking",
            tool_calls,
            execution,
            decision_summary="Do not directly confirm bookings inside the bounded loop.",
            booking_intent_id=1,
            customer_email="testcustomer@nyu.edu",
            idempotency_key="idem",
        )
        raised = False
    except RuntimeError as exc:
        raised = True
        assert "human-confirmed tool" in str(exc)

    assert raised is True
    assert tool_calls == []
    assert execution["stop_reason"] == "human_confirmed_tool_blocked"
    assert execution["confirmation_required"] is True


def test_single_step_mode_does_not_use_bounded_react(monkeypatch):
    agent = make_agent(Settings(agent_runtime_mode="single_step", agent_router_mode="deterministic"))
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent.registry, "call", lambda role, tool_name, **kwargs: {"count": 0, "flights": []})

    resp = agent.customer_chat(
        "single-step-booking",
        "testcustomer@nyu.edu",
        "Find the cheapest United flight from SFO to LAX next month and prepare a booking.",
    )

    assert resp["execution"]["runtime_mode_used"] == "single_step"
    assert resp["execution"]["request_path"] != "bounded_react"


def test_single_step_month_search_uses_same_month_filter(monkeypatch):
    agent = make_agent(Settings(agent_runtime_mode="single_step", agent_router_mode="deterministic"))
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)
    calls = []

    def fake_call(role, tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        if tool_name == "search_flights":
            assert kwargs["departure_airport"] == "JFK"
            assert kwargs["arrival_airport"] == "ORD"
            assert kwargs["month"] == "2026-08"
            return {"count": 0, "flights": []}
        if tool_name == "get_user_preferences":
            return {"preferences": {}}
        raise AssertionError(f"unexpected tool call {tool_name}")

    monkeypatch.setattr(agent.registry, "call", fake_call)

    resp = agent.customer_chat("single-step-month", "testcustomer@nyu.edu", "Find all flights from JFK to ORD on August")

    assert calls[0][0] == "search_flights"
    assert resp["execution"]["request_path"] == "tool_routing"


def test_single_step_this_year_search_uses_period_filter(monkeypatch):
    agent = make_agent(Settings(agent_runtime_mode="single_step", agent_router_mode="deterministic"))
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)
    calls = []

    def fake_call(role, tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        if tool_name == "search_flights":
            assert kwargs["departure_airport"] == "JFK"
            assert kwargs["arrival_airport"] == "ORD"
            assert kwargs["period"] == "this_year"
            assert kwargs.get("month") is None
            return {"count": 0, "flights": []}
        if tool_name == "get_user_preferences":
            return {"preferences": {}}
        raise AssertionError(f"unexpected tool call {tool_name}")

    monkeypatch.setattr(agent.registry, "call", fake_call)

    resp = agent.customer_chat("single-step-this-year", "testcustomer@nyu.edu", "Find all flights from JFK to ORD this year")

    assert calls[0][0] == "search_flights"
    assert resp["execution"]["request_path"] == "tool_routing"
