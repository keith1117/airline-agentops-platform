from pathlib import Path


def test_compose_has_p0_demo_seed_and_healthcheck():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "healthcheck:" in compose
    assert "service_healthy" in compose
    assert "seed:" in compose
    assert "python\", \"-m\", \"scripts.seed_p0_demo" in compose
    assert "service_completed_successfully" in compose
    assert 'MYSQL_DB: "Airline Ticket Reservation System"' in compose
    assert "AGENT_SERVICE_URL: http://agent:8001" in compose


def test_dockerignore_excludes_local_only_artifacts():
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8")

    assert ".venv/" in dockerignore
    assert ".env" in dockerignore
    assert "__pycache__/" in dockerignore
    assert "eval/sft_ready_traces.jsonl" in dockerignore

