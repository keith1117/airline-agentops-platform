"""Persistent human decisions. Transaction effects and audit events commit together."""
import json
import uuid
from datetime import date

from .db import get_conn
from .tools.customer_tools import cancel_customer_ticket, preview_customer_ticket_cancellation


ACTION_DDL = [
    """CREATE TABLE IF NOT EXISTS agent_actions (
        id CHAR(32) PRIMARY KEY,
        customer_email VARCHAR(100) NOT NULL,
        airline_name VARCHAR(100) NOT NULL,
        session_id VARCHAR(80),
        kind VARCHAR(30) NOT NULL,
        status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
        payload JSON NOT NULL,
        result JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        INDEX action_owner_status (customer_email, status),
        INDEX action_airline_status (airline_name, status)
    )""",
    """CREATE TABLE IF NOT EXISTS agent_action_events (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        action_id CHAR(32) NOT NULL,
        actor VARCHAR(120) NOT NULL,
        event VARCHAR(40) NOT NULL,
        detail JSON NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (action_id) REFERENCES agent_actions(id)
    )""",
    """CREATE TABLE IF NOT EXISTS ticket_id_allocator (
        id INT PRIMARY KEY,
        next_id INT NOT NULL
    )""",
    "INSERT IGNORE INTO ticket_id_allocator VALUES (1, 1)",
]


class ActionError(ValueError):
    pass


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


def _event(cur, action_id, actor, event, detail=None):
    cur.execute(
        "INSERT INTO agent_action_events(action_id, actor, event, detail) VALUES(%s,%s,%s,%s)",
        (action_id, actor, event, json.dumps(detail or {}, default=str)),
    )


def _transition(cur, action, actor, status, result=None):
    cur.execute("UPDATE agent_actions SET status=%s, result=%s WHERE id=%s",
                (status, json.dumps(result or {}, default=str), action["id"]))
    _event(cur, action["id"], actor, status, result)


def _locked(cur, action_id, customer_email):
    cur.execute("SELECT *, expires_at <= CURRENT_TIMESTAMP AS expired FROM agent_actions "
                "WHERE id=%s AND customer_email=%s FOR UPDATE", (action_id, customer_email))
    action = cur.fetchone()
    if not action:
        raise ActionError("Action not found for your account.")
    action["payload"] = _json(action["payload"])
    action["result"] = _json(action["result"]) or {}
    return action


def _pending(cur, action, customer_email):
    if action["status"] not in {"PENDING", "CHECKOUT_STARTED"}:
        raise ActionError(f"This action is {action['status'].lower()}. Request a new preview.")
    if action["expired"]:
        _transition(cur, action, customer_email, "EXPIRED")
        return False
    return True


def create_action(customer_email, kind, payload, session_id=None):
    if kind not in {"BOOKING_HANDOFF", "CANCELLATION"}:
        raise ActionError("Unsupported action.")
    # Persist only backend business fields, never payment fields or model reasoning.
    fields = {"airline_name", "flight_number", "departure_date_time", "departure_airport",
              "arrival_airport", "base_price", "ticket_id", "flight_status",
              "cancellation_fee", "refund_amount", "policy_code"}
    payload = {k: v for k, v in payload.items() if k in fields and v is not None}
    if not payload.get("airline_name") or not payload.get("departure_date_time"):
        raise ActionError("The action needs an exact flight.")
    action_id = uuid.uuid4().hex
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO agent_actions(id, customer_email, airline_name, session_id, kind, payload, expires_at) "
                        "VALUES(%s,%s,%s,%s,%s,%s,DATE_ADD(CURRENT_TIMESTAMP, INTERVAL 30 MINUTE))",
                        (action_id, customer_email, payload["airline_name"], session_id, kind,
                         json.dumps(payload, default=str)))
            _event(cur, action_id, customer_email, "PENDING", {"kind": kind})
        conn.commit()
        return action_id
    finally:
        conn.close()


def record_handoffs(result, customer_email, session_id):
    for key, kind in (("pending_booking_search", "BOOKING_HANDOFF"), ("pending_cancellation", "CANCELLATION")):
        if result.get(key):
            result[key]["action_id"] = create_action(customer_email, kind, result[key], session_id)
    return result


def create_cancellation(customer_email, ticket_id):
    preview = preview_customer_ticket_cancellation(customer_email, ticket_id)
    if preview.get("error") or not preview.get("confirmation_required"):
        raise ActionError(preview.get("error") or "This ticket has already been cancelled.")
    return create_action(customer_email, "CANCELLATION", preview)


def list_actions(*, customer_email=None, airline_name=None, status=""):
    if not customer_email and not airline_name:
        raise ActionError("An account or airline scope is required.")
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            scope, owner = ("customer_email", customer_email) if customer_email else ("airline_name", airline_name)
            # Expiry is a stored state transition with an audit record, scoped to this viewer.
            cur.execute(f"SELECT id FROM agent_actions WHERE {scope}=%s "
                        "AND status IN ('PENDING','CHECKOUT_STARTED') AND expires_at<=CURRENT_TIMESTAMP FOR UPDATE", (owner,))
            for row in cur.fetchall():
                _transition(cur, row, "system", "EXPIRED")
            where = f"{scope}=%s"
            args = [owner]
            if status:
                where += " AND status=%s"
                args.append(status)
            cur.execute(f"SELECT * FROM agent_actions WHERE {where} ORDER BY created_at DESC, id DESC LIMIT 100", tuple(args))
            actions = list(cur.fetchall())
            for action in actions:
                action["payload"] = _json(action["payload"])
                action["result"] = _json(action["result"]) or {}
                cur.execute("SELECT actor, event, detail, created_at FROM agent_action_events "
                            "WHERE action_id=%s ORDER BY id", (action["id"],))
                action["events"] = cur.fetchall()
        conn.commit()
        return actions
    finally:
        conn.close()


def decide_action(action_id, customer_email, decision):
    if decision not in {"reject", "checkout", "confirm"}:
        raise ActionError("Unsupported decision.")
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            action = _locked(cur, action_id, customer_email)
            if action["status"] == "CONFIRMED" and decision == "confirm":
                return action["result"]
            if not _pending(cur, action, customer_email):
                conn.commit()
                raise ActionError("This preview expired. Request a new preview.")
            if decision == "reject":
                result = {"message": "Action rejected. No transaction was executed."}
                _transition(cur, action, customer_email, "REJECTED", result)
            elif decision == "checkout":
                if action["kind"] != "BOOKING_HANDOFF":
                    raise ActionError("Only booking handoffs can start checkout.")
                result = action["payload"]
                if action["status"] != "CHECKOUT_STARTED":
                    _transition(cur, action, customer_email, "CHECKOUT_STARTED")
            else:
                if action["kind"] != "CANCELLATION":
                    raise ActionError("Complete bookings on the Search Flights checkout page.")
                result = cancel_customer_ticket(customer_email, int(action["payload"]["ticket_id"]),
                                                connection=conn, expected_preview=action["payload"])
                _transition(cur, action, customer_email, "FAILED" if result.get("error") else "CONFIRMED", result)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def checkout_action(action_id, customer_email):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            action = _locked(cur, action_id, customer_email)
            if action["kind"] != "BOOKING_HANDOFF" or action["status"] != "CHECKOUT_STARTED" or action["expired"]:
                raise ActionError("Start a valid checkout from Pending Actions or Search Flights.")
        return action
    finally:
        conn.close()


def purchase_action(action_id, customer_email, payment):
    """Manual checkout only: lock action, flight and ID allocator before issuing one mock ticket."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            action = _locked(cur, action_id, customer_email)
            if action["kind"] != "BOOKING_HANDOFF":
                raise ActionError("This action is not a booking.")
            if action["status"] == "CONFIRMED":
                return action["result"]
            if not _pending(cur, action, customer_email):
                conn.commit()
                raise ActionError("This checkout expired. Start a new checkout.")
            if action["status"] != "CHECKOUT_STARTED":
                raise ActionError("Review the flight on the Search Flights checkout page first.")
            flight = action["payload"]
            key = (flight["airline_name"], flight["flight_number"], flight["departure_date_time"])
            cur.execute("SELECT f.*, a.seats, f.departure_date_time<=CURRENT_TIMESTAMP AS departed "
                        "FROM Flight f JOIN Airplane a ON a.airline_name=f.airline_name AND a.id_number=f.airplane_id_number "
                        "WHERE f.airline_name=%s AND f.flight_number=%s AND f.departure_date_time=%s FOR UPDATE", key)
            current = cur.fetchone()
            error = None
            if not current or current["status"] == "CANCELLED" or current["departed"]:
                error = "Flight is no longer bookable."
            elif "base_price" in flight and float(flight["base_price"]) != float(current["base_price"]):
                error = "The fare changed. Start a new checkout to review the current price."
            else:
                cur.execute("SELECT COUNT(*) AS sold FROM Ticket t LEFT JOIN ticket_cancellations c "
                            "ON c.ticket_id=t.ticket_ID AND c.customer_email=t.customer_email "
                            "WHERE t.airline_name=%s AND t.flight_number=%s AND t.departure_date_time=%s AND c.id IS NULL", key)
                if cur.fetchone()["sold"] >= current["seats"]:
                    error = "Flight is sold out."
            if error:
                result = {"error": error}
                _transition(cur, action, customer_email, "FAILED", result)
                conn.commit()
                return result
            cur.execute("SELECT name FROM Customer WHERE email=%s", (customer_email,))
            customer = cur.fetchone()
            norm = lambda value: " ".join(str(value or "").split()).lower()
            if not customer or norm(payment.get("name_on_card")) != norm(customer["name"]):
                raise ActionError("The name on the card must match the account name.")
            number = str(payment.get("card_number") or "")
            if not number.isascii() or not number.isdigit() or not 13 <= len(number) <= 19:
                raise ActionError("Invalid card number.")
            try:
                expiry = date.fromisoformat(payment.get("expiration_date", ""))
            except ValueError:
                raise ActionError("Enter a valid expiration date.") from None
            cur.execute("SELECT CURRENT_DATE AS today")
            if expiry < cur.fetchone()["today"] or payment.get("card_type") not in {"Credit", "Debit"}:
                raise ActionError("Use an unexpired Credit or Debit card.")
            cur.execute("SELECT next_id FROM ticket_id_allocator WHERE id=1 FOR UPDATE")
            allocated = cur.fetchone()["next_id"]
            cur.execute("SELECT COALESCE(MAX(ticket_id),0)+1 AS next_id FROM "
                        "(SELECT ticket_ID AS ticket_id FROM Ticket UNION SELECT ticket_id FROM ticket_cancellations) ids")
            ticket_id = max(allocated, cur.fetchone()["next_id"])
            cur.execute("UPDATE ticket_id_allocator SET next_id=%s WHERE id=1", (ticket_id + 1,))
            cur.execute("INSERT INTO Ticket(ticket_ID, customer_email, airline_name, flight_number, departure_date_time, "
                        "card_type, card_number, name_on_card, expiration_date, purchase_date_time) "
                        "VALUES(%s,%s,%s,%s,%s,%s,'MOCK-PAYMENT',%s,%s,CURRENT_TIMESTAMP)",
                        (ticket_id, customer_email, *key, payment["card_type"], customer["name"], expiry))
            cur.execute("SELECT t.ticket_ID FROM Ticket t LEFT JOIN ticket_cancellations c "
                        "ON c.ticket_id=t.ticket_ID AND c.customer_email=t.customer_email "
                        "WHERE t.ticket_ID=%s AND t.customer_email=%s AND t.departure_date_time>CURRENT_TIMESTAMP AND c.id IS NULL",
                        (ticket_id, customer_email))
            if not cur.fetchone():
                raise ActionError("The ticket is not visible in My Flights; purchase rolled back.")
            result = {"ticket_id": ticket_id, "message": f"Ticket purchased (#{ticket_id})"}
            _transition(cur, action, customer_email, "CONFIRMED", result)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
