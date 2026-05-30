from datetime import date, datetime, timedelta

from agent_service.db import get_conn, ensure_agent_schema


def first_day_next_month() -> date:
    today = date.today()
    if today.month == 12:
        return date(today.year + 1, 1, 1)
    return date(today.year, today.month + 1, 1)


def main() -> None:
    ensure_agent_schema(retries=3)
    dep = datetime.combine(first_day_next_month() + timedelta(days=7), datetime.min.time()).replace(hour=9, minute=30)
    arr = dep + timedelta(hours=1, minutes=35)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT IGNORE INTO Airline(name) VALUES('United')")
            cur.execute(
                """
                INSERT INTO Airline_Staff(username, password, first_name, last_name, email_address, airline_name)
                VALUES('admin', 'abcd', 'Roe', 'Jones', 'staff@nyu.edu', 'United')
                ON DUPLICATE KEY UPDATE airline_name=VALUES(airline_name)
                """
            )
            cur.execute(
                """
                INSERT INTO Airport(code, city, country, airport_type)
                VALUES
                  ('SFO', 'San Francisco', 'USA', 'Both'),
                  ('LAX', 'Los Angeles', 'USA', 'Both'),
                  ('JFK', 'New York', 'USA', 'Both'),
                  ('PVG', 'Shanghai', 'China', 'Both')
                ON DUPLICATE KEY UPDATE city=VALUES(city), country=VALUES(country), airport_type=VALUES(airport_type)
                """
            )
            cur.execute(
                """
                INSERT INTO Airplane(id_number, airline_name, seats, manufacturer, age)
                VALUES('P0-737', 'United', 8, 'Boeing', 2)
                ON DUPLICATE KEY UPDATE seats=VALUES(seats)
                """
            )
            cur.execute(
                """
                INSERT INTO Customer(email, name, password, city, state)
                VALUES('testcustomer@nyu.edu', 'Jon Snow', '1234', 'Brooklyn', 'NY')
                ON DUPLICATE KEY UPDATE name=VALUES(name)
                """
            )
            cur.execute(
                """
                DELETE FROM booking_intents
                WHERE airline_name='United'
                  AND flight_number='P0206'
                  AND departure_date_time=%s
                """,
                (dep,),
            )
            cur.execute(
                """
                DELETE FROM Ticket
                WHERE airline_name='United'
                  AND flight_number='P0206'
                  AND departure_date_time=%s
                """,
                (dep,),
            )
            cur.execute(
                """
                INSERT INTO Flight(airline_name, flight_number, departure_date_time, arrival_date_time,
                                   base_price, departure_airport, arrival_airport, airplane_id_number, status)
                VALUES('United', 'P0206', %s, %s, 420.00, 'SFO', 'LAX', 'P0-737', 'ON_TIME')
                ON DUPLICATE KEY UPDATE arrival_date_time=VALUES(arrival_date_time),
                    base_price=VALUES(base_price), status=VALUES(status)
                """,
                (dep, arr),
            )
            cur.execute(
                """
                INSERT INTO Review(customer_email, airline_name, flight_number, departure_date_time, rating, comment, created_at)
                VALUES('testcustomer@nyu.edu', 'United', 'P0206', %s, 2, 'P0 demo review: boarding was slow.', NOW())
                ON DUPLICATE KEY UPDATE rating=VALUES(rating), comment=VALUES(comment), created_at=NOW()
                """,
                (dep,),
            )
        conn.commit()
        print(f"Seeded P0 demo flight United P0206 at {dep:%Y-%m-%d %H:%M:%S}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
