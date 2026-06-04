import hashlib
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional

from ..db import get_conn
from ..rag import PolicyRAG


def _serialize_rows(rows):
    out = []
    for row in rows:
        item = {}
        for key, value in row.items():
            item[key] = value.isoformat(sep=" ") if hasattr(value, "isoformat") else value
        out.append(item)
    return out


def _date_bounds(period: Optional[str], month: Optional[str] = None):
    if month:
        parsed = re.match(r"^(\d{4})-(\d{2})$", month)
        if parsed:
            year = int(parsed.group(1))
            month_num = int(parsed.group(2))
            if 1 <= month_num <= 12:
                first = date(year, month_num, 1)
                second = date(year + (month_num == 12), 1 if month_num == 12 else month_num + 1, 1)
                return first.isoformat(), second.isoformat()
    today = date.today()
    if period == "next_month":
        first = date(today.year + (today.month == 12), 1 if today.month == 12 else today.month + 1, 1)
        second = date(first.year + (first.month == 12), 1 if first.month == 12 else first.month + 1, 1)
        return first.isoformat(), second.isoformat()
    if period == "this_year":
        first = date(today.year, 1, 1)
        second = date(today.year + 1, 1, 1)
        return first.isoformat(), second.isoformat()
    if period == "next_year":
        first = date(today.year + 1, 1, 1)
        second = date(today.year + 2, 1, 1)
        return first.isoformat(), second.isoformat()
    return None, None


def search_flights(
    departure_airport: Optional[str] = None,
    arrival_airport: Optional[str] = None,
    airline_name: Optional[str] = None,
    flight_number: Optional[str] = None,
    travel_date: Optional[str] = None,
    month: Optional[str] = None,
    period: Optional[str] = None,
    max_price: Optional[float] = None,
    limit: int = 8,
) -> Dict[str, Any]:
    sql = """
        SELECT f.airline_name, f.flight_number, f.departure_date_time, f.arrival_date_time,
               f.base_price, f.departure_airport, f.arrival_airport, f.status,
               a.seats,
               COUNT(CASE WHEN c.id IS NULL THEN t.ticket_ID END) AS sold,
               (a.seats - COUNT(CASE WHEN c.id IS NULL THEN t.ticket_ID END)) AS seats_left
        FROM Flight f
        JOIN Airplane a
          ON a.airline_name=f.airline_name AND a.id_number=f.airplane_id_number
        LEFT JOIN Ticket t
          ON t.airline_name=f.airline_name
         AND t.flight_number=f.flight_number
         AND t.departure_date_time=f.departure_date_time
        LEFT JOIN ticket_cancellations c
          ON c.ticket_id=t.ticket_ID
         AND c.customer_email=t.customer_email
        WHERE f.departure_date_time >= NOW()
          AND f.status != 'CANCELLED'
    """
    args = []
    if departure_airport:
        sql += " AND f.departure_airport=%s"
        args.append(departure_airport.upper())
    if arrival_airport:
        sql += " AND f.arrival_airport=%s"
        args.append(arrival_airport.upper())
    if airline_name:
        sql += " AND f.airline_name=%s"
        args.append(airline_name)
    if flight_number:
        sql += " AND f.flight_number=%s"
        args.append(flight_number.upper())
    if travel_date and re.match(r"^\d{4}-\d{2}-\d{2}$", str(travel_date)):
        sql += " AND DATE(f.departure_date_time)=%s"
        args.append(travel_date)
    start, end = _date_bounds(period, month=month)
    if start and end:
        sql += " AND f.departure_date_time >= %s AND f.departure_date_time < %s"
        args.extend([start, end])
    if max_price is not None:
        sql += " AND f.base_price <= %s"
        args.append(max_price)
    sql += """
        GROUP BY f.airline_name, f.flight_number, f.departure_date_time,
                 f.arrival_date_time, f.base_price, f.departure_airport,
                 f.arrival_airport, f.status, a.seats
        HAVING seats_left > 0
        ORDER BY f.base_price, f.departure_date_time
        LIMIT %s
    """
    args.append(limit)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(args))
            rows = _serialize_rows(cur.fetchall())
        return {"flights": rows, "count": len(rows)}
    finally:
        conn.close()


def get_customer_trips(customer_email: str) -> Dict[str, Any]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.ticket_ID, f.airline_name, f.flight_number, f.departure_date_time,
                       f.arrival_date_time, f.departure_airport, f.arrival_airport, f.status
                FROM Ticket t
                JOIN Flight f
                  ON t.airline_name=f.airline_name
                 AND t.flight_number=f.flight_number
                 AND t.departure_date_time=f.departure_date_time
                LEFT JOIN ticket_cancellations c
                  ON c.ticket_id=t.ticket_ID
                 AND c.customer_email=t.customer_email
                WHERE t.customer_email=%s
                  AND f.departure_date_time >= NOW()
                  AND c.id IS NULL
                ORDER BY f.departure_date_time ASC
                LIMIT 20
                """,
                (customer_email,),
            )
            rows = _serialize_rows(cur.fetchall())
        return {"trips": rows, "count": len(rows)}
    finally:
        conn.close()


def get_customer_ticket(customer_email: str, ticket_id: int) -> Dict[str, Any]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.ticket_ID, f.airline_name, f.flight_number, f.departure_date_time,
                       f.arrival_date_time, f.departure_airport, f.arrival_airport, f.status
                FROM Ticket t
                JOIN Flight f
                  ON t.airline_name=f.airline_name
                 AND t.flight_number=f.flight_number
                 AND t.departure_date_time=f.departure_date_time
                WHERE t.customer_email=%s AND t.ticket_ID=%s
                LIMIT 1
                """,
                (customer_email, ticket_id),
            )
            row = cur.fetchone()
        return {"ticket": _serialize_rows([row])[0] if row else None}
    finally:
        conn.close()


def _cancellation_terms(status: str, base_price: Decimal):
    rates = {
        "CANCELLED": (Decimal("0.00"), "AIRLINE_CANCELLED_FULL_REFUND"),
        "DELAYED": (Decimal("0.15"), "DELAYED_REDUCED_FEE"),
        "ON_TIME": (Decimal("0.60"), "STANDARD_ON_TIME"),
    }
    fee_rate, policy_code = rates.get(status, rates["ON_TIME"])
    cancellation_fee = (base_price * fee_rate).quantize(Decimal("0.01"))
    refund_amount = (base_price - cancellation_fee).quantize(Decimal("0.01"))
    return cancellation_fee, refund_amount, policy_code


def _serialize_money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def _cancellation_result_from_row(row: Dict[str, Any], already_cancelled: bool = False) -> Dict[str, Any]:
    return {
        "cancelled": True,
        "already_cancelled": already_cancelled,
        "ticket_id": row["ticket_id"],
        "customer_email": row["customer_email"],
        "airline_name": row["airline_name"],
        "flight_number": row["flight_number"],
        "departure_date_time": row["departure_date_time"].isoformat(sep=" ")
        if hasattr(row["departure_date_time"], "isoformat")
        else str(row["departure_date_time"]),
        "flight_status": row["flight_status_at_cancellation"],
        "base_price": _serialize_money(row["base_price"]),
        "cancellation_fee": _serialize_money(row["cancellation_fee"]),
        "refund_amount": _serialize_money(row["refund_amount"]),
        "policy_code": row["policy_code"],
        "message": f"Ticket {row['ticket_id']} was already cancelled."
        if already_cancelled
        else f"Ticket {row['ticket_id']} was cancelled.",
    }


def preview_customer_ticket_cancellation(customer_email: str, ticket_id: int) -> Dict[str, Any]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM ticket_cancellations
                WHERE customer_email=%s AND ticket_id=%s
                LIMIT 1
                """,
                (customer_email, ticket_id),
            )
            existing = cur.fetchone()
            if existing:
                result = _cancellation_result_from_row(existing, already_cancelled=True)
                result.update({"preview": True, "confirmation_required": False})
                return result

            cur.execute(
                """
                SELECT t.ticket_ID, t.customer_email, f.airline_name, f.flight_number,
                       f.departure_date_time, f.arrival_date_time, f.departure_airport,
                       f.arrival_airport, f.status, f.base_price
                FROM Ticket t
                JOIN Flight f
                  ON t.airline_name=f.airline_name
                 AND t.flight_number=f.flight_number
                 AND t.departure_date_time=f.departure_date_time
                WHERE t.customer_email=%s AND t.ticket_ID=%s
                LIMIT 1
                """,
                (customer_email, ticket_id),
            )
            ticket = cur.fetchone()
            if not ticket:
                return {"error": f"I could not find ticket {ticket_id} for your account."}
            if ticket["departure_date_time"] <= datetime.now():
                return {"error": "This ticket cannot be cancelled because the flight has already departed."}

            base_price = Decimal(str(ticket["base_price"]))
            cancellation_fee, refund_amount, policy_code = _cancellation_terms(ticket["status"], base_price)
            return {
                "preview": True,
                "confirmation_required": True,
                "ticket_id": ticket["ticket_ID"],
                "customer_email": customer_email,
                "airline_name": ticket["airline_name"],
                "flight_number": ticket["flight_number"],
                "departure_airport": ticket["departure_airport"],
                "arrival_airport": ticket["arrival_airport"],
                "departure_date_time": ticket["departure_date_time"].isoformat(sep=" "),
                "flight_status": ticket["status"],
                "base_price": _serialize_money(base_price),
                "cancellation_fee": _serialize_money(cancellation_fee),
                "refund_amount": _serialize_money(refund_amount),
                "policy_code": policy_code,
                "message": "Cancellation preview ready. Confirm cancellation before this ticket is cancelled.",
            }
    finally:
        conn.close()


def cancel_customer_ticket(customer_email: str, ticket_id: int) -> Dict[str, Any]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM ticket_cancellations
                WHERE customer_email=%s AND ticket_id=%s
                LIMIT 1
                """,
                (customer_email, ticket_id),
            )
            existing = cur.fetchone()
            if existing:
                return _cancellation_result_from_row(existing, already_cancelled=True)

            cur.execute(
                """
                SELECT t.ticket_ID, t.customer_email, f.airline_name, f.flight_number,
                       f.departure_date_time, f.arrival_date_time, f.departure_airport,
                       f.arrival_airport, f.status, f.base_price
                FROM Ticket t
                JOIN Flight f
                  ON t.airline_name=f.airline_name
                 AND t.flight_number=f.flight_number
                 AND t.departure_date_time=f.departure_date_time
                WHERE t.customer_email=%s AND t.ticket_ID=%s
                LIMIT 1
                """,
                (customer_email, ticket_id),
            )
            ticket = cur.fetchone()
            if not ticket:
                return {"error": f"I could not find ticket {ticket_id} for your account."}
            if ticket["departure_date_time"] <= datetime.now():
                return {"error": "This ticket cannot be cancelled because the flight has already departed."}

            base_price = Decimal(str(ticket["base_price"]))
            cancellation_fee, refund_amount, policy_code = _cancellation_terms(ticket["status"], base_price)
            cur.execute(
                """
                INSERT INTO ticket_cancellations(
                    ticket_id, customer_email, airline_name, flight_number, departure_date_time,
                    flight_status_at_cancellation, base_price, cancellation_fee, refund_amount, policy_code
                )
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    ticket["ticket_ID"],
                    customer_email,
                    ticket["airline_name"],
                    ticket["flight_number"],
                    ticket["departure_date_time"],
                    ticket["status"],
                    base_price,
                    cancellation_fee,
                    refund_amount,
                    policy_code,
                ),
            )
        conn.commit()
        return {
            "cancelled": True,
            "already_cancelled": False,
            "ticket_id": ticket["ticket_ID"],
            "customer_email": customer_email,
            "airline_name": ticket["airline_name"],
            "flight_number": ticket["flight_number"],
            "departure_airport": ticket["departure_airport"],
            "arrival_airport": ticket["arrival_airport"],
            "departure_date_time": ticket["departure_date_time"].isoformat(sep=" "),
            "flight_status": ticket["status"],
            "base_price": _serialize_money(base_price),
            "cancellation_fee": _serialize_money(cancellation_fee),
            "refund_amount": _serialize_money(refund_amount),
            "policy_code": policy_code,
            "message": f"Ticket {ticket_id} was cancelled.",
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_booking_intent(
    customer_email: str,
    airline_name: str,
    flight_number: str,
    departure_date_time: str,
) -> Dict[str, Any]:
    idempotency = hashlib.sha256(
        f"{customer_email}:{airline_name}:{flight_number}:{departure_date_time}".encode("utf-8")
    ).hexdigest()[:32]
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT f.status, f.departure_date_time, a.seats,
                       COUNT(CASE WHEN c.id IS NULL THEN t.ticket_ID END) AS sold
                FROM Flight f
                JOIN Airplane a
                  ON a.airline_name=f.airline_name AND a.id_number=f.airplane_id_number
                LEFT JOIN Ticket t
                  ON t.airline_name=f.airline_name
                 AND t.flight_number=f.flight_number
                 AND t.departure_date_time=f.departure_date_time
                LEFT JOIN ticket_cancellations c
                  ON c.ticket_id=t.ticket_ID
                 AND c.customer_email=t.customer_email
                WHERE f.airline_name=%s AND f.flight_number=%s AND f.departure_date_time=%s
                GROUP BY f.status, f.departure_date_time, a.seats
                """,
                (airline_name, flight_number, departure_date_time),
            )
            flight = cur.fetchone()
            if not flight:
                return {"error": "Flight not found."}
            if flight["status"] == "CANCELLED":
                return {"error": "Cannot book a cancelled flight."}
            if flight["departure_date_time"] <= datetime.now():
                return {"error": "Cannot book a flight that has already departed."}
            if int(flight["sold"]) >= int(flight["seats"]):
                return {"error": "Cannot book because this flight is sold out."}
            cur.execute(
                """
                INSERT INTO booking_intents(
                    customer_email, airline_name, flight_number, departure_date_time,
                    status, idempotency_key
                )
                VALUES(%s,%s,%s,%s,'PENDING_CONFIRMATION',%s)
                ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)
                """,
                (customer_email, airline_name, flight_number, departure_date_time, idempotency),
            )
            intent_id = cur.lastrowid
        conn.commit()
        return {
            "booking_intent_id": intent_id,
            "customer_email": customer_email,
            "airline_name": airline_name,
            "flight_number": flight_number,
            "departure_date_time": departure_date_time,
            "status": "PENDING_CONFIRMATION",
            "idempotency_key": idempotency,
        }
    finally:
        conn.close()


def confirm_booking(booking_intent_id: int, customer_email: str, idempotency_key: str) -> Dict[str, Any]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM booking_intents WHERE id=%s AND customer_email=%s FOR UPDATE",
                (booking_intent_id, customer_email),
            )
            intent = cur.fetchone()
            if not intent:
                conn.rollback()
                return {"status": "FAILED", "message": "Booking intent not found."}
            if intent["idempotency_key"] != idempotency_key:
                conn.rollback()
                return {"status": "FAILED", "message": "Invalid idempotency key."}
            if intent["status"] == "CONFIRMED":
                conn.rollback()
                return {
                    "status": "CONFIRMED",
                    "ticket_id": intent["ticket_id"],
                    "message": "Booking was already confirmed.",
                }
            cur.execute(
                """
                SELECT f.status, f.departure_date_time, a.seats
                FROM Flight f
                JOIN Airplane a
                  ON a.airline_name=f.airline_name AND a.id_number=f.airplane_id_number
                WHERE f.airline_name=%s AND f.flight_number=%s AND f.departure_date_time=%s
                FOR UPDATE
                """,
                (intent["airline_name"], intent["flight_number"], intent["departure_date_time"]),
            )
            flight = cur.fetchone()
            if not flight or flight["status"] == "CANCELLED" or flight["departure_date_time"] <= datetime.now():
                cur.execute("UPDATE booking_intents SET status='FAILED' WHERE id=%s", (booking_intent_id,))
                conn.commit()
                return {"status": "FAILED", "message": "Flight is no longer bookable."}
            cur.execute(
                """
                SELECT COUNT(*) AS sold
                FROM Ticket t
                LEFT JOIN ticket_cancellations c
                  ON c.ticket_id=t.ticket_ID
                 AND c.customer_email=t.customer_email
                WHERE t.airline_name=%s AND t.flight_number=%s AND t.departure_date_time=%s
                  AND c.id IS NULL
                """,
                (intent["airline_name"], intent["flight_number"], intent["departure_date_time"]),
            )
            sold = int(cur.fetchone()["sold"])
            if sold >= int(flight["seats"]):
                cur.execute("UPDATE booking_intents SET status='FAILED' WHERE id=%s", (booking_intent_id,))
                conn.commit()
                return {"status": "FAILED", "message": "Flight is sold out."}
            cur.execute("SELECT ticket_ID FROM Ticket ORDER BY ticket_ID DESC LIMIT 1 FOR UPDATE")
            last_ticket = cur.fetchone()
            next_id = (last_ticket["ticket_ID"] if last_ticket else 0) + 1
            cur.execute(
                """
                INSERT INTO Ticket(
                    ticket_ID, customer_email, airline_name, flight_number, departure_date_time,
                    card_type, card_number, name_on_card, expiration_date, purchase_date_time
                )
                VALUES(%s,%s,%s,%s,%s,'Credit','MOCK-AGENT-PAYMENT','Agent Mock Payment',
                       DATE_ADD(CURDATE(), INTERVAL 2 YEAR),NOW())
                """,
                (
                    next_id,
                    customer_email,
                    intent["airline_name"],
                    intent["flight_number"],
                    intent["departure_date_time"],
                ),
            )
            cur.execute(
                """
                UPDATE booking_intents
                SET status='CONFIRMED', confirmed_at=NOW(), ticket_id=%s
                WHERE id=%s
                """,
                (next_id, booking_intent_id),
            )
        conn.commit()
        return {"status": "CONFIRMED", "ticket_id": next_id, "message": "Mock booking confirmed."}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def answer_policy_question(rag: PolicyRAG, question: str) -> Dict[str, Any]:
    return rag.query(question)


def remember_user_preference(
    customer_email: str,
    departure_city: Optional[str] = None,
    destination_city: Optional[str] = None,
    max_budget: Optional[float] = None,
    preferred_airline: Optional[str] = None,
) -> Dict[str, Any]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_preferences(customer_email, departure_city, destination_city, max_budget, preferred_airline)
                VALUES(%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    departure_city=COALESCE(VALUES(departure_city), departure_city),
                    destination_city=COALESCE(VALUES(destination_city), destination_city),
                    max_budget=COALESCE(VALUES(max_budget), max_budget),
                    preferred_airline=COALESCE(VALUES(preferred_airline), preferred_airline)
                """,
                (customer_email, departure_city, destination_city, max_budget, preferred_airline),
            )
        conn.commit()
        return {"saved": True}
    finally:
        conn.close()


def get_user_preferences(customer_email: str) -> Dict[str, Any]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT departure_city, destination_city, max_budget, preferred_airline
                FROM user_preferences
                WHERE customer_email=%s
                """,
                (customer_email,),
            )
            row = cur.fetchone()
        return {"preferences": row or {}}
    finally:
        conn.close()


def parse_airports(message: str):
    upper = message.upper()
    match = re.search(r"\b(?:FROM\s+)?([A-Z]{3})\s+(?:TO|->)\s+([A-Z]{3})\b", upper)
    if match:
        return match.group(1), match.group(2)
    ignored = {
        "AND",
        "ARE",
        "BUY",
        "CAN",
        "FLY",
        "FOR",
        "GET",
        "LOW",
        "MAX",
        "NOW",
        "PAY",
        "THE",
        "TOO",
    }
    codes = [code for code in re.findall(r"\b[A-Z]{3}\b", upper) if code not in ignored]
    if len(codes) >= 2:
        return codes[0], codes[1]
    return None, None
