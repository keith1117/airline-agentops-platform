import argparse
from pathlib import Path

from scripts.generate_synthetic_data import SyntheticConfig, apply_sql, build_synthetic_dataset, render_insert_sql


DEFAULT_OUTPUT = Path("sql/professional_demo_seed.sql")


def build_professional_demo_sql() -> str:
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
    header = (
        "-- Curated professional demo data for the Docker MySQL demo database.\n"
        "-- Scale: 12 airports, 60 United flights, 20 customers, 90 tickets, 45 reviews.\n"
        "-- Uses INSERT IGNORE and high ticket IDs to preserve the stable P0 booking demo.\n\n"
    )
    return header + render_insert_sql(dataset)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate curated professional demo data for the main Docker MySQL demo DB.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--apply", action="store_true", help="Apply generated SQL to the configured MySQL database.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    sql = build_professional_demo_sql()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(sql, encoding="utf-8")
    print(f"Generated curated professional demo SQL -> {output_path}")
    if args.apply:
        apply_sql(sql)
        print("Applied curated professional demo data to MySQL.")
    else:
        print("MySQL was not modified. Re-run with --apply when you intentionally want to load it.")


if __name__ == "__main__":
    main()
