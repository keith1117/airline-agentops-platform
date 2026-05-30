from scripts.generate_synthetic_data import SyntheticConfig, build_synthetic_dataset, render_insert_sql


def test_synthetic_dataset_preserves_referential_integrity():
    config = SyntheticConfig(airports=6, flights=18, customers=10, tickets=30, reviews=8, seed=7)
    dataset = build_synthetic_dataset(config)

    airline_names = {row["name"] for row in dataset.airlines}
    airport_codes = {row["code"] for row in dataset.airports}
    airplane_keys = {(row["id_number"], row["airline_name"]) for row in dataset.airplanes}
    flight_keys = {(row["airline_name"], row["flight_number"], row["departure_date_time"]) for row in dataset.flights}
    customer_emails = {row["email"] for row in dataset.customers}

    assert len(dataset.airports) == 6
    assert len(dataset.flights) == 18
    assert len(dataset.customers) == 10
    assert len(dataset.tickets) == 30
    assert len(dataset.reviews) == 8

    for airplane in dataset.airplanes:
        assert airplane["airline_name"] in airline_names

    for flight in dataset.flights:
        assert flight["airline_name"] in airline_names
        assert flight["departure_airport"] in airport_codes
        assert flight["arrival_airport"] in airport_codes
        assert (flight["airplane_id_number"], flight["airline_name"]) in airplane_keys

    assert len(flight_keys) == len(dataset.flights)
    assert len({row["ticket_ID"] for row in dataset.tickets}) == len(dataset.tickets)

    for ticket in dataset.tickets:
        assert ticket["customer_email"] in customer_emails
        assert (ticket["airline_name"], ticket["flight_number"], ticket["departure_date_time"]) in flight_keys

    review_keys = set()
    for review in dataset.reviews:
        assert review["customer_email"] in customer_emails
        assert (review["airline_name"], review["flight_number"], review["departure_date_time"]) in flight_keys
        key = (review["customer_email"], review["airline_name"], review["flight_number"], review["departure_date_time"])
        assert key not in review_keys
        review_keys.add(key)


def test_synthetic_sql_orders_parent_tables_before_children():
    config = SyntheticConfig(airports=4, flights=5, customers=4, tickets=6, reviews=3, seed=3)
    dataset = build_synthetic_dataset(config)
    sql = render_insert_sql(dataset)

    airline_pos = sql.index("INSERT IGNORE INTO Airline")
    airport_pos = sql.index("INSERT IGNORE INTO Airport")
    airplane_pos = sql.index("INSERT IGNORE INTO Airplane")
    flight_pos = sql.index("INSERT IGNORE INTO Flight")
    customer_pos = sql.index("INSERT IGNORE INTO Customer")
    ticket_pos = sql.index("INSERT IGNORE INTO Ticket")
    review_pos = sql.index("INSERT IGNORE INTO Review")

    assert airline_pos < airplane_pos < flight_pos < ticket_pos
    assert airport_pos < flight_pos
    assert customer_pos < ticket_pos < review_pos
    assert "SYN" in sql
