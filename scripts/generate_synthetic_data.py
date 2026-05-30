import argparse
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from agent_service.db import get_conn


@dataclass(frozen=True)
class SyntheticConfig:
    airports: int = 24
    flights: int = 10_000
    customers: int = 2_000
    tickets: int = 50_000
    reviews: int = 5_000
    seed: int = 3083
    airline_name: str = "SyntheticAir"
    start_ticket_id: int = 800_000


@dataclass(frozen=True)
class SyntheticDataset:
    airlines: List[Dict[str, Any]]
    airports: List[Dict[str, Any]]
    airplanes: List[Dict[str, Any]]
    customers: List[Dict[str, Any]]
    flights: List[Dict[str, Any]]
    tickets: List[Dict[str, Any]]
    reviews: List[Dict[str, Any]]


AIRPORT_CATALOG = [
    ("SFO", "San Francisco", "USA"),
    ("LAX", "Los Angeles", "USA"),
    ("JFK", "New York", "USA"),
    ("BOS", "Boston", "USA"),
    ("SEA", "Seattle", "USA"),
    ("ORD", "Chicago", "USA"),
    ("DFW", "Dallas", "USA"),
    ("MIA", "Miami", "USA"),
    ("ATL", "Atlanta", "USA"),
    ("DEN", "Denver", "USA"),
    ("LAS", "Las Vegas", "USA"),
    ("AUS", "Austin", "USA"),
    ("PVG", "Shanghai", "China"),
    ("HKG", "Hong Kong", "China"),
    ("SZX", "Shenzhen", "China"),
    ("NRT", "Tokyo", "Japan"),
    ("ICN", "Seoul", "South Korea"),
    ("SIN", "Singapore", "Singapore"),
    ("LHR", "London", "UK"),
    ("CDG", "Paris", "France"),
    ("FRA", "Frankfurt", "Germany"),
    ("DXB", "Dubai", "UAE"),
    ("SYD", "Sydney", "Australia"),
    ("YVR", "Vancouver", "Canada"),
]

MANUFACTURERS = ["Boeing", "Airbus", "Embraer"]
REVIEW_COMMENTS = [
    "Smooth boarding and clean cabin.",
    "Delay communication could be clearer.",
    "Good value for the route.",
    "Seat comfort was acceptable for the price.",
    "Staff handled the disruption professionally.",
]


def build_synthetic_dataset(config: SyntheticConfig) -> SyntheticDataset:
    if config.airports < 2:
        raise ValueError("airports must be at least 2")
    if config.flights < 1:
        raise ValueError("flights must be at least 1")
    if config.customers < 1:
        raise ValueError("customers must be at least 1")
    if config.reviews > config.customers * config.flights:
        raise ValueError("reviews cannot exceed unique customer-flight combinations")

    rng = random.Random(config.seed)
    selected_airports = AIRPORT_CATALOG[: min(config.airports, len(AIRPORT_CATALOG))]
    airlines = [{"name": config.airline_name}]
    airports = [{"code": code, "city": city, "country": country, "airport_type": "Both"} for code, city, country in selected_airports]
    airplanes = _build_airplanes(config, rng)
    customers = _build_customers(config)
    flights = _build_flights(config, airports, airplanes, rng)
    tickets = _build_tickets(config, customers, flights, rng)
    reviews = _build_reviews(config, customers, flights, rng)

    return SyntheticDataset(
        airlines=airlines,
        airports=airports,
        airplanes=airplanes,
        customers=customers,
        flights=flights,
        tickets=tickets,
        reviews=reviews,
    )


def render_insert_sql(dataset: SyntheticDataset) -> str:
    sections = [
        "-- Synthetic data generated for local P2 testing. Uses INSERT IGNORE to preserve existing demo rows.",
        _insert_many("Airline", ["name"], dataset.airlines),
        _insert_many("Airport", ["code", "city", "country", "airport_type"], dataset.airports),
        _insert_many("Airplane", ["id_number", "airline_name", "seats", "manufacturer", "age"], dataset.airplanes),
        _insert_many(
            "Customer",
            [
                "email",
                "name",
                "password",
                "building_number",
                "street",
                "city",
                "state",
                "phone_number",
                "passport_number",
                "passport_expiration",
                "passport_country",
                "date_of_birth",
            ],
            dataset.customers,
        ),
        _insert_many(
            "Flight",
            [
                "airline_name",
                "flight_number",
                "departure_date_time",
                "arrival_date_time",
                "base_price",
                "departure_airport",
                "arrival_airport",
                "airplane_id_number",
                "status",
            ],
            dataset.flights,
        ),
        _insert_many(
            "Ticket",
            [
                "ticket_ID",
                "customer_email",
                "airline_name",
                "flight_number",
                "departure_date_time",
                "card_type",
                "card_number",
                "name_on_card",
                "expiration_date",
                "purchase_date_time",
            ],
            dataset.tickets,
        ),
        _insert_many(
            "Review",
            ["customer_email", "airline_name", "flight_number", "departure_date_time", "rating", "comment", "created_at"],
            dataset.reviews,
        ),
    ]
    return "\n\n".join(section for section in sections if section) + "\n"


def apply_sql(sql: str) -> None:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for statement in [part.strip() for part in sql.split(";") if part.strip()]:
                cur.execute(statement)
        conn.commit()
    finally:
        conn.close()


def _build_airplanes(config: SyntheticConfig, rng: random.Random) -> List[Dict[str, Any]]:
    airplane_count = max(8, min(80, config.flights // 200 or 8))
    rows = []
    for idx in range(airplane_count):
        rows.append(
            {
                "id_number": f"SYN-A{idx:03d}",
                "airline_name": config.airline_name,
                "seats": rng.choice([120, 150, 180, 220]),
                "manufacturer": rng.choice(MANUFACTURERS),
                "age": rng.randint(1, 14),
            }
        )
    return rows


def _build_customers(config: SyntheticConfig) -> List[Dict[str, Any]]:
    rows = []
    for idx in range(config.customers):
        rows.append(
            {
                "email": f"synthetic{idx:05d}@demo.local",
                "name": f"Synthetic Customer {idx:05d}",
                "password": "demo",
                "building_number": str(100 + idx % 900),
                "street": "AgentOps Ave",
                "city": "Synthetic City",
                "state": "NA",
                "phone_number": f"555-01{idx % 10000:04d}",
                "passport_number": f"SYN{idx:08d}",
                "passport_expiration": "2030-12-31",
                "passport_country": "USA",
                "date_of_birth": f"199{idx % 10}-01-15",
            }
        )
    return rows


def _build_flights(
    config: SyntheticConfig,
    airports: Sequence[Dict[str, Any]],
    airplanes: Sequence[Dict[str, Any]],
    rng: random.Random,
) -> List[Dict[str, Any]]:
    start = datetime.now().replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=1)
    rows = []
    for idx in range(config.flights):
        dep = airports[idx % len(airports)]["code"]
        arr = airports[(idx * 7 + 3) % len(airports)]["code"]
        if dep == arr:
            arr = airports[(idx + 1) % len(airports)]["code"]
        departure = start + timedelta(hours=idx * 2)
        duration = timedelta(hours=rng.randint(1, 13), minutes=rng.choice([0, 15, 30, 45]))
        airplane = airplanes[idx % len(airplanes)]
        rows.append(
            {
                "airline_name": config.airline_name,
                "flight_number": f"SYN{idx:05d}",
                "departure_date_time": departure.strftime("%Y-%m-%d %H:%M:%S"),
                "arrival_date_time": (departure + duration).strftime("%Y-%m-%d %H:%M:%S"),
                "base_price": round(rng.uniform(90, 1200), 2),
                "departure_airport": dep,
                "arrival_airport": arr,
                "airplane_id_number": airplane["id_number"],
                "status": rng.choices(["ON_TIME", "DELAYED", "CANCELLED"], weights=[88, 9, 3])[0],
            }
        )
    return rows


def _build_tickets(
    config: SyntheticConfig,
    customers: Sequence[Dict[str, Any]],
    flights: Sequence[Dict[str, Any]],
    rng: random.Random,
) -> List[Dict[str, Any]]:
    rows = []
    for idx in range(config.tickets):
        customer = customers[idx % len(customers)]
        flight = flights[(idx * 11) % len(flights)]
        rows.append(
            {
                "ticket_ID": config.start_ticket_id + idx,
                "customer_email": customer["email"],
                "airline_name": flight["airline_name"],
                "flight_number": flight["flight_number"],
                "departure_date_time": flight["departure_date_time"],
                "card_type": "Credit" if idx % 2 == 0 else "Debit",
                "card_number": f"4111-1111-{idx % 10000:04d}-{(idx * 17) % 10000:04d}",
                "name_on_card": customer["name"],
                "expiration_date": "2030-12-31",
                "purchase_date_time": _purchase_time_before(flight["departure_date_time"], rng),
            }
        )
    return rows


def _build_reviews(
    config: SyntheticConfig,
    customers: Sequence[Dict[str, Any]],
    flights: Sequence[Dict[str, Any]],
    rng: random.Random,
) -> List[Dict[str, Any]]:
    rows = []
    seen = set()
    idx = 0
    while len(rows) < config.reviews:
        customer = customers[(idx * 13) % len(customers)]
        flight = flights[(idx * 17) % len(flights)]
        key = (customer["email"], flight["airline_name"], flight["flight_number"], flight["departure_date_time"])
        idx += 1
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "customer_email": customer["email"],
                "airline_name": flight["airline_name"],
                "flight_number": flight["flight_number"],
                "departure_date_time": flight["departure_date_time"],
                "rating": rng.randint(1, 5),
                "comment": REVIEW_COMMENTS[len(rows) % len(REVIEW_COMMENTS)],
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return rows


def _purchase_time_before(departure_date_time: str, rng: random.Random) -> str:
    departure = datetime.strptime(departure_date_time, "%Y-%m-%d %H:%M:%S")
    purchase = departure - timedelta(days=rng.randint(3, 90), hours=rng.randint(0, 23))
    return purchase.strftime("%Y-%m-%d %H:%M:%S")


def _insert_many(table: str, columns: Sequence[str], rows: Sequence[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    values = ",\n".join("(" + ", ".join(_sql_value(row[column]) for column in columns) + ")" for row in rows)
    return f"INSERT IGNORE INTO {table} ({', '.join(columns)}) VALUES\n{values};"


def _sql_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}'"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic airline data for P2 testing.")
    parser.add_argument("--airports", type=int, default=24)
    parser.add_argument("--flights", type=int, default=10_000)
    parser.add_argument("--customers", type=int, default=2_000)
    parser.add_argument("--tickets", type=int, default=50_000)
    parser.add_argument("--reviews", type=int, default=5_000)
    parser.add_argument("--seed", type=int, default=3083)
    parser.add_argument("--output", default="sql/synthetic_data.sql")
    parser.add_argument("--apply", action="store_true", help="Apply generated SQL to the configured MySQL database.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    config = SyntheticConfig(
        airports=args.airports,
        flights=args.flights,
        customers=args.customers,
        tickets=args.tickets,
        reviews=args.reviews,
        seed=args.seed,
    )
    dataset = build_synthetic_dataset(config)
    sql = render_insert_sql(dataset)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(sql, encoding="utf-8")
    print(
        "Generated synthetic data: "
        f"{len(dataset.airports)} airports, {len(dataset.flights)} flights, "
        f"{len(dataset.customers)} customers, {len(dataset.tickets)} tickets, "
        f"{len(dataset.reviews)} reviews -> {output_path}"
    )
    if args.apply:
        apply_sql(sql)
        print("Applied synthetic data to MySQL.")


if __name__ == "__main__":
    main()
