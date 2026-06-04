from datetime import date

from agent_service.config import Settings
from agent_service.rag import PolicyRAG
from agent_service.react_agent import ReActAgent
from agent_service.reporting import resolve_sales_window
from agent_service.tools import staff_tools
import app as web_app


class _FakeCursor:
    def __init__(self):
        self.sql = ""
        self.args = ()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, args):
        self.sql = sql
        self.args = args

    def fetchall(self):
        return []


class _FakeConnection:
    def __init__(self):
        self.cursor_instance = _FakeCursor()

    def cursor(self):
        return self.cursor_instance

    def close(self):
        pass


def test_sales_windows_use_complete_calendar_periods():
    today = date(2026, 6, 5)

    assert resolve_sales_window("this_month", today=today) == {
        "period": "this_month",
        "start_date": "2026-06-01",
        "end_date": "2026-06-06",
        "label": "This month to date (2026-06-01 to 2026-06-05)",
    }
    assert resolve_sales_window("this_year", today=today) == {
        "period": "this_year",
        "start_date": "2026-01-01",
        "end_date": "2026-06-06",
        "label": "This year to date (2026-01-01 to 2026-06-05)",
    }
    assert resolve_sales_window("last_month", today=today) == {
        "period": "last_month",
        "start_date": "2026-05-01",
        "end_date": "2026-06-01",
        "label": "Last month (2026-05-01 to 2026-05-31)",
    }
    assert resolve_sales_window("last_year", today=today) == {
        "period": "last_year",
        "start_date": "2025-01-01",
        "end_date": "2026-01-01",
        "label": "Last year (2025-01-01 to 2025-12-31)",
    }


def test_sales_report_tool_applies_resolved_start_and_end(monkeypatch):
    connection = _FakeConnection()
    monkeypatch.setattr(staff_tools, "get_conn", lambda: connection)
    monkeypatch.setattr(
        staff_tools,
        "resolve_sales_window",
        lambda period, start_date=None, end_date=None: {
            "period": period,
            "start_date": "2026-06-01",
            "end_date": "2026-07-01",
            "label": "This month (2026-06-01 to 2026-06-30)",
        },
    )

    result = staff_tools.get_sales_report("United", period="this_month")

    normalized_sql = " ".join(connection.cursor_instance.sql.split())
    assert "t.purchase_date_time >= %s" in normalized_sql
    assert "t.purchase_date_time < %s" in normalized_sql
    assert connection.cursor_instance.args == ("United", "2026-06-01", "2026-07-01")
    assert result["period"] == "this_month"
    assert result["range_label"] == "This month (2026-06-01 to 2026-06-30)"


def test_staff_deterministic_sales_request_passes_requested_period(monkeypatch):
    settings = Settings(agent_router_mode="deterministic", agent_trace_enabled=False)
    agent = ReActAgent(PolicyRAG("docs/policies/airline_policy.md", settings=settings), settings=settings)
    monkeypatch.setattr(agent, "_trace", lambda *args, **kwargs: None)
    calls = []

    def fake_call(role, tool_name, **kwargs):
        calls.append((role, tool_name, kwargs))
        return {"rows": [], "count": 0, "range_label": "This month"}

    monkeypatch.setattr(agent.registry, "call", fake_call)
    response = agent.staff_chat(
        "sales-this-month",
        "alice",
        "United",
        "show me the sales report for this month",
    )

    assert calls == [
        ("staff", "get_sales_report", {"airline_name": "United", "period": "this_month"})
    ]
    assert "This month" in response["answer"]


def test_staff_llm_plan_passes_sales_period_to_tool(monkeypatch):
    settings = Settings(agent_router_mode="deterministic", agent_trace_enabled=False)
    agent = ReActAgent(PolicyRAG("docs/policies/airline_policy.md", settings=settings), settings=settings)
    calls = []

    def fake_call(role, tool_name, **kwargs):
        calls.append((role, tool_name, kwargs))
        return {"rows": [], "count": 0, "range_label": "This year to date"}

    monkeypatch.setattr(agent.registry, "call", fake_call)
    result = agent._execute_staff_plan(
        {"tool": "get_sales_report", "args": {"period": "this_year"}},
        "show me the sales report for this year",
        "United",
        [],
        agent._execution(),
    )

    assert calls == [
        ("staff", "get_sales_report", {"airline_name": "United", "period": "this_year"})
    ]
    assert "This year to date" in result["answer"]


def test_manual_last_month_report_uses_shared_calendar_window(monkeypatch):
    connection = _FakeConnection()
    connection.cursor_instance.fetchall = lambda: [{"ym": "2026-05", "tickets": 2}]
    monkeypatch.setattr(web_app, "conn", connection)
    monkeypatch.setattr(
        web_app,
        "resolve_sales_window",
        lambda period, start_date=None, end_date=None: {
            "period": "last_month",
            "start_date": "2026-05-01",
            "end_date": "2026-06-01",
            "label": "Last month (2026-05-01 to 2026-05-31)",
        },
    )

    client = web_app.app.test_client()
    with client.session_transaction() as session:
        session.update({"role": "staff", "username": "alice", "airline": "United"})
    response = client.post("/staff/reports", data={"mode": "last_month"})

    assert response.status_code == 200
    assert connection.cursor_instance.args == ("United", "2026-05-01", "2026-06-01")
    assert b"Last month (2026-05-01 to 2026-05-31)" in response.data
