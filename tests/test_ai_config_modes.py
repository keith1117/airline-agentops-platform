from agent_service import config


def test_new_llm_env_vars_take_priority_over_legacy_openai_vars(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "new-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://new.example/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://legacy.example/v1")

    settings = config.load_settings()

    assert settings.llm_api_key == "new-key"
    assert settings.llm_base_url == "https://new.example/v1"


def test_legacy_openai_vars_are_fallback_only(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://legacy.example/v1")

    settings = config.load_settings()

    assert settings.llm_api_key == "legacy-key"
    assert settings.llm_base_url == "https://legacy.example/v1"


def test_embedding_config_inherits_final_resolved_llm_config(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "new-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://new.example/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://legacy.example/v1")
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("EMBEDDING_BASE_URL", raising=False)

    settings = config.load_settings()

    assert settings.embedding_api_key == "new-key"
    assert settings.embedding_base_url == "https://new.example/v1"


def test_default_modes_are_ai_first_auto_with_relevance_gate(monkeypatch):
    monkeypatch.delenv("AGENT_ROUTER_MODE", raising=False)
    monkeypatch.delenv("TOOL_ROUTER_MODE", raising=False)
    monkeypatch.delenv("AGENT_RUNTIME_MODE", raising=False)
    monkeypatch.delenv("RAG_RETRIEVER_MODE", raising=False)
    monkeypatch.delenv("POLICY_ANSWER_MODE", raising=False)

    settings = config.load_settings()

    assert settings.agent_router_mode == "auto"
    assert settings.tool_router_mode == "auto"
    assert settings.rag_retriever_mode == "auto"
    assert settings.policy_answer_mode == "auto"
    assert settings.rag_top_k == 3
    assert settings.rag_similarity_threshold > 0
    assert settings.agent_runtime_mode == "single_step"


def test_agent_runtime_mode_supports_single_step_bounded_react_and_auto(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_MODE", "bounded_react")
    assert config.load_settings().agent_runtime_mode == "bounded_react"

    monkeypatch.setenv("AGENT_RUNTIME_MODE", "single_step")
    assert config.load_settings().agent_runtime_mode == "single_step"

    monkeypatch.setenv("AGENT_RUNTIME_MODE", "auto")
    assert config.load_settings().agent_runtime_mode == "auto"


def test_tool_router_mode_supports_native_json_and_legacy_agent_mode(monkeypatch):
    monkeypatch.setenv("TOOL_ROUTER_MODE", "native")
    assert config.load_settings().tool_router_mode == "native"

    monkeypatch.setenv("TOOL_ROUTER_MODE", "json")
    assert config.load_settings().tool_router_mode == "json"

    monkeypatch.delenv("TOOL_ROUTER_MODE", raising=False)
    monkeypatch.setenv("AGENT_ROUTER_MODE", "llm")
    settings = config.load_settings()

    assert settings.agent_router_mode == "llm"
    assert settings.tool_router_mode == "json"
