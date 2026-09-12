from agent_service.tools import customer_tools
from agent_service.react_agent import ReActAgent
from agent_service.tools.customer_tools import AIRPORT_CITY_ALIASES, parse_airports, search_flights


def test_parse_airports_accepts_english_and_chinese_city_routes():
    assert parse_airports("Find flights from Shanghai to Boston next month") == ("PVG", "BOS")
    assert parse_airports("帮我查询下个月从上海飞往波士顿的航班") == ("PVG", "BOS")
    assert parse_airports("帮我查询下个月从旧金山到洛杉矶的航班") == ("SFO", "LAX")
    assert parse_airports("Hong Kong to Beijing") == ("HKG", "BEI")


def test_every_supported_city_alias_resolves_to_its_iata_code():
    for code, aliases in AIRPORT_CITY_ALIASES.items():
        destination = "LAX" if code == "BOS" else "BOS"
        for alias in aliases:
            assert parse_airports(f"from {alias} to {destination}")[0] == code


def test_chinese_relative_periods_are_preserved_for_city_searches():
    assert ReActAgent._extract_period("查询下个月从上海到波士顿的航班") == "next_month"
    assert ReActAgent._extract_period("查询今年从旧金山到洛杉矶的航班") == "this_year"
    assert ReActAgent._extract_period("查询明年从香港到北京的航班") == "next_year"


class FakeCursor:
    def __init__(self):
        self.sql = ""
        self.args = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def execute(self, sql, args):
        self.sql = sql
        self.args = list(args)

    def fetchall(self):
        return []


class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()

    def cursor(self):
        return self.cursor_instance

    def close(self):
        pass


def test_search_flights_accepts_database_city_names(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(customer_tools, "get_conn", lambda: connection)

    result = search_flights(departure_airport="Shanghai", arrival_airport="Boston")

    assert result == {"count": 0, "flights": []}
    assert "JOIN Airport da" in connection.cursor_instance.sql
    assert "LOWER(da.city)=LOWER(%s)" in connection.cursor_instance.sql
    assert "LOWER(aa.city)=LOWER(%s)" in connection.cursor_instance.sql
    assert connection.cursor_instance.args[:2] == ["Shanghai", "Boston"]


def test_search_flights_expands_legacy_iata_aliases(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(customer_tools, "get_conn", lambda: connection)

    search_flights(departure_airport="HKG", arrival_airport="PEK")

    assert connection.cursor_instance.args[:4] == ["HKG", "HKA", "BEI", "PEK"]


def test_search_flights_maps_new_york_metro_code_to_inventory_airport(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(customer_tools, "get_conn", lambda: connection)

    search_flights(departure_airport="NYC", arrival_airport="BOS")

    assert connection.cursor_instance.args[:2] == ["JFK", "BOS"]
