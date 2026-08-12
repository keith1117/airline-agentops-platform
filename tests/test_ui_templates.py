from datetime import datetime

import app as web_app
from app import app, present_agent_messages


def render_template(template_name, **context):
    with app.test_request_context("/"):
        return app.jinja_env.get_template(template_name).render(**context)


def test_public_and_auth_templates_render():
    for name in ["index.html", "login.html", "register_customer.html", "register_staff.html"]:
        html = render_template(name)
        assert "<form" in html or "Book smarter flights" in html


def test_homepage_uses_single_navigation_path_and_current_acceptance_copy():
    html = render_template("index.html")

    assert "Start Demo" not in html
    assert "Create Customer" not in html
    assert "53 passed" in html
    assert "Agent guardrails" in html
    assert 'value="SFO"' not in html
    assert 'value="LAX"' not in html


def test_customer_templates_render():
    flight = {
        "ticket_ID": 1,
        "airline_name": "United",
        "flight_number": "P0206",
        "departure_date_time": "2026-06-08 09:30:00",
        "arrival_date_time": "2026-06-08 11:05:00",
        "departure_airport": "SFO",
        "arrival_airport": "LAX",
        "base_price": 420.0,
        "status": "ON_TIME",
    }
    review = {
        "airline_name": "United",
        "flight_number": "P0206",
        "departure_date_time": "2026-06-08 09:30:00",
        "rating": 5,
        "comment": "Great demo flight",
        "created_at": "2026-05-30 10:00:00",
    }

    home_html = render_template("customer_home.html", name="Test User", flights=[flight])
    assert "data-table" in home_html
    assert "Cancel Ticket" in home_html
    assert "Search Flights" in render_template("customer_search.html", rows=[flight], dep="SFO", arr="LAX", date="")
    assert "Great demo flight" in render_template("customer_reviews.html", rows=[review])


def test_staff_templates_render():
    flight = {
        "flight_number": "P0206",
        "departure_date_time": "2026-06-08 09:30:00",
        "arrival_date_time": "2026-06-08 11:05:00",
        "departure_airport": "SFO",
        "arrival_airport": "LAX",
        "status": "ON_TIME",
    }
    filters = {
        "period": "",
        "start_date": "",
        "end_date": "",
        "from_airport": "",
        "to_airport": "",
        "from_city": "",
        "to_city": "",
    }

    assert "Staff Dashboard" in render_template("staff_home.html", rows=[flight], filters=filters)
    assert "Tickets" in render_template("staff_reports.html", rows=[{"ym": "2026-05", "day": None, "tickets": 2}])
    assert "Create Flight" in render_template("staff_create_flight.html", rows=[flight])
    assert "Change Flight Status" in render_template("staff_change_status.html")
    assert "Add Airplane" in render_template("staff_add_airplane.html", airline="United")
    assert "Ratings Summary" in render_template(
        "staff_view_ratings.html",
        summary=[{"flight_number": "P0206", "departure_date_time": "2026-06-08 09:30:00", "avg_rating": 4.5, "cnt": 2}],
        comments=[],
    )
    assert "Customers" in render_template(
        "staff_customers.html",
        airline="United",
        flight_number="P0206",
        departure_date_time="2026-06-08 09:30:00",
        customers=[],
    )


def test_agent_templates_render_structured_messages():
    messages = present_agent_messages([
        {
            "role": "assistant",
            "content": "Sales report raw fallback",
            "meta": {
                "tables": [{"month": "2026-05", "tickets": 1, "estimated_revenue": 420.0}],
                "tool_calls": [{"name": "get_sales_report", "args": {"airline_name": "United"}, "result": {"count": 1}}],
            },
        },
        {
            "role": "assistant",
            "content": "Policy answer",
            "meta": {
                "citations": [{"section": "Refund Policy", "chunk_id": "policy-2"}],
                "tool_calls": [{"name": "answer_policy_question", "args": {"question": "refund"}, "result": {"citations": [1]}}],
            },
        },
        {
            "role": "assistant",
            "content": "Flight found",
            "meta": {
                "pending_booking_search": {
                    "airline_name": "United",
                    "flight_number": "P0206",
                    "departure_airport": "SFO",
                    "arrival_airport": "LAX",
                    "departure_date": "2026-06-08",
                    "departure_date_time": "2026-06-08 09:30:00",
                }
            },
        },
    ])

    customer = render_template("customer_agent.html", messages=messages, agent_url="http://agent:8001")
    staff = render_template("staff_copilot.html", messages=messages, airline="United", agent_url="http://agent:8001")

    assert "agent-table" in customer
    assert "citation-pill" in customer
    assert "Policy Center" in customer
    assert "Tool calls" not in customer
    assert "Confirm Mock Booking" not in customer
    assert "Book" in customer
    assert "#agent-bottom" in customer
    assert "agent-table" in staff
    assert "Tool calls" in staff
    assert "Policy Center" in staff
    assert "#agent-bottom" in staff


def test_customer_agent_does_not_show_book_button_for_multi_flight_result_without_handoff():
    messages = present_agent_messages([
        {
            "role": "assistant",
            "content": "Here are matching available flights.",
            "meta": {
                "tool_calls": [
                    {
                        "name": "search_flights",
                        "args": {"departure_airport": "SFO", "arrival_airport": "BOS"},
                        "result": {
                            "count": 2,
                            "flights": [
                                {
                                    "airline_name": "United",
                                    "flight_number": "UA100",
                                    "departure_airport": "SFO",
                                    "arrival_airport": "BOS",
                                    "departure_date_time": "2027-04-15 08:00:00",
                                    "arrival_date_time": "2027-04-15 09:15:00",
                                    "base_price": 231.51,
                                    "seats_left": 179,
                                    "status": "ON_TIME",
                                },
                                {
                                    "airline_name": "United",
                                    "flight_number": "UA900",
                                    "departure_airport": "SFO",
                                    "arrival_airport": "BOS",
                                    "departure_date_time": "2027-06-01 08:00:00",
                                    "arrival_date_time": "2027-06-01 16:30:00",
                                    "base_price": 355.98,
                                    "seats_left": 218,
                                    "status": "ON_TIME",
                                },
                            ],
                        },
                    }
                ]
            },
        }
    ])

    customer = render_template("customer_agent.html", messages=messages, agent_url="http://agent:8001")

    assert "Flight results" in customer
    assert "UA100" in customer
    assert "UA900" in customer
    assert "Continue booking" not in customer
    assert "<button type=\"submit\">Book</button>" not in customer


class _PurchaseCursor:
    def __init__(self):
        self.results = []
        self.executed = []
        self.inserted_ticket_id = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, args=()):
        self.executed.append((" ".join(sql.split()), args))
        normalized = " ".join(sql.split())
        if "SELECT status, departure_date_time FROM Flight" in normalized:
            self.results.append({"status": "ON_TIME", "departure_date_time": datetime(2027, 4, 15, 8, 0, 0)})
        elif "SELECT NOW() AS now_ts" in normalized:
            self.results.append({"now_ts": datetime(2026, 8, 12, 0, 0, 0)})
        elif "SELECT name FROM Customer" in normalized:
            self.results.append({"name": "Jon Snow"})
        elif "FROM ( SELECT ticket_ID AS ticket_id FROM Ticket UNION SELECT ticket_id FROM ticket_cancellations )" in normalized:
            self.results.append({"next_id": 910067})
        elif "INSERT INTO Ticket" in normalized:
            self.inserted_ticket_id = args[0]
        elif "WHERE t.customer_email=%s AND f.departure_date_time >= NOW() AND c.id IS NULL AND t.ticket_ID=%s" in normalized:
            self.results.append({"ticket_ID": args[1]})

    def fetchone(self):
        return self.results.pop(0) if self.results else None


class _PurchaseConnection:
    def __init__(self):
        self.cursor_instance = _PurchaseCursor()
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_customer_purchase_uses_non_reused_ticket_id_and_verifies_my_flights_visibility(monkeypatch):
    connection = _PurchaseConnection()
    monkeypatch.setattr(web_app, "conn", connection)
    monkeypatch.setattr(web_app, "ensure_agent_schema", lambda **kwargs: None)

    client = app.test_client()
    with client.session_transaction() as session:
        session.update({"role": "customer", "email": "jon@example.com", "display": "Jon Snow"})

    response = client.post(
        "/customer/purchase",
        data={
            "airline_name": "United",
            "flight_number": "SYN00048",
            "departure_date_time": "2027-04-15 08:00:00",
            "name_on_card": "Jon Snow",
            "card_type": "Credit",
            "card_number": "4111111111111111",
            "expiration_date": "2028-01-01",
        },
        follow_redirects=False,
    )

    next_id_sql = [sql for sql, _ in connection.cursor_instance.executed if "UNION SELECT ticket_id" in sql]
    visibility_sql = [sql for sql, _ in connection.cursor_instance.executed if "AND t.ticket_ID=%s" in sql]
    assert response.status_code == 302
    assert next_id_sql
    assert visibility_sql
    assert connection.cursor_instance.inserted_ticket_id == 910067
    assert connection.committed is True
    assert connection.rolled_back is False
