import pytest

from agent_service.config import Settings
from agent_service.rag import PolicyRAG, RAGConfigurationError


class FakeEmbeddingClient:
    def enabled(self):
        return True

    def embed(self, texts):
        return [self._vector(text) for text in texts]

    def _vector(self, text):
        lower = text.lower()
        if any(word in lower for word in ["refund", "cancel", "cancelled"]):
            return [1.0, 0.0, 0.0]
        if any(word in lower for word in ["bag", "baggage"]):
            return [0.0, 1.0, 0.0]
        if any(word in lower for word in ["hotel", "pet", "student", "miles"]):
            return [0.0, 0.0, 1.0]
        return [0.1, 0.1, 0.0]


class FakeLLMClient:
    def __init__(self, response="Grounded answer from retrieved policy context."):
        self.response = response
        self.calls = []

    def enabled(self):
        return True

    def complete(self, messages):
        self.calls.append(messages)
        return self.response


def _policy_file(tmp_path):
    policy = tmp_path / "policy.md"
    policy.write_text(
        "# Airline Policy\n\n"
        "## Refund Policy\n"
        "Refundable tickets may be cancelled before departure in the demo system.\n\n"
        "## Baggage Policy\n"
        "Customers may bring one checked bag in the demo system.\n",
        encoding="utf-8",
    )
    return policy


def _settings(tmp_path, **overrides):
    values = {
        "rag_retriever_mode": "embedding",
        "policy_answer_mode": "llm",
        "llm_api_key": "test-llm-key",
        "embedding_api_key": "test-embedding-key",
        "rag_embedding_cache": str(tmp_path / "policy_embeddings.json"),
        "rag_top_k": 3,
        "rag_similarity_threshold": 0.75,
    }
    values.update(overrides)
    return Settings(**values)


def test_embedding_rag_uses_relevant_chunks_and_backend_citations(tmp_path):
    llm = FakeLLMClient()
    rag = PolicyRAG(
        str(_policy_file(tmp_path)),
        settings=_settings(tmp_path),
        llm_client=llm,
        embedding_client=FakeEmbeddingClient(),
    )

    result = rag.query("Can I get a refund if I cancel my ticket?")

    assert result["answer"] == "Grounded answer from retrieved policy context."
    assert result["citations"]
    assert result["citations"][0]["section"] == "Refund Policy"
    assert result["execution"]["retriever_used"] == "embedding"
    assert result["execution"]["answer_mode_used"] == "llm"
    assert result["execution"]["fallback_reason"] is None
    assert llm.calls


def test_unsupported_policy_question_below_threshold_does_not_call_grounded_llm(tmp_path):
    llm = FakeLLMClient()
    rag = PolicyRAG(
        str(_policy_file(tmp_path)),
        settings=_settings(tmp_path),
        llm_client=llm,
        embedding_client=FakeEmbeddingClient(),
    )

    result = rag.query("Do you provide hotel vouchers for pets?")

    assert result["citations"] == []
    assert "cannot confirm" in result["answer"].lower()
    assert result["execution"]["retriever_used"] == "embedding"
    assert result["execution"]["answer_mode_used"] == "none"
    assert "below similarity threshold" in result["execution"]["fallback_reason"]
    assert llm.calls == []


def test_forced_embedding_mode_missing_config_raises_controlled_error(tmp_path):
    rag = PolicyRAG(
        str(_policy_file(tmp_path)),
        settings=_settings(tmp_path, embedding_api_key="", llm_api_key=""),
        llm_client=FakeLLMClient(),
        embedding_client=None,
    )

    with pytest.raises(RAGConfigurationError):
        rag.query("Can I get a refund if I cancel my ticket?")
