import os

import pytest

from agent_service.db import ensure_agent_schema, get_conn
from agent_service.config import Settings
from agent_service.rag import PolicyRAG
from agent_service.react_agent import ReActAgent
from scripts.seed_p0_demo import main as seed_p0_demo


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_P1_MEMORY") != "1",
    reason="Set RUN_P1_MEMORY=1 when local MySQL is available.",
)


@pytest.fixture()
def agent():
    settings = Settings(
        agent_router_mode="deterministic",
        tool_router_mode="deterministic",
        rag_retriever_mode="keyword",
        policy_answer_mode="extractive",
    )
    ensure_agent_schema(retries=3)
    seed_p0_demo()
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_preferences WHERE customer_email=%s", ("testcustomer@nyu.edu",))
        conn.commit()
    finally:
        conn.close()
    return ReActAgent(PolicyRAG("docs/policies/airline_policy.md", settings=settings), settings=settings)


def test_memory_saves_route_budget_and_airline(agent):
    resp = agent.customer_chat(
        "p1-memory-save",
        "testcustomer@nyu.edu",
        "Remember I prefer United and usually fly SFO to LAX under 500",
    )

    assert any(call["name"] == "remember_user_preference" for call in resp["tool_calls"])
    assert "route SFO -> LAX" in resp["answer"]
    assert "preferred airline United" in resp["answer"]

    prefs = agent.registry.call("customer", "get_user_preferences", customer_email="testcustomer@nyu.edu")
    assert prefs["preferences"]["departure_city"] == "SFO"
    assert prefs["preferences"]["destination_city"] == "LAX"
    assert float(prefs["preferences"]["max_budget"]) == 500
    assert prefs["preferences"]["preferred_airline"] == "United"


def test_memory_is_used_for_later_search_when_route_is_omitted(agent):
    agent.customer_chat(
        "p1-memory-prime",
        "testcustomer@nyu.edu",
        "Remember I prefer United and usually fly SFO to LAX under 500",
    )

    resp = agent.customer_chat(
        "p1-memory-search",
        "testcustomer@nyu.edu",
        "Find flights next month",
    )

    tool_names = [call["name"] for call in resp["tool_calls"]]
    assert "get_user_preferences" in tool_names
    search_call = [call for call in resp["tool_calls"] if call["name"] == "search_flights"][-1]
    assert search_call["args"]["departure_airport"] == "SFO"
    assert search_call["args"]["arrival_airport"] == "LAX"
    assert search_call["args"]["airline_name"] == "United"
    assert float(search_call["args"]["max_price"]) == 500
    assert "United P0206" in resp["answer"]


def test_explicit_route_overrides_memory(agent):
    agent.customer_chat(
        "p1-memory-override-prime",
        "testcustomer@nyu.edu",
        "Remember I prefer United and usually fly SFO to LAX under 500",
    )

    resp = agent.customer_chat(
        "p1-memory-override",
        "testcustomer@nyu.edu",
        "Find flights from JFK to PVG next month",
    )

    search_call = [call for call in resp["tool_calls"] if call["name"] == "search_flights"][-1]
    assert search_call["args"]["departure_airport"] == "JFK"
    assert search_call["args"]["arrival_airport"] == "PVG"
    assert search_call["args"]["max_price"] is None
