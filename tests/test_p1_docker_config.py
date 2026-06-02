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
    assert "AGENT_ROUTER_MODE: ${AGENT_ROUTER_MODE:-auto}" in compose
    assert "RAG_RETRIEVER_MODE: ${RAG_RETRIEVER_MODE:-auto}" in compose
    assert "POLICY_ANSWER_MODE: ${POLICY_ANSWER_MODE:-auto}" in compose
    assert "LLM_API_KEY: ${LLM_API_KEY:-}" in compose
    assert "OPENAI_API_KEY: ${OPENAI_API_KEY:-}" in compose
    assert "RAG_SIMILARITY_THRESHOLD: ${RAG_SIMILARITY_THRESHOLD:-0.35}" in compose


def test_dockerignore_excludes_local_only_artifacts():
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8")

    assert ".venv/" in dockerignore
    assert ".env" in dockerignore
    assert "__pycache__/" in dockerignore
    assert "eval/sft_ready_traces.jsonl" in dockerignore
    assert "logs/" in dockerignore
    assert "instance/rag/" in dockerignore
    assert "sql/synthetic_data.sql" in dockerignore


def test_compose_includes_phpmyadmin_for_docker_mysql_visualization():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "phpmyadmin:" in compose
    assert "image: phpmyadmin:latest" in compose
    assert "PMA_HOST: mysql" in compose
    assert "PMA_PORT: 3306" in compose
    assert '"8080:80"' in compose
