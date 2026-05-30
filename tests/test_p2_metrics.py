from agent_service.metrics import MetricsCollector
from agent_service.main import _with_tool_count


def test_metrics_collector_records_request_summary(tmp_path):
    log_path = tmp_path / "metrics.jsonl"
    collector = MetricsCollector(log_path=str(log_path))

    collector.record_request(
        endpoint="/api/agent/customer/chat",
        method="POST",
        status_code=200,
        latency_ms=25,
        role="customer",
        tool_count=2,
        error=False,
    )
    collector.record_request(
        endpoint="/api/agent/customer/chat",
        method="POST",
        status_code=500,
        latency_ms=75,
        role="customer",
        tool_count=0,
        error=True,
    )

    snapshot = collector.snapshot()

    assert snapshot["total_requests"] == 2
    assert snapshot["error_count"] == 1
    assert snapshot["endpoints"]["POST /api/agent/customer/chat"]["count"] == 2
    assert snapshot["endpoints"]["POST /api/agent/customer/chat"]["avg_latency_ms"] == 50
    assert snapshot["roles"]["customer"]["tool_calls"] == 2
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 2


def test_tool_count_response_header_serializes_agent_payload():
    response = _with_tool_count({"answer": "ok", "tool_calls": [{"name": "search_flights"}]})

    assert response.headers["X-Agent-Tool-Count"] == "1"
    assert response.status_code == 200
