import os

import pytest

from agent_service.eval_runner import run_eval_suite
from agent_service.config import Settings
from agent_service.rag import PolicyRAG
from agent_service.react_agent import ReActAgent
from scripts.seed_p0_demo import main as seed_p0_demo


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_P1_EVAL") != "1",
    reason="Set RUN_P1_EVAL=1 when local MySQL is available.",
)


def test_basic_eval_suite_reports_agent_metrics():
    seed_p0_demo()
    settings = Settings(
        agent_router_mode="deterministic",
        tool_router_mode="deterministic",
        rag_retriever_mode="keyword",
        policy_answer_mode="extractive",
    )
    agent = ReActAgent(PolicyRAG("docs/policies/airline_policy.md", settings=settings), settings=settings)

    result = run_eval_suite("default", agent)

    assert result["total"] >= 20
    assert result["task_success_rate"] >= 0.8
    assert result["tool_call_accuracy"] >= 0.8
    assert result["citation_presence_rate"] >= 0.8
    assert "average_steps" in result
    assert "failed_cases" in result
