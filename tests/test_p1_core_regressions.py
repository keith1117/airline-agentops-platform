import os

import pytest

from agent_service.db import ensure_agent_schema, get_conn
from agent_service.rag import PolicyRAG
from agent_service.react_agent import ReActAgent
from scripts.seed_p0_demo import first_day_next_month, main as seed_p0_demo


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_P1_CORE") != "1",
    reason="Set RUN_P1_CORE=1 when local MySQL is available.",
)


@pytest.fixture()
def agent():
    ensure_agent_schema(retries=3)
    seed_p0_demo()
    return ReActAgent(PolicyRAG("docs/policies/airline_policy.md"))


def _p0_departure_time():
    from datetime import datetime, timedelta

    dep = datetime.combine(first_day_next_month() + timedelta(days=7), datetime.min.time()).replace(
        hour=9,
        minute=30,
    )
    return dep.strftime("%Y-%m-%d %H:%M:%S")


def test_policy_rag_no_context_falls_back_cleanly():
    result = PolicyRAG("docs/policies/airline_policy.md").query("Does the platform support quantum lounge mining rewards?")

    assert result["citations"] == []
    assert "cannot confirm" in result["answer"].lower()


def test_booking_confirmation_is_idempotent(agent):
    email = "p1core@nyu.edu"
    departure_time = _p0_departure_time()
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO Customer(email, name, password)
                VALUES(%s, 'P1 Core Tester', '1234')
                ON DUPLICATE KEY UPDATE name=VALUES(name)
                """,
                (email,),
            )
            cur.execute(
                """
                DELETE FROM booking_intents
                WHERE customer_email=%s AND airline_name='United' AND flight_number='P0206'
                  AND departure_date_time=%s
                """,
                (email, departure_time),
            )
            cur.execute(
                """
                DELETE FROM Ticket
                WHERE customer_email=%s AND airline_name='United' AND flight_number='P0206'
                  AND departure_date_time=%s
                """,
                (email, departure_time),
            )
        conn.commit()
    finally:
        conn.close()

    booking_resp = agent.customer_chat(
        "p1-core-idempotency",
        email,
        f"Book United flight P0206 at {departure_time}",
    )
    pending = booking_resp["pending_confirmation"]
    assert pending

    first = agent.confirm_booking(pending["booking_intent_id"], email, pending["idempotency_key"])
    second = agent.confirm_booking(pending["booking_intent_id"], email, pending["idempotency_key"])

    assert first["status"] == "CONFIRMED"
    assert second["status"] == "CONFIRMED"
    assert second["ticket_id"] == first["ticket_id"]

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM Ticket
                WHERE customer_email=%s AND airline_name='United' AND flight_number='P0206'
                  AND departure_date_time=%s
                """,
                (email, departure_time),
            )
            count = cur.fetchone()["cnt"]
    finally:
        conn.close()

    assert count == 1


def test_invalid_booking_idempotency_key_does_not_issue_ticket(agent):
    email = "p1core-invalid@nyu.edu"
    departure_time = _p0_departure_time()
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO Customer(email, name, password)
                VALUES(%s, 'P1 Invalid Tester', '1234')
                ON DUPLICATE KEY UPDATE name=VALUES(name)
                """,
                (email,),
            )
        conn.commit()
    finally:
        conn.close()

    booking_resp = agent.customer_chat(
        "p1-core-invalid-key",
        email,
        f"Book United flight P0206 at {departure_time}",
    )
    pending = booking_resp["pending_confirmation"]
    result = agent.confirm_booking(pending["booking_intent_id"], email, "wrong-key")

    assert result["status"] == "FAILED"
    assert "Invalid idempotency key" in result["message"]


def test_customer_flight_search_excludes_cancelled_inventory(agent):
    from datetime import datetime, timedelta

    dep = datetime.combine(first_day_next_month() + timedelta(days=9), datetime.min.time()).replace(hour=10)
    arr = dep + timedelta(hours=2)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO Flight(airline_name, flight_number, departure_date_time, arrival_date_time,
                                   base_price, departure_airport, arrival_airport, airplane_id_number, status)
                VALUES('United', 'P0CAN', %s, %s, 100.00, 'SFO', 'LAX', 'P0-737', 'CANCELLED')
                ON DUPLICATE KEY UPDATE status=VALUES(status), base_price=VALUES(base_price)
                """,
                (dep, arr),
            )
        conn.commit()
    finally:
        conn.close()

    resp = agent.customer_chat(
        "p1-core-no-cancelled",
        "testcustomer@nyu.edu",
        "Find flights from SFO to LAX next month",
    )

    flights = []
    for call in resp["tool_calls"]:
        if call["name"] == "search_flights":
            flights.extend(call["result"].get("flights", []))
    assert flights
    assert all(flight["status"] != "CANCELLED" for flight in flights)
    assert "P0CAN" not in resp["answer"]


def _insert_customer_ticket(email, ticket_id, flight_number, departure_time):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO Customer(email, name, password)
                VALUES(%s, 'Cancellation Tester', '1234')
                ON DUPLICATE KEY UPDATE name=VALUES(name)
                """,
                (email,),
            )
            cur.execute("DELETE FROM ticket_cancellations WHERE ticket_id=%s", (ticket_id,))
            cur.execute("DELETE FROM Ticket WHERE ticket_ID=%s", (ticket_id,))
            cur.execute(
                """
                INSERT INTO Ticket(
                    ticket_ID, customer_email, airline_name, flight_number, departure_date_time,
                    card_type, card_number, name_on_card, expiration_date, purchase_date_time
                )
                VALUES(%s,%s,'United',%s,%s,'Credit','TEST-CANCEL','Cancellation Tester',
                       DATE_ADD(CURDATE(), INTERVAL 2 YEAR),NOW())
                """,
                (ticket_id, email, flight_number, departure_time),
            )
        conn.commit()
    finally:
        conn.close()


def test_cancel_customer_ticket_charges_large_fee_for_on_time_ticket(agent):
    from agent_service.tools.customer_tools import cancel_customer_ticket

    email = "cancel-on-time@nyu.edu"
    ticket_id = 910060
    departure_time = _p0_departure_time()
    _insert_customer_ticket(email, ticket_id, "P0206", departure_time)

    result = cancel_customer_ticket(email, ticket_id)
    second = cancel_customer_ticket(email, ticket_id)

    assert result["cancelled"] is True
    assert result["flight_status"] == "ON_TIME"
    assert result["policy_code"] == "STANDARD_ON_TIME"
    assert result["cancellation_fee"] == 252.0
    assert result["refund_amount"] == 168.0
    assert second["already_cancelled"] is True
    assert second["refund_amount"] == 168.0


def test_cancel_customer_ticket_reduces_fee_for_delayed_ticket(agent):
    from datetime import datetime, timedelta

    from agent_service.tools.customer_tools import cancel_customer_ticket
    from scripts.seed_p0_demo import first_day_next_month

    email = "cancel-delayed@nyu.edu"
    ticket_id = 910061
    dep = datetime.combine(first_day_next_month() + timedelta(days=10), datetime.min.time()).replace(hour=15)
    arr = dep + timedelta(hours=2)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO Flight(airline_name, flight_number, departure_date_time, arrival_date_time,
                                   base_price, departure_airport, arrival_airport, airplane_id_number, status)
                VALUES('United', 'P0DLY', %s, %s, 500.00, 'SFO', 'LAX', 'P0-737', 'DELAYED')
                ON DUPLICATE KEY UPDATE status=VALUES(status), base_price=VALUES(base_price)
                """,
                (dep, arr),
            )
        conn.commit()
    finally:
        conn.close()
    _insert_customer_ticket(email, ticket_id, "P0DLY", dep.strftime("%Y-%m-%d %H:%M:%S"))

    result = cancel_customer_ticket(email, ticket_id)

    assert result["cancelled"] is True
    assert result["flight_status"] == "DELAYED"
    assert result["policy_code"] == "DELAYED_REDUCED_FEE"
    assert result["cancellation_fee"] == 75.0
    assert result["refund_amount"] == 425.0
