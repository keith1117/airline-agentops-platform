import argparse
from datetime import datetime, timedelta
from pathlib import Path

from scripts.generate_synthetic_data import SyntheticConfig, SyntheticDataset, apply_sql, build_synthetic_dataset, render_insert_sql
from agent_service.db import get_conn


DEFAULT_OUTPUT = Path("sql/professional_demo_seed.sql")
FIRST_MONTH = datetime(2026, 6, 1, 8, 0, 0)
MONTH_COUNT = 19


def build_professional_demo_dataset() -> SyntheticDataset:
    config = SyntheticConfig(
        airports=12,
        flights=60,
        customers=20,
        tickets=90,
        reviews=45,
        seed=609,
        airline_name="United",
        start_ticket_id=900_000,
    )
    dataset = build_synthetic_dataset(config)
    _spread_flight_times_monthly(dataset)
    return dataset


def build_professional_demo_sql() -> str:
    dataset = build_professional_demo_dataset()
    header = (
        "-- Curated professional demo data for the Docker MySQL demo database.\n"
        "-- Scale: 12 airports, 60 United flights, 20 customers, 90 tickets, 45 reviews.\n"
        "-- Flight inventory is spread monthly from 2026-06 through 2027-12 for durable demos.\n"
        "-- Uses INSERT IGNORE and high ticket IDs to preserve the stable P0 booking demo.\n\n"
    )
    return header + render_insert_sql(dataset)


def refresh_professional_demo_data() -> None:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM Review WHERE customer_email LIKE 'synthetic%@demo.local' AND airline_name='United'")
            cur.execute("DELETE FROM Ticket WHERE ticket_ID >= 900000 AND airline_name='United'")
            cur.execute("DELETE FROM booking_intents WHERE customer_email LIKE 'synthetic%@demo.local' AND airline_name='United'")
            cur.execute("DELETE FROM Flight WHERE airline_name='United' AND flight_number LIKE 'SYN%'")
            cur.execute("DELETE FROM Airplane WHERE airline_name='United' AND id_number LIKE 'SYN-A%'")
            cur.execute("DELETE FROM Customer WHERE email LIKE 'synthetic%@demo.local'")
        conn.commit()
    finally:
        conn.close()


def _spread_flight_times_monthly(dataset: SyntheticDataset) -> None:
    old_to_new = {}
    for idx, flight in enumerate(dataset.flights):
        old_key = (flight["airline_name"], flight["flight_number"], flight["departure_date_time"])
        month_offset = idx % MONTH_COUNT
        cycle = idx // MONTH_COUNT
        month_start = _add_months(FIRST_MONTH, month_offset)
        departure = month_start + timedelta(days=cycle * 7 + (idx % 3), hours=(idx * 2) % 12)
        duration = datetime.strptime(flight["arrival_date_time"], "%Y-%m-%d %H:%M:%S") - datetime.strptime(
            flight["departure_date_time"],
            "%Y-%m-%d %H:%M:%S",
        )
        arrival = departure + duration
        flight["departure_date_time"] = departure.strftime("%Y-%m-%d %H:%M:%S")
        flight["arrival_date_time"] = arrival.strftime("%Y-%m-%d %H:%M:%S")
        old_to_new[old_key] = (flight["departure_date_time"], flight["arrival_date_time"])

    for idx, ticket in enumerate(dataset.tickets):
        key = (ticket["airline_name"], ticket["flight_number"], ticket["departure_date_time"])
        if key not in old_to_new:
            continue
        new_departure, _ = old_to_new[key]
        departure = datetime.strptime(new_departure, "%Y-%m-%d %H:%M:%S")
        ticket["departure_date_time"] = new_departure
        ticket["purchase_date_time"] = (departure - timedelta(days=14 + (idx % 45), hours=idx % 12)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    for idx, review in enumerate(dataset.reviews):
        key = (review["airline_name"], review["flight_number"], review["departure_date_time"])
        if key not in old_to_new:
            continue
        new_departure, new_arrival = old_to_new[key]
        arrival = datetime.strptime(new_arrival, "%Y-%m-%d %H:%M:%S")
        review["departure_date_time"] = new_departure
        review["created_at"] = (arrival + timedelta(days=1 + (idx % 5))).strftime("%Y-%m-%d %H:%M:%S")


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate curated professional demo data for the main Docker MySQL demo DB.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--apply", action="store_true", help="Apply generated SQL to the configured MySQL database.")
    parser.add_argument("--refresh", action="store_true", help="Delete existing curated professional rows before applying.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    sql = build_professional_demo_sql()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(sql, encoding="utf-8")
    print(f"Generated curated professional demo SQL -> {output_path}")
    if args.apply:
        if args.refresh:
            refresh_professional_demo_data()
            print("Removed existing curated professional demo data from MySQL.")
        apply_sql(sql)
        print("Applied curated professional demo data to MySQL.")
    else:
        print("MySQL was not modified. Re-run with --apply when you intentionally want to load it.")


if __name__ == "__main__":
    main()
