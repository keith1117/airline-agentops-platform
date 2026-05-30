from typing import Any, Dict

from ..db import get_conn


def _serialize_rows(rows):
    out = []
    for row in rows:
        item = {}
        for key, value in row.items():
            item[key] = value.isoformat(sep=" ") if hasattr(value, "isoformat") else value
        out.append(item)
    return out


def get_sales_report(airline_name: str, months: int = 12) -> Dict[str, Any]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DATE_FORMAT(t.purchase_date_time, '%%Y-%%m') AS month,
                       COUNT(*) AS tickets,
                       SUM(f.base_price) AS estimated_revenue
                FROM Ticket t
                JOIN Flight f
                  ON f.airline_name=t.airline_name
                 AND f.flight_number=t.flight_number
                 AND f.departure_date_time=t.departure_date_time
                WHERE t.airline_name=%s
                  AND t.purchase_date_time >= DATE_SUB(CURDATE(), INTERVAL %s MONTH)
                GROUP BY DATE_FORMAT(t.purchase_date_time, '%%Y-%%m')
                ORDER BY month
                """,
                (airline_name, months),
            )
            rows = _serialize_rows(cur.fetchall())
        return {"rows": rows, "count": len(rows)}
    finally:
        conn.close()


def analyze_reviews(airline_name: str, limit: int = 10) -> Dict[str, Any]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT flight_number, AVG(rating) AS avg_rating, COUNT(*) AS review_count
                FROM Review
                WHERE airline_name=%s
                GROUP BY flight_number
                ORDER BY avg_rating ASC, review_count DESC
                LIMIT %s
                """,
                (airline_name, limit),
            )
            summary = _serialize_rows(cur.fetchall())
            cur.execute(
                """
                SELECT flight_number, rating, comment, created_at
                FROM Review
                WHERE airline_name=%s
                ORDER BY rating ASC, created_at DESC
                LIMIT %s
                """,
                (airline_name, limit),
            )
            comments = _serialize_rows(cur.fetchall())
        return {"summary": summary, "comments": comments}
    finally:
        conn.close()


def get_flight_load_factor(airline_name: str, limit: int = 10) -> Dict[str, Any]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT f.flight_number, f.departure_date_time, f.departure_airport, f.arrival_airport,
                       a.seats, COUNT(t.ticket_ID) AS sold,
                       ROUND(COUNT(t.ticket_ID) / a.seats * 100, 1) AS load_factor_pct
                FROM Flight f
                JOIN Airplane a
                  ON a.airline_name=f.airline_name AND a.id_number=f.airplane_id_number
                LEFT JOIN Ticket t
                  ON t.airline_name=f.airline_name
                 AND t.flight_number=f.flight_number
                 AND t.departure_date_time=f.departure_date_time
                WHERE f.airline_name=%s
                GROUP BY f.flight_number, f.departure_date_time, f.departure_airport,
                         f.arrival_airport, a.seats
                ORDER BY load_factor_pct DESC, f.departure_date_time
                LIMIT %s
                """,
                (airline_name, limit),
            )
            rows = _serialize_rows(cur.fetchall())
        return {"rows": rows, "count": len(rows)}
    finally:
        conn.close()


def get_route_performance(airline_name: str, limit: int = 10) -> Dict[str, Any]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT f.departure_airport, f.arrival_airport,
                       COUNT(t.ticket_ID) AS tickets,
                       SUM(f.base_price) AS estimated_revenue
                FROM Flight f
                LEFT JOIN Ticket t
                  ON t.airline_name=f.airline_name
                 AND t.flight_number=f.flight_number
                 AND t.departure_date_time=f.departure_date_time
                WHERE f.airline_name=%s
                GROUP BY f.departure_airport, f.arrival_airport
                ORDER BY tickets DESC, estimated_revenue DESC
                LIMIT %s
                """,
                (airline_name, limit),
            )
            rows = _serialize_rows(cur.fetchall())
        return {"rows": rows, "count": len(rows)}
    finally:
        conn.close()

