import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


VALID_AGENT_ROUTER_MODES = {"auto", "deterministic", "llm"}
VALID_TOOL_ROUTER_MODES = {"auto", "native", "json", "deterministic"}
VALID_AGENT_RUNTIME_MODES = {"single_step", "bounded_react"}
VALID_RAG_RETRIEVER_MODES = {"auto", "keyword", "embedding"}
VALID_POLICY_ANSWER_MODES = {"auto", "extractive", "llm"}


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _mode(name: str, default: str, valid: set[str]) -> str:
    value = _env(name, default).lower()
    if value not in valid:
        raise ValueError(f"{name} must be one of {', '.join(sorted(valid))}; got {value!r}")
    return value


def _optional_int(value: str) -> Optional[int]:
    return int(value) if value else None


@dataclass(frozen=True)
class Settings:
    mysql_host: str = "localhost"
    mysql_port: int = 8889
    mysql_user: str = "root"
    mysql_password: str = "root"
    mysql_db: str = "Airline Ticket Reservation System"

    agent_router_mode: str = "auto"
    tool_router_mode: str = "auto"
    agent_runtime_mode: str = "single_step"
    rag_retriever_mode: str = "auto"
    policy_answer_mode: str = "auto"
    agent_trace_enabled: bool = True

    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: Optional[int] = None

    rag_policy_path: str = "docs/policies/airline_policy.md"
    rag_embedding_cache: str = "instance/rag/policy_embeddings.json"
    rag_top_k: int = 3
    rag_similarity_threshold: float = 0.35

    max_agent_steps: int = 4
    metrics_log_path: str = "logs/agent_metrics.jsonl"

    @property
    def openai_api_key(self) -> str:
        return self.llm_api_key

    @property
    def openai_base_url(self) -> str:
        return self.llm_base_url


def load_settings() -> Settings:
    llm_api_key = _env("LLM_API_KEY") or _env("OPENAI_API_KEY")
    llm_base_url = _env("LLM_BASE_URL") or _env("OPENAI_BASE_URL", "https://api.openai.com/v1")

    embedding_api_key = _env("EMBEDDING_API_KEY") or llm_api_key
    embedding_base_url = _env("EMBEDDING_BASE_URL") or llm_base_url
    agent_router_mode = _mode("AGENT_ROUTER_MODE", "auto", VALID_AGENT_ROUTER_MODES)
    if _env("TOOL_ROUTER_MODE"):
        tool_router_mode = _mode("TOOL_ROUTER_MODE", "auto", VALID_TOOL_ROUTER_MODES)
    elif agent_router_mode == "llm":
        tool_router_mode = "json"
    elif agent_router_mode == "deterministic":
        tool_router_mode = "deterministic"
    else:
        tool_router_mode = "auto"

    return Settings(
        mysql_host=_env("MYSQL_HOST", "localhost"),
        mysql_port=int(_env("MYSQL_PORT", "8889")),
        mysql_user=_env("MYSQL_USER", "root"),
        mysql_password=_env("MYSQL_PASSWORD", "root"),
        mysql_db=_env("MYSQL_DB", "Airline Ticket Reservation System"),
        agent_router_mode=agent_router_mode,
        tool_router_mode=tool_router_mode,
        agent_runtime_mode=_mode("AGENT_RUNTIME_MODE", "single_step", VALID_AGENT_RUNTIME_MODES),
        rag_retriever_mode=_mode("RAG_RETRIEVER_MODE", "auto", VALID_RAG_RETRIEVER_MODES),
        policy_answer_mode=_mode("POLICY_ANSWER_MODE", "auto", VALID_POLICY_ANSWER_MODES),
        agent_trace_enabled=_env("AGENT_TRACE_ENABLED", "true").lower() not in {"0", "false", "no"},
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url,
        llm_model=_env("LLM_MODEL", "gpt-4o-mini"),
        embedding_api_key=embedding_api_key,
        embedding_base_url=embedding_base_url,
        embedding_model=_env("EMBEDDING_MODEL", "text-embedding-3-small"),
        embedding_dimensions=_optional_int(_env("EMBEDDING_DIMENSIONS")),
        rag_policy_path=_env("RAG_POLICY_PATH", "docs/policies/airline_policy.md"),
        rag_embedding_cache=_env("RAG_EMBEDDING_CACHE", "instance/rag/policy_embeddings.json"),
        rag_top_k=int(_env("RAG_TOP_K", "3")),
        rag_similarity_threshold=float(_env("RAG_SIMILARITY_THRESHOLD", "0.35")),
        max_agent_steps=int(_env("MAX_AGENT_STEPS", "4")),
        metrics_log_path=_env("METRICS_LOG_PATH", "logs/agent_metrics.jsonl"),
    )


settings = load_settings()
