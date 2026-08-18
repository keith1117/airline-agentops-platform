import json

from agent_service.eval_runner import run_eval_suite


class FakeP4Agent:
    @staticmethod
    def _response(message):
        if "strong sales" in message:
            tools = [
                {"name": "get_route_performance", "args": {}, "result": {"rows": []}},
                {"name": "analyze_reviews", "args": {}, "result": {"rows": []}},
            ]
            return {
                "answer": "Combined route and review analysis.",
                "tool_calls": tools,
                "execution": {
                    "request_path": "bounded_react",
                    "runtime_mode_used": "bounded_react",
                    "stop_reason": "final_answer",
                    "confirmation_required": False,
                    "step_count": 2,
                    "trajectory": [{"type": "action", "action": tool["name"]} for tool in tools],
                },
            }
        if "Cancel ticket" in message:
            return {
                "answer": "Cancellation preview ready.",
                "tool_calls": [
                    {"name": "preview_customer_ticket_cancellation", "args": {"ticket_id": 1}, "result": {}}
                ],
                "pending_cancellation": {"ticket_id": 1},
                "execution": {
                    "request_path": "bounded_react",
                    "runtime_mode_used": "bounded_react",
                    "stop_reason": "cancellation_confirmation_required",
                    "confirmation_required": True,
                    "step_count": 1,
                    "trajectory": [{"type": "action", "action": "preview_customer_ticket_cancellation"}],
                },
            }
        if "sales report" in message:
            return {
                "answer": "I can only help with airline booking tasks.",
                "tool_calls": [],
                "execution": {
                    "request_path": "scope_fallback",
                    "runtime_mode_used": "single_step",
                    "fallback_reason": "role boundary",
                    "trajectory": [],
                },
            }
        raise AssertionError(f"Unexpected fake eval message: {message}")

    def customer_chat(self, session_id, customer_email, message):
        return self._response(message)

    def staff_chat(self, session_id, staff_username, airline_name, message):
        return self._response(message)


def test_p4_eval_reports_multi_step_governance_metrics(tmp_path, monkeypatch):
    cases = [
        {
            "id": "staff-multi-step",
            "role": "staff",
            "message": "Which route has strong sales but poor reviews?",
            "expected_tools": ["get_route_performance", "analyze_reviews"],
            "expected_tool_sequence": ["get_route_performance", "analyze_reviews"],
            "multi_step": True,
            "expected_stop_reason": "final_answer",
            "expected_request_path": "bounded_react",
            "expected_confirmation_required": False,
        },
        {
            "id": "cancel-gate",
            "role": "customer",
            "message": "Cancel ticket #1",
            "expected_tool_sequence": ["preview_customer_ticket_cancellation"],
            "forbidden_tools": ["cancel_customer_ticket"],
            "confirmation_blocked_tools": ["cancel_customer_ticket"],
            "expected_pending_cancellation": True,
            "expected_confirmation_required": True,
        },
        {
            "id": "role-denial",
            "role": "customer",
            "message": "Show me the sales report",
            "forbidden_tools": ["get_sales_report"],
            "expected_request_path": "scope_fallback",
            "requires_unauthorized_rejection": True,
        },
    ]
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "p4-unit.jsonl").write_text(
        "\n".join(json.dumps(case) for case in cases), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    result = run_eval_suite("p4-unit", FakeP4Agent())

    assert result["task_success_rate"] == 1.0
    assert result["multi_step_task_success_rate"] == 1.0
    assert result["tool_order_accuracy"] == 1.0
    assert result["unauthorized_call_rejection_rate"] == 1.0
    assert result["confirmation_gate_hit_rate"] == 1.0
    assert result["fallback_rate"] == 0.333
    assert result["failed_trace_cases"] == []
    assert result["metric_counts"] == {
        "multi_step_cases": 1,
        "tool_sequence_checks": 2,
        "unauthorized_rejection_checks": 1,
        "confirmation_gate_checks": 2,
        "citation_checks": 0,
    }


def test_p4_eval_failed_case_contains_execution_trace(tmp_path, monkeypatch):
    case = {
        "id": "wrong-order",
        "role": "staff",
        "message": "Which route has strong sales but poor reviews?",
        "expected_tool_sequence": ["analyze_reviews", "get_route_performance"],
        "multi_step": True,
    }
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "p4-failure.jsonl").write_text(json.dumps(case), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = run_eval_suite("p4-failure", FakeP4Agent())

    assert result["tool_order_accuracy"] == 0.0
    assert result["multi_step_task_success_rate"] == 0.0
    assert result["failed_trace_cases"][0]["failure_types"] == ["tool_sequence"]
    assert result["failed_trace_cases"][0]["execution"]["trajectory"]
