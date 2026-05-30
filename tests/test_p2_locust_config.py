from pathlib import Path


def test_locust_smoke_file_defines_agent_scenarios():
    locustfile = Path("load_tests/locustfile.py")

    assert locustfile.exists()
    source = locustfile.read_text(encoding="utf-8")

    assert "HttpUser" in source
    assert "AirlineAgentSmokeUser" in source
    assert "/api/agent/customer/chat" in source
    assert "/api/agent/staff/chat" in source
    assert "/api/metrics" in source
    assert "Find flights from SFO to LAX next month" in source
    assert "Can I get a refund if my flight is cancelled?" in source
    assert "Which flights have the worst reviews?" in source


def test_locust_dependency_and_smoke_script_are_declared():
    requirements = Path("requirements.txt").read_text(encoding="utf-8")
    script = Path("scripts/run_locust_smoke.sh")

    assert "locust" in requirements
    assert script.exists()

    script_text = script.read_text(encoding="utf-8")
    assert "load_tests/locustfile.py" in script_text
    assert "--headless" in script_text
    assert "--users" in script_text
    assert "--spawn-rate" in script_text
    assert "--run-time" in script_text
    assert "--csv" in script_text
