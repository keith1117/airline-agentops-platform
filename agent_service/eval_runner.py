import json
import re
from pathlib import Path
from typing import Any, Dict, List


def _load_cases(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _run_case(agent, case: Dict[str, Any], idx: int, suffix: str = "") -> Dict[str, Any]:
    role = case["role"]
    session_id = f"eval-{role}-{idx}{suffix}"
    if role == "customer":
        return agent.customer_chat(
            session_id,
            case.get("customer_email", "testcustomer@nyu.edu"),
            case["message"],
        )
    return agent.staff_chat(
        session_id,
        case.get("staff_username", "admin"),
        case.get("airline_name", "United"),
        case["message"],
    )


def _resolve_case_fixture(case: Dict[str, Any]) -> Dict[str, Any]:
    fixture = case.get("fixture")
    if fixture not in {"future_customer_ticket", "customer_with_future_ticket"}:
        return case

    from .db import get_conn

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.ticket_id, t.customer_email
                FROM Ticket t
                JOIN Flight f
                  ON f.airline_name=t.airline_name
                 AND f.flight_number=t.flight_number
                 AND f.departure_date_time=t.departure_date_time
                WHERE t.departure_date_time > NOW()
                  AND f.status IN ('ON_TIME', 'DELAYED')
                ORDER BY t.departure_date_time, t.ticket_id
                LIMIT 1
                """
            )
            ticket = cur.fetchone()
    finally:
        conn.close()

    if not ticket:
        raise RuntimeError("The eval fixture requires one future ON_TIME or DELAYED customer ticket.")
    resolved = dict(case)
    resolved["customer_email"] = ticket["customer_email"]
    if fixture == "future_customer_ticket":
        resolved["message"] = case["message"].format(ticket_id=ticket["ticket_id"])
    return resolved


def _expected_tools(case: Dict[str, Any]) -> List[str]:
    if "expected_tools" in case:
        return case["expected_tools"]
    if "expected_tool" in case:
        return [case["expected_tool"]]
    return []


def _expected_keywords(case: Dict[str, Any]) -> List[str]:
    if "expected_keywords" in case:
        return case["expected_keywords"]
    if "expected_keyword" in case:
        return [case["expected_keyword"]]
    return []


def _tool_args_match(tool_calls: List[Dict[str, Any]], expected_args: Dict[str, Dict[str, Any]]) -> bool:
    for tool_name, expected in expected_args.items():
        calls = [call for call in tool_calls if call.get("name") == tool_name]
        if not calls:
            return False
        actual_args = calls[-1].get("args", {})
        for key, expected_value in expected.items():
            if actual_args.get(key) != expected_value:
                return False
    return True


def _sequence_matches(actual: List[str], expected: List[str], mode: str = "exact") -> bool:
    if not expected:
        return True
    if mode == "exact":
        return actual == expected
    if mode != "subsequence":
        raise ValueError(f"Unsupported tool_sequence_mode: {mode}")
    expected_idx = 0
    for tool_name in actual:
        if tool_name == expected[expected_idx]:
            expected_idx += 1
            if expected_idx == len(expected):
                return True
    return False


def _rate(passed: int, total: int) -> float | None:
    return round(passed / total, 3) if total else None


def _expected_value_matches(actual: Any, case: Dict[str, Any], field: str) -> bool:
    expected_field = f"expected_{field}"
    return expected_field not in case or actual == case[expected_field]


def run_eval_suite(suite_name: str, agent) -> Dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", suite_name):
        raise ValueError("Unknown evaluation suite.")
    path = Path("eval") / f"{suite_name}.jsonl"
    if not path.exists():
        path = Path("eval/default.jsonl")
    cases = _load_cases(path)
    results = []
    passed = 0
    total_steps = 0
    tool_checks = 0
    tool_checks_passed = 0
    citation_checks = 0
    citation_checks_passed = 0
    sequence_checks = 0
    sequence_checks_passed = 0
    multi_step_checks = 0
    multi_step_checks_passed = 0
    unauthorized_checks = 0
    unauthorized_checks_passed = 0
    confirmation_checks = 0
    confirmation_checks_passed = 0
    fallback_count = 0
    for idx, case in enumerate(cases, start=1):
        case = _resolve_case_fixture(case)
        for setup_idx, setup in enumerate(case.get("setup", []), start=1):
            _run_case(agent, {**case, **setup}, idx, suffix=f"-setup-{setup_idx}")

        resp = _run_case(agent, case, idx)
        tool_names = [call["name"] for call in resp.get("tool_calls", [])]
        total_steps += len(tool_names)
        expected_tools = _expected_tools(case)
        forbidden_tools = case.get("forbidden_tools", [])
        tool_checks += int(bool(expected_tools or forbidden_tools))
        ok_expected_tools = all(tool in tool_names for tool in expected_tools)
        ok_forbidden_tools = not any(tool in tool_names for tool in forbidden_tools)
        ok_tool_args = _tool_args_match(resp.get("tool_calls", []), case.get("expected_tool_args", {}))
        ok_tool = ok_expected_tools and ok_forbidden_tools and ok_tool_args
        tool_checks_passed += int(ok_tool) if expected_tools or forbidden_tools else 0

        expected_sequence = case.get("expected_tool_sequence", [])
        if expected_sequence:
            sequence_checks += 1
            ok_sequence = _sequence_matches(
                tool_names,
                expected_sequence,
                case.get("tool_sequence_mode", "exact"),
            )
            sequence_checks_passed += int(ok_sequence)
        else:
            ok_sequence = True

        is_multi_step = bool(case.get("multi_step", len(expected_sequence) > 1))
        if is_multi_step:
            multi_step_checks += 1

        answer = resp.get("answer", "")
        ok_keyword = all(keyword.lower() in answer.lower() for keyword in _expected_keywords(case))

        if case.get("requires_citation"):
            citation_checks += 1
            ok_citation = bool(resp.get("citations"))
            citation_checks_passed += int(ok_citation)
        else:
            ok_citation = True

        execution = resp.get("execution") or {}
        fallback_reason = execution.get("fallback_reason")
        fallback_count += int(bool(fallback_reason))
        ok_stop_reason = _expected_value_matches(execution.get("stop_reason"), case, "stop_reason")
        ok_request_path = _expected_value_matches(execution.get("request_path"), case, "request_path")
        ok_runtime_mode = _expected_value_matches(execution.get("runtime_mode_used"), case, "runtime_mode_used")
        ok_pending_booking_search = _expected_value_matches(
            bool(resp.get("pending_booking_search")), case, "pending_booking_search"
        )
        ok_pending_cancellation = _expected_value_matches(
            bool(resp.get("pending_cancellation")), case, "pending_cancellation"
        )

        if case.get("requires_unauthorized_rejection"):
            unauthorized_checks += 1
            ok_unauthorized = ok_forbidden_tools and execution.get("request_path") == "scope_fallback"
            unauthorized_checks_passed += int(ok_unauthorized)
        else:
            ok_unauthorized = True

        if "expected_confirmation_required" in case:
            confirmation_checks += 1
            blocked_tools = case.get("confirmation_blocked_tools", [])
            ok_confirmation = (
                execution.get("confirmation_required") == case["expected_confirmation_required"]
                and not any(tool in tool_names for tool in blocked_tools)
            )
            confirmation_checks_passed += int(ok_confirmation)
        else:
            ok_confirmation = True

        ok = all(
            [
                ok_tool,
                ok_sequence,
                ok_keyword,
                ok_citation,
                ok_stop_reason,
                ok_request_path,
                ok_runtime_mode,
                ok_pending_booking_search,
                ok_pending_cancellation,
                ok_unauthorized,
                ok_confirmation,
            ]
        )
        if is_multi_step:
            multi_step_checks_passed += int(ok)
        passed += int(ok)
        checks = {
            "tools": ok_tool,
            "tool_sequence": ok_sequence,
            "keywords": ok_keyword,
            "citations": ok_citation,
            "stop_reason": ok_stop_reason,
            "request_path": ok_request_path,
            "runtime_mode": ok_runtime_mode,
            "pending_booking_search": ok_pending_booking_search,
            "pending_cancellation": ok_pending_cancellation,
            "unauthorized_rejection": ok_unauthorized,
            "confirmation_gate": ok_confirmation,
        }
        results.append(
            {
                "id": case.get("id", idx),
                "passed": ok,
                "checks": checks,
                "failure_types": [name for name, passed_check in checks.items() if not passed_check],
                "tools": tool_names,
                "answer": answer[:300],
                "execution": {
                    "request_path": execution.get("request_path"),
                    "runtime_mode_used": execution.get("runtime_mode_used"),
                    "router_used": execution.get("router_used"),
                    "step_count": execution.get("step_count"),
                    "stop_reason": execution.get("stop_reason"),
                    "confirmation_required": execution.get("confirmation_required"),
                    "fallback_reason": fallback_reason,
                    "trajectory": execution.get("trajectory", []),
                },
            }
        )
    total = len(results) or 1
    tool_denominator = tool_checks or 1
    citation_denominator = citation_checks or 1
    failed_cases = [item for item in results if not item["passed"]]
    return {
        "suite": suite_name,
        "total": len(results),
        "passed": passed,
        "task_success_rate": round(passed / total, 3),
        "tool_call_accuracy": round(tool_checks_passed / tool_denominator, 3),
        "citation_presence_rate": round(citation_checks_passed / citation_denominator, 3),
        "average_steps": round(total_steps / total, 2),
        "multi_step_task_success_rate": _rate(multi_step_checks_passed, multi_step_checks),
        "tool_order_accuracy": _rate(sequence_checks_passed, sequence_checks),
        "unauthorized_call_rejection_rate": _rate(unauthorized_checks_passed, unauthorized_checks),
        "confirmation_gate_hit_rate": _rate(confirmation_checks_passed, confirmation_checks),
        "fallback_rate": round(fallback_count / total, 3),
        "metric_counts": {
            "multi_step_cases": multi_step_checks,
            "tool_sequence_checks": sequence_checks,
            "unauthorized_rejection_checks": unauthorized_checks,
            "confirmation_gate_checks": confirmation_checks,
            "citation_checks": citation_checks,
        },
        "failed_cases": failed_cases,
        "failed_trace_cases": failed_cases,
    }
