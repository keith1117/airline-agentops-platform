from typing import Any, Dict

from ..db import get_conn
from ..reporting import resolve_sales_window, aggregate_sales


def _serialize_rows(rows):
    out = []
    for row in rows:
        item = {}
        for key, value in row.items():
            item[key] = value.isoformat(sep=" ") if hasattr(value, "isoformat") else value
        out.append(item)
    return out


def get_sales_report(
    airline_name: str,
    period: str = "past_year",
    start_date: str = None,
    end_date: str = None,
) -> Dict[str, Any]:
    window = resolve_sales_window(period, start_date=start_date, end_date=end_date)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.purchase_date_time, f.base_price
                FROM Ticket t
                JOIN Flight f
                  ON f.airline_name=t.airline_name
                 AND f.flight_number=t.flight_number
                 AND f.departure_date_time=t.departure_date_time
                WHERE t.airline_name=%s
                  AND t.purchase_date_time >= %s
                  AND t.purchase_date_time < %s
                  AND t.purchase_date_time <= NOW()
                ORDER BY t.purchase_date_time
                """,
                (airline_name, window["start_utc"], window["end_utc"]),
            )
            rows = aggregate_sales(cur.fetchall(), zone=window["timezone"])
        return {
            "timezone": window["timezone"],
            "rows": rows,
            "count": len(rows),
            "period": window["period"],
            "start_date": window["start_date"],
            "end_date": window["end_date"],
            "range_label": window["label"],
        }
    finally:
        conn.close()


def analyze_reviews(airline_name: str, limit: int = 10, target: str = "flight", order: str = "worst") -> Dict[str, Any]:
    target = target if target in {"flight", "route"} else "flight"
    order = order if order in {"best", "worst"} else "worst"
    rating_order = "DESC" if order == "best" else "ASC"
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT flight_number, AVG(rating) AS avg_rating, COUNT(*) AS review_count
                FROM Review
                WHERE airline_name=%s
                GROUP BY flight_number
                ORDER BY avg_rating {rating_order}, review_count DESC
                LIMIT %s
                """,
                (airline_name, limit),
            )
            summary = _serialize_rows(cur.fetchall())
            cur.execute(
                f"""
                SELECT f.departure_airport, f.arrival_airport,
                       AVG(r.rating) AS avg_rating, COUNT(*) AS review_count
                FROM Review r
                JOIN Flight f
                  ON f.airline_name=r.airline_name
                 AND f.flight_number=r.flight_number
                 AND f.departure_date_time=r.departure_date_time
                WHERE r.airline_name=%s
                GROUP BY f.departure_airport, f.arrival_airport
                ORDER BY avg_rating {rating_order}, review_count DESC
                LIMIT %s
                """,
                (airline_name, limit),
            )
            route_summary = _serialize_rows(cur.fetchall())
            cur.execute(
                f"""
                SELECT flight_number, rating, comment, created_at
                FROM Review
                WHERE airline_name=%s
                ORDER BY rating {rating_order}, created_at DESC
                LIMIT %s
                """,
                (airline_name, limit),
            )
            comments = _serialize_rows(cur.fetchall())
        return {
            "summary": summary,
            "route_summary": route_summary,
            "comments": comments,
            "target": target,
            "order": order,
        }
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
