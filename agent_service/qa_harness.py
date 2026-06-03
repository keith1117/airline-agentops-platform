import json
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


@dataclass(frozen=True)
class AgentQACase:
    id: str
    role: str
    message: str
    expected_tools: List[str] = field(default_factory=list)
    forbidden_tools: List[str] = field(default_factory=list)
    expected_keywords: List[str] = field(default_factory=list)
    requires_citation: bool = False
    requires_pending_confirmation: bool = False
    expected_request_path: Optional[str] = None
    customer_email: str = "testcustomer@nyu.edu"
    staff_username: str = "admin"
    airline_name: str = "United"
    category: str = "general"


def generate_agent_qa_cases(
    seed: int,
    count: int = 24,
    recent_prompts: Optional[Iterable[str]] = None,
) -> List[AgentQACase]:
    """Generate reproducible, bounded-random Agent QA cases.

    This intentionally uses template variation rather than free-form LLM generation so
    every case has deterministic expectations and can be reproduced by seed.
    """

    rng = random.Random(seed)
    recent = set(recent_prompts or [])
    candidates = _case_pool()
    rng.shuffle(candidates)
    selected: List[AgentQACase] = []
    seen: Set[str] = set()
    for case in candidates:
        if case.message in recent or case.message in seen:
            continue
        selected.append(case)
        seen.add(case.message)
        if len(selected) >= count:
            return selected
    return selected


def run_agent_qa(
    agent: Any,
    cases: Sequence[AgentQACase],
    report_dir: str | Path = "logs/agent_qa_runs",
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    report_root = Path(report_dir)
    report_root.mkdir(parents=True, exist_ok=True)
    run_id = run_id or datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    failures_path = report_root / f"agent_qa_{run_id}_failures.jsonl"
    cases_path = report_root / f"agent_qa_{run_id}_cases.jsonl"

    results = []
    failures = []
    for index, case in enumerate(cases, start=1):
        response = _run_case(agent, case, index, run_id)
        checks = _evaluate_response(case, response)
        passed = all(checks.values())
        result = {
            "id": case.id,
            "role": case.role,
            "category": case.category,
            "message": case.message,
            "passed": passed,
            "checks": checks,
            "tools": [call.get("name") for call in response.get("tool_calls", [])],
            "answer": response.get("answer", "")[:500],
        }
        results.append(result)
        if not passed:
            failures.append(
                {
                    "id": case.id,
                    "role": case.role,
                    "category": case.category,
                    "message": case.message,
                    "expected": _expected_payload(case),
                    "actual": _actual_payload(response),
                    "checks": checks,
                }
            )

    _write_jsonl(cases_path, [asdict(case) for case in cases])
    _write_jsonl(failures_path, failures)
    total = len(cases)
    passed = total - len(failures)
    return {
        "run_id": run_id,
        "total": total,
        "passed": passed,
        "failed": len(failures),
        "task_success_rate": round(passed / total, 3) if total else 0.0,
        "report_path": str(failures_path),
        "cases_path": str(cases_path),
        "failed_cases": failures,
        "results": results,
    }


def _run_case(agent: Any, case: AgentQACase, index: int, run_id: str) -> Dict[str, Any]:
    session_id = f"agent-qa-{run_id}-{index}"
    if case.role == "customer":
        return agent.customer_chat(session_id, case.customer_email, case.message)
    if case.role == "staff":
        return agent.staff_chat(session_id, case.staff_username, case.airline_name, case.message)
    raise ValueError(f"Unsupported Agent QA role: {case.role}")


def _evaluate_response(case: AgentQACase, response: Dict[str, Any]) -> Dict[str, bool]:
    answer = str(response.get("answer", ""))
    lower_answer = answer.lower()
    tool_names = [call.get("name") for call in response.get("tool_calls", [])]
    execution = response.get("execution") or {}
    return {
        "expected_tools": all(tool in tool_names for tool in case.expected_tools),
        "forbidden_tools": not any(tool in tool_names for tool in case.forbidden_tools),
        "keywords": all(keyword.lower() in lower_answer for keyword in case.expected_keywords),
        "citations": bool(response.get("citations")) if case.requires_citation else True,
        "pending_confirmation": bool(response.get("pending_confirmation")) if case.requires_pending_confirmation else True,
        "request_path": execution.get("request_path") == case.expected_request_path if case.expected_request_path else True,
        "no_controlled_error": "controlled error" not in lower_answer and "traceback" not in lower_answer,
    }


def _expected_payload(case: AgentQACase) -> Dict[str, Any]:
    return {
        "expected_tools": case.expected_tools,
        "forbidden_tools": case.forbidden_tools,
        "expected_keywords": case.expected_keywords,
        "requires_citation": case.requires_citation,
        "requires_pending_confirmation": case.requires_pending_confirmation,
        "expected_request_path": case.expected_request_path,
    }


def _actual_payload(response: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "answer": response.get("answer", ""),
        "citations": response.get("citations", []),
        "pending_confirmation": response.get("pending_confirmation"),
        "tool_calls": [
            {"name": call.get("name"), "args": call.get("args", {})}
            for call in response.get("tool_calls", [])
        ],
        "execution": response.get("execution", {}),
    }


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _case_pool() -> List[AgentQACase]:
    cases: List[AgentQACase] = []
    routes = [
        ("SFO", "LAX"),
        ("JFK", "ORD"),
        ("SEA", "MIA"),
        ("LAS", "LAX"),
        ("BOS", "SFO"),
    ]
    periods = [
        ("next month", "next_month"),
        ("this year", "this_year"),
        ("next year", "next_year"),
        ("August", "month"),
    ]
    for dep, arr in routes:
        for label, _ in periods:
            cases.append(
                AgentQACase(
                    id=f"customer-search-{dep}-{arr}-{label.replace(' ', '-')}",
                    role="customer",
                    category="customer_search",
                    message=f"Find all flights from {dep} to {arr} {label}",
                    expected_tools=["search_flights"],
                    expected_keywords=[],
                    forbidden_tools=["create_booking_intent", "confirm_booking", "cancel_customer_ticket"],
                    expected_request_path="tool_routing",
                )
            )
            cases.append(
                AgentQACase(
                    id=f"customer-booking-prep-{dep}-{arr}-{label.replace(' ', '-')}",
                    role="customer",
                    category="bounded_booking",
                    message=f"Find the cheapest United flight from {dep} to {arr} {label} and prepare a booking.",
                    expected_tools=["search_flights"],
                    forbidden_tools=["confirm_booking", "cancel_customer_ticket"],
                )
            )

    cases.extend(
        [
            AgentQACase(
                id="customer-policy-refund",
                role="customer",
                category="policy_rag",
                message="Can I get a refund if my flight is cancelled?",
                expected_tools=["answer_policy_question"],
                expected_keywords=["refund"],
                requires_citation=True,
                expected_request_path="policy_rag",
            ),
            AgentQACase(
                id="customer-policy-baggage",
                role="customer",
                category="policy_rag",
                message="Show me refund policy and baggage policy",
                expected_tools=["answer_policy_question"],
                expected_keywords=["baggage", "refund"],
                requires_citation=True,
                expected_request_path="policy_rag",
            ),
            AgentQACase(
                id="customer-cancel-missing-ticket",
                role="customer",
                category="cancellation",
                message="Please cancel my flight",
                forbidden_tools=["cancel_customer_ticket"],
                expected_keywords=["ticket number"],
                expected_request_path="clarification",
            ),
            AgentQACase(
                id="customer-identity",
                role="customer",
                category="guardrail",
                message="what is my name?",
                forbidden_tools=["search_flights", "get_sales_report", "create_booking_intent"],
                expected_keywords=["testcustomer@nyu.edu"],
                expected_request_path="identity",
            ),
            AgentQACase(
                id="customer-out-of-scope",
                role="customer",
                category="guardrail",
                message="recommend me a Chinese restaurant",
                forbidden_tools=["search_flights", "get_customer_trips", "create_booking_intent"],
                expected_keywords=["I can only help"],
                expected_request_path="scope_fallback",
            ),
            AgentQACase(
                id="staff-sales",
                role="staff",
                category="staff_analytics",
                message="Show me the sales report for the last year",
                expected_tools=["get_sales_report"],
                expected_keywords=["sales"],
                forbidden_tools=["create_booking_intent", "confirm_booking", "cancel_customer_ticket"],
                expected_request_path="tool_routing",
            ),
            AgentQACase(
                id="staff-reviews",
                role="staff",
                category="staff_analytics",
                message="Which flights have the worst reviews?",
                expected_tools=["analyze_reviews"],
                expected_keywords=["review"],
                forbidden_tools=["create_booking_intent", "confirm_booking", "cancel_customer_ticket"],
                expected_request_path="tool_routing",
            ),
            AgentQACase(
                id="staff-route-performance",
                role="staff",
                category="staff_analytics",
                message="Which route has strong sales but poor reviews?",
                expected_tools=["get_route_performance"],
                expected_keywords=["route"],
                forbidden_tools=["create_booking_intent", "confirm_booking", "cancel_customer_ticket"],
            ),
            AgentQACase(
                id="staff-out-of-scope",
                role="staff",
                category="guardrail",
                message="what is the weather tomorrow?",
                forbidden_tools=["get_sales_report", "analyze_reviews", "get_route_performance"],
                expected_keywords=["I can only help"],
                expected_request_path="scope_fallback",
            ),
        ]
    )
    return cases
