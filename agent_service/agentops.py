import json
from collections import Counter
from typing import Any, Dict, Iterable, List

from .db import get_conn
from .trace_export import _parse_execution


TRACE_SCAN_LIMIT = 1000
TRACE_PAGE_LIMIT = 200


def load_agentops_dashboard(
    metrics_snapshot: Dict[str, Any],
    *,
    role: str = "",
    request_path: str = "",
    runtime_mode: str = "",
    outcome: str = "",
    limit: int = 50,
) -> Dict[str, Any]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, session_id, role, principal, user_message, reasoning,
                       tool_calls, final_answer, latency_ms, error, created_at
                FROM agent_traces
                ORDER BY id DESC
                LIMIT %s
                """,
                (TRACE_SCAN_LIMIT,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return build_agentops_dashboard(
        rows,
        metrics_snapshot,
        role=role,
        request_path=request_path,
        runtime_mode=runtime_mode,
        outcome=outcome,
        limit=limit,
    )


def build_agentops_dashboard(
    rows: Iterable[Dict[str, Any]],
    metrics_snapshot: Dict[str, Any],
    *,
    role: str = "",
    request_path: str = "",
    runtime_mode: str = "",
    outcome: str = "",
    limit: int = 50,
) -> Dict[str, Any]:
    normalized = [_normalize_trace(row) for row in rows]
    filtered = [
        trace
        for trace in normalized
        if _matches_filters(
            trace,
            role=role,
            request_path=request_path,
            runtime_mode=runtime_mode,
            outcome=outcome,
        )
    ]
    page_limit = min(max(int(limit), 1), TRACE_PAGE_LIMIT)
    return {
        "summary": _summarize(filtered),
        "traces": filtered[:page_limit],
        "metrics": metrics_snapshot,
        "filters": {
            "role": role,
            "request_path": request_path,
            "runtime_mode": runtime_mode,
            "outcome": outcome,
            "limit": page_limit,
        },
        "filter_options": {
            "roles": _values(normalized, "role"),
            "request_paths": _values(normalized, "request_path"),
            "runtime_modes": _values(normalized, "runtime_mode_used"),
        },
        "scanned_traces": len(normalized),
        "returned_traces": min(len(filtered), page_limit),
    }


def _normalize_trace(row: Dict[str, Any]) -> Dict[str, Any]:
    execution = _parse_execution(row.get("reasoning") or "")
    tool_calls = _parse_tool_calls(row.get("tool_calls"))
    trajectory = execution.get("trajectory") if isinstance(execution.get("trajectory"), list) else []
    tools_used = [call.get("name", "unknown_tool") for call in tool_calls if isinstance(call, dict)]
    observed_steps = sum(1 for step in trajectory if isinstance(step, dict) and step.get("type") == "action")
    step_count = max(int(execution.get("step_count") or 0), observed_steps)
    fallback_reason = execution.get("fallback_reason")
    error = row.get("error")
    return {
        "id": row.get("id"),
        "session_id": row.get("session_id"),
        "role": row.get("role") or "unknown",
        "principal": row.get("principal") or "-",
        "user_message": row.get("user_message") or "",
        "final_answer": row.get("final_answer") or "",
        "created_at": str(row.get("created_at") or ""),
        "latency_ms": int(row.get("latency_ms") or 0),
        "request_path": execution.get("request_path") or "unknown",
        "runtime_mode_used": execution.get("runtime_mode_used") or "unknown",
        "router_used": execution.get("router_used") or "none",
        "tools_used": tools_used,
        "step_count": int(step_count or 0),
        "stop_reason": execution.get("stop_reason") or "unknown",
        "confirmation_required": bool(execution.get("confirmation_required")),
        "fallback_reason": fallback_reason,
        "error": str(error) if error else None,
        "outcome": "error" if error else ("fallback" if fallback_reason else "success"),
        "trajectory": [_normalize_step(step) for step in trajectory if isinstance(step, dict)],
    }


def _parse_tool_calls(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw or "[]")
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _normalize_step(step: Dict[str, Any]) -> Dict[str, str]:
    step_type = str(step.get("type") or "step")
    tool = str(step.get("tool") or step.get("action") or "")
    payload = step.get("content")
    if payload is None and "args" in step:
        payload = step.get("args")
    return {
        "type": step_type,
        "tool": tool,
        "display": _display_value(payload),
    }


def _display_value(value: Any, max_length: int = 1200) -> str:
    if isinstance(value, str):
        rendered = value
    else:
        rendered = json.dumps(value, ensure_ascii=False, default=str, indent=2)
    if len(rendered) <= max_length:
        return rendered
    return rendered[:max_length].rstrip() + "..."


def _matches_filters(
    trace: Dict[str, Any],
    *,
    role: str,
    request_path: str,
    runtime_mode: str,
    outcome: str,
) -> bool:
    return all(
        [
            not role or trace["role"] == role,
            not request_path or trace["request_path"] == request_path,
            not runtime_mode or trace["runtime_mode_used"] == runtime_mode,
            not outcome or trace["outcome"] == outcome,
        ]
    )


def _summarize(traces: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(traces)
    error_count = sum(1 for trace in traces if trace["error"])
    fallback_count = sum(1 for trace in traces if trace["fallback_reason"])
    confirmation_count = sum(1 for trace in traces if trace["confirmation_required"])
    return {
        "total_traces": total,
        "error_count": error_count,
        "fallback_count": fallback_count,
        "fallback_rate": _rate(fallback_count, total),
        "avg_latency_ms": _average(trace["latency_ms"] for trace in traces),
        "avg_steps": _average(trace["step_count"] for trace in traces),
        "confirmation_required_count": confirmation_count,
        "request_paths": _counter_rows(trace["request_path"] for trace in traces),
        "routers": _counter_rows(trace["router_used"] for trace in traces),
        "tools": _counter_rows(tool for trace in traces for tool in trace["tools_used"]),
    }


def _average(values: Iterable[int]) -> float:
    items = list(values)
    return round(sum(items) / len(items), 2) if items else 0


def _rate(value: int, total: int) -> float:
    return round(value / total, 3) if total else 0


def _counter_rows(values: Iterable[str]) -> List[Dict[str, Any]]:
    return [{"name": name, "count": count} for name, count in Counter(values).most_common()]


def _values(traces: List[Dict[str, Any]], field: str) -> List[str]:
    return sorted({str(trace[field]) for trace in traces if trace.get(field)})
