from collections import Counter

from scripts.seed_professional_demo import build_professional_demo_dataset, build_professional_demo_sql


def test_professional_demo_seed_is_curated_and_non_destructive():
    sql = build_professional_demo_sql()

    assert "Curated professional demo data" in sql
    assert "INSERT IGNORE INTO Airline" in sql
    assert "'United'" in sql
    assert "'P0206'" not in sql
    assert "900000" in sql
    assert "synthetic00000@demo.local" in sql


def test_professional_demo_seed_spreads_flights_through_2027():
    dataset = build_professional_demo_dataset()
    months = Counter(flight["departure_date_time"][:7] for flight in dataset.flights)

    expected_months = []
    for year, start, end in [(2026, 6, 12), (2027, 1, 12)]:
        expected_months.extend(f"{year}-{month:02d}" for month in range(start, end + 1))

    assert list(months) == expected_months
    assert all(months[month] >= 1 for month in expected_months)
    assert len(dataset.flights) == 60


def test_professional_demo_seed_updates_child_times_with_flights():
    dataset = build_professional_demo_dataset()
    flight_keys = {(row["airline_name"], row["flight_number"], row["departure_date_time"]) for row in dataset.flights}

    assert all(
        (ticket["airline_name"], ticket["flight_number"], ticket["departure_date_time"]) in flight_keys
        for ticket in dataset.tickets
    )
    assert all(
        (review["airline_name"], review["flight_number"], review["departure_date_time"]) in flight_keys
        for review in dataset.reviews
    )
