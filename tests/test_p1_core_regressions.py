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
