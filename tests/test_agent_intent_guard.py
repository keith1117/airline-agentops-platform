from agent_service.rag import PolicyRAG
from agent_service.react_agent import ReActAgent


def make_agent(monkeypatch):
    agent = ReActAgent(PolicyRAG("docs/policies/airline_policy.md"))
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)
    return agent


def test_customer_identity_question_does_not_call_tools(monkeypatch):
    agent = make_agent(monkeypatch)

    resp = agent.customer_chat("guard-customer-name", "testcustomer@nyu.edu", "what is my name?")

    assert resp["tool_calls"] == []
    assert "testcustomer@nyu.edu" in resp["answer"]


def test_staff_identity_question_does_not_call_tools(monkeypatch):
    agent = make_agent(monkeypatch)

    resp = agent.staff_chat("guard-staff-name", "admin", "United", "what is my name?")

    assert resp["tool_calls"] == []
    assert "admin" in resp["answer"]
    assert "United" in resp["answer"]


def test_staff_out_of_scope_question_does_not_default_to_sales(monkeypatch):
    agent = make_agent(monkeypatch)

    resp = agent.staff_chat("guard-staff-weather", "admin", "United", "what is the weather tomorrow?")

    assert resp["tool_calls"] == []
    assert "i can only help with airline operations" in resp["answer"].lower()
    assert "i can't answer" in resp["answer"].lower()
    assert "tools" not in resp["answer"].lower()
    assert not resp["answer"].lower().startswith("sales report:")
