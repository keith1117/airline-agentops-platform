import os

import pytest

from agent_service.db import ensure_agent_schema
from agent_service.rag import PolicyRAG
from agent_service.react_agent import ReActAgent
from agent_service.tool_registry import ToolAccessError
from scripts.seed_p0_demo import main as seed_p0_demo


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_P0_ACCEPTANCE") != "1",
    reason="Set RUN_P0_ACCEPTANCE=1 when local MySQL is available.",
)


@pytest.fixture(scope="module")
def agent():
    ensure_agent_schema(retries=3)
    seed_p0_demo()
    return ReActAgent(PolicyRAG("docs/policies/airline_policy.md"))


def test_customer_search_uses_database_tool(agent):
    resp = agent.customer_chat(
        "p0-search",
        "testcustomer@nyu.edu",
        "Find flights from SFO to LAX next month",
    )

    assert any(call["name"] == "search_flights" for call in resp["tool_calls"])
    assert "United P0206" in resp["answer"]


def test_customer_policy_question_has_citation(agent):
    resp = agent.customer_chat(
        "p0-policy",
        "testcustomer@nyu.edu",
        "Can I get a refund if my flight is cancelled?",
    )

    assert any(call["name"] == "answer_policy_question" for call in resp["tool_calls"])
    assert resp["citations"]
    assert "cancelled" in resp["answer"].lower()


def test_customer_booking_requires_confirmation_then_issues_ticket(agent):
    search_resp = agent.customer_chat(
        "p0-booking-search",
        "testcustomer@nyu.edu",
        "Find flights from SFO to LAX next month",
    )
    flight = search_resp["tool_calls"][0]["result"]["flights"][0]

    booking_resp = agent.customer_chat(
        "p0-booking",
        "testcustomer@nyu.edu",
        f"Book United flight {flight['flight_number']} at {flight['departure_date_time']}",
    )

    pending = booking_resp["pending_confirmation"]
    assert pending
    assert pending["status"] == "PENDING_CONFIRMATION"

    confirm_resp = agent.confirm_booking(
        pending["booking_intent_id"],
        "testcustomer@nyu.edu",
        pending["idempotency_key"],
    )

    assert confirm_resp["status"] == "CONFIRMED"
    assert confirm_resp["ticket_id"]


def test_staff_copilot_uses_staff_analytics_tools(agent):
    resp = agent.staff_chat(
        "p0-staff",
        "admin",
        "United",
        "Which flights have the worst reviews?",
    )

    assert any(call["name"] == "analyze_reviews" for call in resp["tool_calls"])
    assert "review" in resp["answer"].lower()


def test_customer_cannot_call_staff_tool(agent):
    with pytest.raises(ToolAccessError):
        agent.registry.call("customer", "get_sales_report", airline_name="United")


def test_staff_chat_does_not_execute_customer_booking(agent):
    resp = agent.staff_chat(
        "p0-staff-no-book",
        "admin",
        "United",
        "Book United flight P0206 for testcustomer@nyu.edu",
    )

    assert not any(call["name"] in {"create_booking_intent", "confirm_booking"} for call in resp["tool_calls"])

