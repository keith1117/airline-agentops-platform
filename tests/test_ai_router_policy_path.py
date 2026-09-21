from agent_service.config import Settings
from agent_service.rag import PolicyRAG
from agent_service.react_agent import ReActAgent
from agent_service.trace_export import _parse_execution


class FakeRouter:
    def route(self, role, message, context=None):
        return {
            "intent": "policy_question",
            "tool": "answer_policy_question",
            "args": {"question": message},
            "needs_clarification": False,
            "clarification_question": None,
        }


def test_llm_router_policy_tool_enters_same_rag_pipeline_when_fast_path_misses(monkeypatch):
    settings = Settings(
        agent_router_mode="llm",
        rag_retriever_mode="keyword",
        policy_answer_mode="extractive",
    )
    agent = ReActAgent(
        PolicyRAG("docs/policies/airline_policy.md", settings=settings),
        settings=settings,
        router=FakeRouter(),
    )
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)

    resp = agent.customer_chat(
        "router-policy-path",
        "testcustomer@nyu.edu",
        "What options do I have if my trip plans change?",
    )

    assert any(call["name"] == "answer_policy_question" for call in resp["tool_calls"])
    assert resp["execution"]["request_path"] == "policy_rag"
    assert resp["execution"]["router_used"] == "llm"
    assert resp["execution"]["answer_mode_used"] in {"extractive", "none"}


class BookingRouter:
    def route(self, role, message, context=None):
        return {
            "intent": "booking_transaction",
            "tool": "create_booking_intent",
            "args": {},
            "needs_clarification": True,
            "clarification_question": "Which flight should I create a pending booking for?",
        }


class CompleteBookingRouter:
    def route(self, role, message, context=None):
        return {
            "intent": "booking_transaction",
            "tool": "create_booking_intent",
            "args": {
                "airline_name": "United",
                "flight_number": "P0206",
                "departure_date_time": "2026-06-08 09:30:00",
                "departure_airport": "SFO",
                "arrival_airport": "LAX",
            },
            "needs_clarification": False,
            "clarification_question": None,
        }


def test_llm_booking_plan_with_complete_flight_details_returns_bookable_search_result(monkeypatch):
    settings = Settings(agent_router_mode="llm")
    agent = ReActAgent(
        PolicyRAG("docs/policies/airline_policy.md", settings=settings),
        settings=settings,
        router=CompleteBookingRouter(),
    )
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)

    calls = []

    def fake_call(role, tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        if tool_name == "search_flights":
            return {
                "count": 1,
                "flights": [
                    {
                        "airline_name": "United",
                        "flight_number": "P0206",
                        "departure_date_time": "2026-06-08 09:30:00",
                        "arrival_date_time": "2026-06-08 11:05:00",
                        "departure_airport": "SFO",
                        "arrival_airport": "LAX",
                        "base_price": 420,
                        "seats_left": 8,
                        "status": "ON_TIME",
                    }
                ],
            }
        raise AssertionError(f"unexpected tool call {tool_name}")

    monkeypatch.setattr(agent.registry, "call", fake_call)

    resp = agent.customer_chat(
        "router-booking-complete",
        "testcustomer@nyu.edu",
        "purchase flight of P0206 from SFO to LAX departure time at 2026-06-08 09:30:00",
    )

    assert [name for name, _ in calls] == ["search_flights"]
    assert resp["pending_confirmation"] is None
    assert resp["pending_booking_search"]["flight_number"] == "P0206"
    assert "which flight number" not in resp["answer"].lower()
    assert "book" in resp["answer"].lower()


def test_transaction_request_with_payment_word_does_not_enter_policy_rag(monkeypatch):
    settings = Settings(agent_router_mode="llm")
    agent = ReActAgent(
        PolicyRAG("docs/policies/airline_policy.md", settings=settings),
        settings=settings,
        router=BookingRouter(),
    )
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)

    resp = agent.customer_chat(
        "router-payment-transaction",
        "testcustomer@nyu.edu",
        "Pay for this booking now",
    )

    assert not any(call["name"] == "answer_policy_question" for call in resp["tool_calls"])
    assert resp["tool_calls"] == []
    assert "which flight" in resp["answer"].lower()


def test_ticket_followup_after_refund_context_checks_exact_ticket_status(monkeypatch):
    settings = Settings(agent_router_mode="deterministic")
    agent = ReActAgent(
        PolicyRAG("docs/policies/airline_policy.md", settings=settings),
        settings=settings,
    )
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent, "_recent_session_text", lambda session_id: "User asked about refund policy.")

    calls = []

    def fake_call(role, tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        if tool_name == "get_customer_ticket":
            return {
                "ticket": {
                    "ticket_ID": 900090,
                    "airline_name": "United",
                    "flight_number": "P0206",
                    "departure_date_time": "2026-06-08 09:30:00",
                    "arrival_date_time": "2026-06-08 11:05:00",
                    "departure_airport": "SFO",
                    "arrival_airport": "LAX",
                    "status": "ON_TIME",
                }
            }
        raise AssertionError(f"unexpected tool call {tool_name}")

    monkeypatch.setattr(agent.registry, "call", fake_call)

    resp = agent.customer_chat("ticket-followup-refund", "testcustomer@nyu.edu", "my ticket: #900090")

    assert [name for name, _ in calls] == ["get_customer_ticket"]
    assert "ticket 900090" in resp["answer"].lower()
    assert "on_time" in resp["answer"].lower()
    assert "not currently eligible" in resp["answer"].lower()
    assert "get_customer_trips" not in [call["name"] for call in resp["tool_calls"]]


def test_cancel_request_without_ticket_asks_for_ticket_instead_of_policy_rag(monkeypatch):
    settings = Settings(agent_router_mode="deterministic")
    agent = ReActAgent(
        PolicyRAG("docs/policies/airline_policy.md", settings=settings),
        settings=settings,
    )
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)

    def fake_call(role, tool_name, **kwargs):
        raise AssertionError(f"unexpected tool call {tool_name}")

    monkeypatch.setattr(agent.registry, "call", fake_call)

    resp = agent.customer_chat("cancel-needs-ticket", "testcustomer@nyu.edu", "please cancel my flight")

    assert resp["tool_calls"] == []
    assert "ticket number" in resp["answer"].lower()
    assert "such as" not in resp["answer"].lower()
    assert resp["execution"]["request_path"] == "clarification"


def test_cancel_followup_with_ticket_id_creates_cancellation_preview(monkeypatch):
    settings = Settings(agent_router_mode="deterministic")
    agent = ReActAgent(
        PolicyRAG("docs/policies/airline_policy.md", settings=settings),
        settings=settings,
    )
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)
    monkeypatch.setattr(agent, "_recent_session_text", lambda session_id: "User asked: please cancel my flight.")

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

    resp = agent.customer_chat("cancel-followup", "testcustomer@nyu.edu", "my ticket: #900090")

    assert [name for name, _ in calls] == ["preview_customer_ticket_cancellation"]
    assert resp["pending_cancellation"]["ticket_id"] == 900090
    assert resp["execution"]["stop_reason"] == "cancellation_confirmation_required"
    assert resp["execution"]["confirmation_required"] is True
    assert "ticket 900090" in resp["answer"].lower()
    assert "confirm" in resp["answer"].lower()
    assert "$252.00" in resp["answer"]
    assert "$168.00" in resp["answer"]


class CancelTicketRouter:
    def enabled(self):
        return True

    def route(self, role, message, context=None):
        return {
            "intent": "cancel_ticket",
            "tool": "cancel_customer_ticket",
            "args": {"ticket_id": 900090},
            "needs_clarification": False,
            "clarification_question": None,
        }


def test_llm_cancel_tool_plan_is_downgraded_to_preview(monkeypatch):
    settings = Settings(agent_router_mode="llm")
    agent = ReActAgent(
        PolicyRAG("docs/policies/airline_policy.md", settings=settings),
        settings=settings,
        router=CancelTicketRouter(),
    )
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

    resp = agent.customer_chat("cancel-router-preview", "testcustomer@nyu.edu", "please undo my trip")

    assert [name for name, _ in calls] == ["preview_customer_ticket_cancellation"]
    assert not any(call["name"] == "cancel_customer_ticket" for call in resp["tool_calls"])
    assert resp["pending_cancellation"]["confirmation_required"] is True


class UnknownToolRouter:
    def enabled(self):
        return True

    def route(self, role, message, context=None):
        return {
            "intent": "unknown",
            "tool": "drop_database",
            "args": {},
            "needs_clarification": False,
            "clarification_question": None,
        }


class NativeSearchRouter:
    router_kind = "native"

    def enabled(self):
        return True

    def route(self, role, message, context=None):
        return {
            "intent": "flight_search",
            "tool": "search_flights",
            "args": {"departure_airport": "SFO", "arrival_airport": "LAX"},
            "needs_clarification": False,
            "clarification_question": None,
        }


class FailingNativeRouter:
    router_kind = "native"

    def enabled(self):
        return True

    def route(self, role, message, context=None):
        raise RuntimeError("native tool calling failed")


class NoToolNativeRouter:
    router_kind = "native"

    def enabled(self):
        return True

    def route(self, role, message, context=None):
        return {
            "intent": "unknown",
            "tool": None,
            "args": {},
            "needs_clarification": False,
            "clarification_question": None,
        }


def test_auto_mode_unknown_llm_tool_falls_back_to_scope_response(monkeypatch):
    settings = Settings(agent_router_mode="auto")
    agent = ReActAgent(
        PolicyRAG("docs/policies/airline_policy.md", settings=settings),
        settings=settings,
        router=UnknownToolRouter(),
    )
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)

    resp = agent.customer_chat(
        "router-unknown-tool",
        "testcustomer@nyu.edu",
        "Recommend a restaurant near Times Square",
    )

    assert resp["tool_calls"] == []
    assert "i can only help with airline booking tasks" in resp["answer"].lower()
    assert "unsupported customer tool" in resp["execution"]["fallback_reason"].lower()


def test_native_router_path_records_native_router_and_react_trajectory(monkeypatch):
    settings = Settings(tool_router_mode="native")
    agent = ReActAgent(
        PolicyRAG("docs/policies/airline_policy.md", settings=settings),
        settings=settings,
        router=NativeSearchRouter(),
    )
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)

    def fake_call(role, tool_name, **kwargs):
        assert tool_name == "search_flights"
        return {
            "count": 1,
            "flights": [
                {
                    "airline_name": "United",
                    "flight_number": "P0206",
                    "departure_date_time": "2026-06-08 09:30:00",
                    "departure_airport": "SFO",
                    "arrival_airport": "LAX",
                    "base_price": 420,
                    "seats_left": 8,
                }
            ],
        }

    monkeypatch.setattr(agent.registry, "call", fake_call)

    resp = agent.customer_chat("native-search", "testcustomer@nyu.edu", "Find flights from SFO to LAX")

    assert resp["execution"]["router_used"] == "native"
    assert resp["execution"]["request_path"] == "tool_routing"
    assert [step["type"] for step in resp["execution"]["trajectory"]] == [
        "reasoning",
        "action",
        "observation",
        "final_answer",
    ]
    assert resp["execution"]["trajectory"][1]["tool"] == "search_flights"


def test_native_search_uses_saved_preferences_when_route_is_omitted(monkeypatch):
    class PreferenceSearchRouter(NativeSearchRouter):
        def route(self, role, message, context=None):
            return {
                "intent": "flight_search",
                "tool": "search_flights",
                "args": {"period": "next_month"},
                "needs_clarification": False,
                "clarification_question": None,
            }

    settings = Settings(tool_router_mode="native")
    agent = ReActAgent(
        PolicyRAG("docs/policies/airline_policy.md", settings=settings),
        settings=settings,
        router=PreferenceSearchRouter(),
    )
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)
    calls = []

    def fake_call(role, tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        if tool_name == "get_user_preferences":
            return {
                "preferences": {
                    "departure_city": "SFO",
                    "destination_city": "LAX",
                    "max_budget": 500.0,
                    "preferred_airline": "United",
                }
            }
        if tool_name == "search_flights":
            return {"count": 0, "flights": []}
        raise AssertionError(f"unexpected tool call {tool_name}")

    monkeypatch.setattr(agent.registry, "call", fake_call)

    resp = agent.customer_chat("native-memory-search", "testcustomer@nyu.edu", "Find flights next month")

    assert [name for name, _ in calls] == ["get_user_preferences", "search_flights"]
    assert calls[1][1]["departure_airport"] == "SFO"
    assert calls[1][1]["arrival_airport"] == "LAX"
    assert calls[1][1]["airline_name"] == "United"
    assert calls[1][1]["max_price"] == 500.0
    assert [call["name"] for call in resp["tool_calls"]] == ["get_user_preferences", "search_flights"]


def test_staff_booking_request_is_rejected_before_native_routing(monkeypatch):
    settings = Settings(tool_router_mode="native")
    agent = ReActAgent(
        PolicyRAG("docs/policies/airline_policy.md", settings=settings),
        settings=settings,
        router=FailingNativeRouter(),
    )
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)

    resp = agent.staff_chat(
        "native-staff-no-book",
        "admin",
        "United",
        "Book United flight P0206 for testcustomer@nyu.edu",
    )

    assert resp["tool_calls"] == []
    assert resp["execution"]["request_path"] == "scope_fallback"
    assert "airline operations" in resp["answer"].lower()


def test_native_staff_load_factor_uses_product_formatter(monkeypatch):
    class LoadFactorRouter:
        router_kind = "native"

        def enabled(self):
            return True

        def route(self, role, message, context=None):
            return {
                "intent": "get_flight_load_factor",
                "tool": "get_flight_load_factor",
                "args": {},
                "needs_clarification": False,
                "clarification_question": None,
            }

    settings = Settings(tool_router_mode="native")
    agent = ReActAgent(
        PolicyRAG("docs/policies/airline_policy.md", settings=settings),
        settings=settings,
        router=LoadFactorRouter(),
    )
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        agent.registry,
        "call",
        lambda role, tool_name, **kwargs: {
            "rows": [{"flight_number": "P0206", "load_factor_pct": 50.0}],
            "count": 1,
        },
    )

    resp = agent.staff_chat("native-load", "admin", "United", "Which flights are close to full?")

    assert "highest load factor flights" in resp["answer"].lower()


def test_forced_native_router_failure_is_controlled_error(monkeypatch):
    settings = Settings(tool_router_mode="native")
    agent = ReActAgent(
        PolicyRAG("docs/policies/airline_policy.md", settings=settings),
        settings=settings,
        router=FailingNativeRouter(),
    )
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)

    resp = agent.customer_chat("native-fail", "testcustomer@nyu.edu", "Find flights from SFO to LAX")

    assert "controlled error" in resp["answer"].lower()
    assert "native tool calling failed" in resp["execution"]["fallback_reason"]


def test_forced_native_no_tool_records_scope_fallback(monkeypatch):
    settings = Settings(tool_router_mode="native")
    agent = ReActAgent(
        PolicyRAG("docs/policies/airline_policy.md", settings=settings),
        settings=settings,
        router=NoToolNativeRouter(),
    )
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)

    resp = agent.customer_chat(
        "native-no-customer-tool",
        "testcustomer@nyu.edu",
        "Show me the United sales report",
    )

    assert resp["tool_calls"] == []
    assert resp["execution"]["router_used"] == "native"
    assert resp["execution"]["request_path"] == "scope_fallback"
    assert "airline booking tasks" in resp["answer"].lower()


def test_auto_native_no_tool_can_fall_back_to_deterministic(monkeypatch):
    settings = Settings(tool_router_mode="auto", agent_router_mode="auto")
    agent = ReActAgent(
        PolicyRAG("docs/policies/airline_policy.md", settings=settings),
        settings=settings,
        router=NoToolNativeRouter(),
    )
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)

    def fake_call(role, tool_name, **kwargs):
        assert tool_name == "search_flights"
        return {"count": 0, "flights": []}

    monkeypatch.setattr(agent.registry, "call", fake_call)

    resp = agent.customer_chat("native-no-tool", "testcustomer@nyu.edu", "Find flights from SFO to LAX")

    assert "no matching future flights" in resp["answer"].lower()
    assert resp["execution"]["router_used"] == "deterministic"
    assert "returned no tool" in resp["execution"]["fallback_reason"]


def test_trace_execution_parser_extracts_react_trajectory():
    reasoning = 'Classify request\nexecution: {"router_used":"native","trajectory":[{"type":"action","tool":"search_flights"}]}'

    execution = _parse_execution(reasoning)

    assert execution["router_used"] == "native"
    assert execution["trajectory"][0]["tool"] == "search_flights"
