from agent_service.react_agent import ReActAgent
from agent_service.tools import customer_tools


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
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def test_get_customer_trips_only_queries_upcoming_uncancelled_trips(monkeypatch):
    connection = _FakeConnection()
    monkeypatch.setattr(customer_tools, "get_conn", lambda: connection)

    result = customer_tools.get_customer_trips("customer@example.com")

    normalized_sql = " ".join(connection.cursor_instance.sql.split())
    assert "WHERE t.customer_email=%s" in normalized_sql
    assert "f.departure_date_time >= NOW()" in normalized_sql
    assert "c.id IS NULL" in normalized_sql
    assert "ORDER BY f.departure_date_time ASC" in normalized_sql
    assert connection.cursor_instance.args == ("customer@example.com",)
    assert result == {"trips": [], "count": 0}
    assert connection.closed is True


def test_empty_trip_result_is_described_as_no_upcoming_trips():
    assert ReActAgent._format_trips({"trips": [], "count": 0}) == (
        "You do not have any upcoming trips."
    )
