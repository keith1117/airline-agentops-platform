import json

from agent_service.qa_harness import generate_agent_qa_cases, run_agent_qa


class FakeAgent:
    def customer_chat(self, session_id, customer_email, message):
        if "refund" in message.lower():
            return {
                "answer": "You may be eligible for a refund if the airline cancelled the flight.",
                "citations": [{"section": "Refund Policy"}],
                "tool_calls": [{"name": "answer_policy_question", "args": {}, "result": {}}],
                "execution": {"request_path": "policy_rag", "router_used": "native"},
            }
        return {
            "answer": "I can only help with airline booking tasks.",
            "citations": [],
            "tool_calls": [],
            "execution": {"request_path": "scope_fallback", "router_used": "deterministic"},
        }

    def staff_chat(self, session_id, staff_username, airline_name, message):
        return {
            "answer": "I can only help with airline operations.",
            "tool_calls": [],
            "tables": None,
            "execution": {"request_path": "scope_fallback", "router_used": "deterministic"},
        }


def test_qa_case_generation_is_seeded_and_can_avoid_recent_prompts():
    first = generate_agent_qa_cases(seed=7, count=8)
    second = generate_agent_qa_cases(seed=7, count=8)

    assert [case.message for case in first] == [case.message for case in second]
    assert len({case.message for case in first}) == len(first)

    recent = {case.message for case in first}
    next_batch = generate_agent_qa_cases(seed=8, count=8, recent_prompts=recent)

    assert recent.isdisjoint({case.message for case in next_batch})


def test_agent_qa_runner_writes_failed_cases_jsonl(tmp_path):
    cases = generate_agent_qa_cases(seed=3, count=4)
    summary = run_agent_qa(FakeAgent(), cases, report_dir=tmp_path, run_id="unit")

    assert summary["total"] == 4
    assert summary["failed"] >= 1
    assert summary["report_path"].endswith("agent_qa_unit_failures.jsonl")

    report = tmp_path / "agent_qa_unit_failures.jsonl"
    assert report.exists()
    rows = [json.loads(line) for line in report.read_text(encoding="utf-8").splitlines()]
    assert rows
    assert {"id", "role", "message", "expected", "actual", "checks"}.issubset(rows[0])
    assert "answer" in rows[0]["actual"]
    assert "tool_calls" in rows[0]["actual"]
    assert "execution" in rows[0]["actual"]
