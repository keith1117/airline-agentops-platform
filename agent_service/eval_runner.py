import json
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


def run_eval_suite(suite_name: str, agent) -> Dict[str, Any]:
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
    for idx, case in enumerate(cases, start=1):
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

        answer = resp.get("answer", "")
        ok_keyword = all(keyword.lower() in answer.lower() for keyword in _expected_keywords(case))

        if case.get("requires_citation"):
            citation_checks += 1
            ok_citation = bool(resp.get("citations"))
            citation_checks_passed += int(ok_citation)
        else:
            ok_citation = True

        ok = ok_tool and ok_keyword and ok_citation
        passed += int(ok)
        results.append(
            {
                "id": case.get("id", idx),
                "passed": ok,
                "checks": {
                    "tools": ok_tool,
                    "keywords": ok_keyword,
                    "citations": ok_citation,
                },
                "tools": tool_names,
                "answer": answer[:300],
            }
        )
    total = len(results) or 1
    tool_denominator = tool_checks or 1
    citation_denominator = citation_checks or 1
    return {
        "suite": suite_name,
        "total": len(results),
        "passed": passed,
        "task_success_rate": round(passed / total, 3),
        "tool_call_accuracy": round(tool_checks_passed / tool_denominator, 3),
        "citation_presence_rate": round(citation_checks_passed / citation_denominator, 3),
        "average_steps": round(total_steps / total, 2),
        "failed_cases": [item for item in results if not item["passed"]],
    }
