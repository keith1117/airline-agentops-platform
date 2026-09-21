import argparse
import json
import math
import time
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from agent_service.config import settings as default_settings
from agent_service.db import ensure_agent_schema
from agent_service.eval_runner import _load_cases, run_eval_suite
from agent_service.rag import PolicyRAG
from agent_service.react_agent import ReActAgent


class RecordingAgent:
    def __init__(self, agent: ReActAgent, valid_citation_ids: set[str]) -> None:
        self.agent = agent
        self.valid_citation_ids = valid_citation_ids
        self.events: List[Dict[str, Any]] = []

    def customer_chat(self, session_id: str, customer_email: str, message: str) -> Dict[str, Any]:
        return self._record("customer", session_id, message, self.agent.customer_chat, session_id, customer_email, message)

    def staff_chat(
        self,
        session_id: str,
        staff_username: str,
        airline_name: str,
        message: str,
    ) -> Dict[str, Any]:
        return self._record(
            "staff",
            session_id,
            message,
            self.agent.staff_chat,
            session_id,
            staff_username,
            airline_name,
            message,
        )

    def _record(self, role: str, session_id: str, message: str, call, *args: Any) -> Dict[str, Any]:
        started = time.perf_counter()
        response = call(*args)
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        execution = response.get("execution") or {}
        citations = response.get("citations") or []
        self.events.append(
            {
                "role": role,
                "session_id": session_id,
                "message": message,
                "latency_ms": latency_ms,
                "tools": [item.get("name") for item in response.get("tool_calls", [])],
                "router_used": execution.get("router_used"),
                "retriever_used": execution.get("retriever_used"),
                "answer_mode_used": execution.get("answer_mode_used"),
                "request_path": execution.get("request_path"),
                "fallback_reason": execution.get("fallback_reason"),
                "citation_count": len(citations),
                "citations_grounded": all(
                    citation.get("chunk_id") in self.valid_citation_ids for citation in citations
                ),
                "answer": str(response.get("answer", ""))[:500],
            }
        )
        return response


def _nearest_rank(values: List[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 1)


def _mean_available(rows: List[Dict[str, Any]], key: str) -> float | None:
    values = [row[key] for row in rows if row.get(key) is not None]
    return round(sum(values) / len(values), 3) if values else None


def _write_markdown(path: Path, report: Dict[str, Any]) -> None:
    summary = report["summary"]
    citation_presence = summary["citation_presence_rate"]
    citation_presence_text = f"{citation_presence:.3f}" if citation_presence is not None else "n/a"
    citation_grounding = summary["citation_grounding_rate"]
    citation_grounding_text = f"{citation_grounding:.3f}" if citation_grounding is not None else "n/a"
    lines = [
        "# Live Model Evaluation",
        "",
        f"- Run ID: `{report['run_id']}`",
        f"- Model: `{report['configuration']['llm_model']}`",
        f"- Embedding model: `{report['configuration']['embedding_model']}`",
        f"- Suite: `{report['configuration']['suite']}` × {report['configuration']['repeats']} repeats",
        f"- Main trajectories: `{summary['total_trajectories']}`",
        f"- Task success: `{summary['passed_trajectories']}/{summary['total_trajectories']}` "
        f"(`{summary['task_success_rate']:.3f}`)",
        f"- Tool-call accuracy: `{summary['tool_call_accuracy']:.3f}`",
        f"- Citation presence: `{citation_presence_text}`",
        f"- Citation grounding: `{citation_grounding_text}`",
        f"- Fallback rate: `{summary['fallback_rate']:.3f}`",
        f"- Native-router trajectories: `{summary['native_router_trajectories']}`",
        f"- Embedding + grounded-LLM trajectories: `{summary['embedding_llm_trajectories']}`",
        f"- Live-path success: `{summary['live_path_passed']}/{summary['live_path_trajectories']}` "
        f"(`{summary['live_path_success_rate']:.3f}`)",
        f"- Main-trajectory latency: P50 `{summary['latency_ms']['p50']}` ms, "
        f"P95 `{summary['latency_ms']['p95']}` ms",
        "",
        "Latency includes local application and database work plus provider-dependent network and model time. "
        "Token usage and cost are not reported because the current client does not persist provider usage fields.",
        "",
        "## Repeats",
        "",
        "| Repeat | Passed | Task success | Tool accuracy | Citation presence | Fallback | Elapsed |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["repeats"]:
        repeat_citation = item["citation_presence_rate"]
        repeat_citation_text = f"{repeat_citation:.3f}" if repeat_citation is not None else "n/a"
        lines.append(
            f"| {item['repeat']} | {item['passed']}/{item['total']} | {item['task_success_rate']:.3f} | "
            f"{item['tool_call_accuracy']:.3f} | {repeat_citation_text} | "
            f"{item['fallback_rate']:.3f} | {item['elapsed_ms']} ms |"
        )
    if summary["failure_categories"]:
        lines.extend(["", "## Failure categories", ""])
        lines.extend(f"- `{name}`: {count}" for name, count in summary["failure_categories"].items())
    governance = [
        ("Multi-step task success", summary["multi_step_task_success_rate"]),
        ("Tool-order accuracy", summary["tool_order_accuracy"]),
        ("Unauthorized-call rejection", summary["unauthorized_call_rejection_rate"]),
        ("Confirmation-gate hit rate", summary["confirmation_gate_hit_rate"]),
    ]
    if any(value is not None for _, value in governance):
        lines.extend(["", "## Governance metrics", ""])
        lines.extend(f"- {label}: `{value:.3f}`" for label, value in governance if value is not None)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run repeated, forced live-model Agent evaluations.")
    parser.add_argument("--suite", default="default")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--report-dir", default="logs/live_model_eval")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    if args.repeats < 1:
        raise SystemExit("--repeats must be at least 1")

    settings = replace(
        default_settings,
        tool_router_mode="native",
        rag_retriever_mode="embedding",
        policy_answer_mode="llm",
    )
    if not settings.llm_api_key or not settings.embedding_api_key:
        raise SystemExit("LLM_API_KEY and EMBEDDING_API_KEY must be configured for live evaluation.")

    suite_path = Path("eval") / f"{args.suite}.jsonl"
    cases = _load_cases(suite_path)
    ensure_agent_schema()
    rag = PolicyRAG(settings.rag_policy_path, settings=settings)
    valid_citation_ids = {chunk["chunk_id"] for chunk in rag.chunks}
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    repeats = []
    all_cases = []
    failure_categories: Counter[str] = Counter()

    for repeat_index in range(1, args.repeats + 1):
        recorder = RecordingAgent(ReActAgent(rag, settings=settings), valid_citation_ids)
        started = time.perf_counter()
        result = run_eval_suite(args.suite, recorder)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        failed = {item["id"]: item for item in result["failed_cases"]}
        main_events = [event for event in recorder.events if "-setup-" not in event["session_id"]]
        if len(main_events) != len(cases):
            raise RuntimeError(f"Expected {len(cases)} main events, recorded {len(main_events)}.")
        for case, event in zip(cases, main_events):
            event["repeat"] = repeat_index
            event["case_id"] = case.get("id")
            event["passed"] = case.get("id") not in failed
            event["failure_types"] = failed.get(case.get("id"), {}).get("failure_types", [])
            failure_categories.update(event["failure_types"])
            all_cases.append(event)
        repeats.append(
            {
                "repeat": repeat_index,
                "total": result["total"],
                "passed": result["passed"],
                "task_success_rate": result["task_success_rate"],
                "tool_call_accuracy": result["tool_call_accuracy"],
                "citation_presence_rate": result["citation_presence_rate"]
                if result["metric_counts"]["citation_checks"]
                else None,
                "fallback_rate": result["fallback_rate"],
                "multi_step_task_success_rate": result["multi_step_task_success_rate"],
                "tool_order_accuracy": result["tool_order_accuracy"],
                "unauthorized_call_rejection_rate": result["unauthorized_call_rejection_rate"],
                "confirmation_gate_hit_rate": result["confirmation_gate_hit_rate"],
                "elapsed_ms": elapsed_ms,
                "failed_cases": sorted(failed),
            }
        )

    total = len(all_cases)
    passed = sum(item["passed"] for item in all_cases)
    live_cases = [
        item
        for item in all_cases
        if item["router_used"] == "native"
        or (item["retriever_used"] == "embedding" and item["answer_mode_used"] == "llm")
    ]
    cited_cases = [item for item in all_cases if item["citation_count"]]
    summary = {
        "total_trajectories": total,
        "passed_trajectories": passed,
        "task_success_rate": round(passed / total, 3),
        "tool_call_accuracy": round(sum(item["tool_call_accuracy"] for item in repeats) / len(repeats), 3),
        "citation_presence_rate": _mean_available(repeats, "citation_presence_rate"),
        "citation_grounding_rate": round(
            sum(item["citations_grounded"] for item in cited_cases) / len(cited_cases), 3
        )
        if cited_cases
        else None,
        "fallback_rate": round(sum(bool(item["fallback_reason"]) for item in all_cases) / total, 3),
        "multi_step_task_success_rate": _mean_available(repeats, "multi_step_task_success_rate"),
        "tool_order_accuracy": _mean_available(repeats, "tool_order_accuracy"),
        "unauthorized_call_rejection_rate": _mean_available(repeats, "unauthorized_call_rejection_rate"),
        "confirmation_gate_hit_rate": _mean_available(repeats, "confirmation_gate_hit_rate"),
        "native_router_trajectories": sum(item["router_used"] == "native" for item in all_cases),
        "embedding_llm_trajectories": sum(
            item["retriever_used"] == "embedding" and item["answer_mode_used"] == "llm"
            for item in all_cases
        ),
        "live_path_trajectories": len(live_cases),
        "live_path_passed": sum(item["passed"] for item in live_cases),
        "live_path_success_rate": round(sum(item["passed"] for item in live_cases) / len(live_cases), 3)
        if live_cases
        else None,
        "latency_ms": {
            "p50": _nearest_rank([item["latency_ms"] for item in all_cases], 0.50),
            "p95": _nearest_rank([item["latency_ms"] for item in all_cases], 0.95),
            "max": max(item["latency_ms"] for item in all_cases),
        },
        "failure_categories": dict(sorted(failure_categories.items())),
    }
    report = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "configuration": {
            "suite": args.suite,
            "repeats": args.repeats,
            "llm_model": settings.llm_model,
            "embedding_model": settings.embedding_model,
            "tool_router_mode": settings.tool_router_mode,
            "rag_retriever_mode": settings.rag_retriever_mode,
            "policy_answer_mode": settings.policy_answer_mode,
        },
        "summary": summary,
        "repeats": repeats,
        "cases": all_cases,
    }
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"live_model_eval_{run_id}.json"
    markdown_path = report_dir / f"live_model_eval_{run_id}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_markdown(markdown_path, report)
    print(json.dumps({"report": str(json_path), "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
