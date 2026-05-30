import json
import os

import pytest

from agent_service.rag import PolicyRAG
from agent_service.react_agent import ReActAgent
from agent_service.trace_export import export_traces
from scripts.seed_p0_demo import main as seed_p0_demo


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_P1_TRACE") != "1",
    reason="Set RUN_P1_TRACE=1 when local MySQL is available.",
)


def test_trace_export_writes_sft_ready_jsonl(tmp_path):
    seed_p0_demo()
    agent = ReActAgent(PolicyRAG("docs/policies/airline_policy.md"))
    prefix = "p1-trace-export"
    agent.customer_chat(
        f"{prefix}-customer",
        "testcustomer@nyu.edu",
        "Find flights from SFO to LAX next month",
    )
    agent.staff_chat(
        f"{prefix}-staff",
        "admin",
        "United",
        "Which flights have the worst reviews?",
    )

    output_path = tmp_path / "traces.jsonl"
    result = export_traces(str(output_path), session_prefix=prefix)

    assert result["exported"] >= 2
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == result["exported"]

    first = json.loads(lines[0])
    assert "messages" in first
    assert [message["role"] for message in first["messages"]] == ["user", "assistant", "tool", "assistant"]
    assert "metadata" in first
    assert first["metadata"]["session_id"].startswith(prefix)
    assert first["metadata"]["tool_names"]

