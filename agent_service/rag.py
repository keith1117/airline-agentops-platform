import hashlib
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import Settings, settings as default_settings
from .llm import EmbeddingClient, LLMClient


CHUNKING_VERSION = "markdown-section-v1"


class RAGConfigurationError(RuntimeError):
    pass


class PolicyRAG:
    """Policy QA with keyword fallback and optional embedding-grounded LLM answers."""

    STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "can",
        "customer",
        "demo",
        "does",
        "for",
        "flight",
        "i",
        "is",
        "it",
        "me",
        "my",
        "of",
        "or",
        "platform",
        "support",
        "system",
        "the",
        "this",
        "to",
        "what",
        "with",
    }

    def __init__(
        self,
        policy_path: str,
        settings: Settings = default_settings,
        llm_client: Optional[Any] = None,
        embedding_client: Optional[Any] = None,
    ) -> None:
        self.settings = settings
        self.policy_path = Path(policy_path)
        self.llm_client = llm_client or LLMClient(settings)
        self.embedding_client = embedding_client or EmbeddingClient(settings)
        self.chunks = self._load_chunks()

    def _load_chunks(self) -> List[Dict[str, str]]:
        if not self.policy_path.exists():
            return []
        text = self.policy_path.read_text(encoding="utf-8")
        sections = re.split(r"\n(?=## )", text)
        chunks: List[Dict[str, str]] = []
        for idx, section in enumerate(sections):
            stripped = section.strip()
            if not stripped:
                continue
            header = stripped.splitlines()[0].replace("#", "").strip()
            chunks.append(
                {
                    "chunk_id": f"policy-{_slug(header)}-{idx}",
                    "source": str(self.policy_path),
                    "section": header,
                    "text": stripped,
                }
            )
        return chunks

    def query(self, question: str, limit: Optional[int] = None) -> Dict[str, Any]:
        top_k = limit or self.settings.rag_top_k
        execution = {
            "request_path": "policy_rag",
            "router_used": "bypassed",
            "retriever_used": "none",
            "answer_mode_used": "none",
            "fallback_reason": None,
        }
        hits = self._retrieve(question, top_k, execution)
        if not hits:
            return self._no_context(execution)

        answer = self._answer(question, hits, execution)
        return {
            "answer": answer,
            "citations": [_citation(hit["chunk"]) for hit in hits],
            "retrieval_scores": [
                {
                    "chunk_id": hit["chunk"]["chunk_id"],
                    "section": hit["chunk"]["section"],
                    "similarity": hit["score"],
                }
                for hit in hits
            ],
            "execution": execution,
        }

    def _retrieve(self, question: str, top_k: int, execution: Dict[str, Any]) -> List[Dict[str, Any]]:
        mode = self.settings.rag_retriever_mode
        if mode == "keyword":
            execution["retriever_used"] = "keyword"
            return self._keyword_hits(question, top_k)

        if mode in {"auto", "embedding"}:
            if not self._embedding_enabled():
                if mode == "embedding":
                    raise RAGConfigurationError("Embedding retriever is forced but EMBEDDING_API_KEY is not configured.")
                execution["retriever_used"] = "keyword"
                execution["fallback_reason"] = "embedding unavailable; used keyword retriever"
                return self._keyword_hits(question, top_k)
            try:
                hits = self._embedding_hits(question, top_k)
                execution["retriever_used"] = "embedding"
            except Exception as exc:
                if mode == "embedding":
                    raise RAGConfigurationError(f"Embedding retrieval failed: {exc}") from exc
                execution["retriever_used"] = "keyword"
                execution["fallback_reason"] = f"embedding retrieval failed; used keyword retriever: {exc}"
                return self._keyword_hits(question, top_k)
            if hits and hits[0]["score"] >= self.settings.rag_similarity_threshold:
                return [hit for hit in hits if hit["score"] >= self.settings.rag_similarity_threshold]
            best = hits[0]["score"] if hits else 0.0
            execution["fallback_reason"] = (
                f"below similarity threshold: best={best:.3f}, threshold={self.settings.rag_similarity_threshold:.3f}"
            )
            return []

        raise RAGConfigurationError(f"Unsupported RAG_RETRIEVER_MODE: {mode}")

    def _answer(self, question: str, hits: List[Dict[str, Any]], execution: Dict[str, Any]) -> str:
        mode = self.settings.policy_answer_mode
        if mode == "extractive":
            execution["answer_mode_used"] = "extractive"
            return "Based on the airline policy knowledge base: " + self._summarize(
                question, "\n\n".join(hit["chunk"]["text"] for hit in hits)
            )
        if mode in {"auto", "llm"}:
            if not self._llm_enabled():
                if mode == "llm":
                    raise RAGConfigurationError("Grounded policy answer is forced but LLM_API_KEY is not configured.")
                execution["answer_mode_used"] = "extractive"
                _append_fallback(execution, "LLM unavailable; used extractive answer")
                return "Based on the airline policy knowledge base: " + self._summarize(
                    question, "\n\n".join(hit["chunk"]["text"] for hit in hits)
                )
            try:
                execution["answer_mode_used"] = "llm"
                return self._grounded_answer(question, hits)
            except Exception as exc:
                if mode == "llm":
                    raise RAGConfigurationError(f"Grounded policy answer failed: {exc}") from exc
                execution["answer_mode_used"] = "extractive"
                _append_fallback(execution, f"grounded answer failed; used extractive answer: {exc}")
                return "Based on the airline policy knowledge base: " + self._summarize(
                    question, "\n\n".join(hit["chunk"]["text"] for hit in hits)
                )
        raise RAGConfigurationError(f"Unsupported POLICY_ANSWER_MODE: {mode}")

    def _embedding_enabled(self) -> bool:
        return bool(getattr(self.embedding_client, "enabled", lambda: False)())

    def _llm_enabled(self) -> bool:
        return bool(getattr(self.llm_client, "enabled", lambda: False)())

    def _keyword_hits(self, question: str, limit: int) -> List[Dict[str, Any]]:
        q_tokens = self._tokens(question)
        ranked = []
        for chunk in self.chunks:
            score = len(q_tokens & self._tokens(chunk["text"]))
            if score:
                ranked.append((float(score), chunk))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [{"score": score, "chunk": chunk} for score, chunk in ranked[:limit]]

    def _embedding_hits(self, question: str, limit: int) -> List[Dict[str, Any]]:
        cache = self._load_or_build_embedding_cache()
        question_vector = self.embedding_client.embed([question])[0]
        hits = []
        for chunk in cache["chunks"]:
            score = _cosine(question_vector, chunk["embedding"])
            hits.append(
                {
                    "score": score,
                    "chunk": {
                        "chunk_id": chunk["chunk_id"],
                        "source": chunk["source"],
                        "section": chunk["section"],
                        "text": chunk["text"],
                    },
                }
            )
        hits.sort(key=lambda item: item["score"], reverse=True)
        return hits[:limit]

    def _load_or_build_embedding_cache(self) -> Dict[str, Any]:
        cache_path = Path(self.settings.rag_embedding_cache)
        expected = self._cache_identity()
        try:
            if cache_path.exists():
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                if _cache_matches(data, expected):
                    return data
        except Exception:
            pass
        return self._build_embedding_cache(cache_path, expected)

    def _build_embedding_cache(self, cache_path: Path, expected: Dict[str, Any]) -> Dict[str, Any]:
        vectors = self.embedding_client.embed([chunk["text"] for chunk in self.chunks]) if self.chunks else []
        actual_dimensions = len(vectors[0]) if vectors else self.settings.embedding_dimensions
        data = {
            **expected,
            "embedding_dimensions": actual_dimensions,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "chunks": [
                {
                    **chunk,
                    "embedding": vector,
                }
                for chunk, vector in zip(self.chunks, vectors)
            ],
        }
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", delete=False, dir=str(cache_path.parent), encoding="utf-8") as tmp:
            json.dump(data, tmp)
            tmp_path = tmp.name
        os.replace(tmp_path, cache_path)
        return data

    def _cache_identity(self) -> Dict[str, Any]:
        return {
            "embedding_model": self.settings.embedding_model,
            "embedding_dimensions_requested": self.settings.embedding_dimensions,
            "policy_path": str(self.policy_path),
            "policy_sha256": _sha256(self.policy_path),
            "chunking_version": CHUNKING_VERSION,
        }

    def _grounded_answer(self, question: str, hits: List[Dict[str, Any]]) -> str:
        context = "\n\n".join(
            f"[{hit['chunk']['chunk_id']}] {hit['chunk']['section']}\n{hit['chunk']['text']}" for hit in hits
        )
        prompt = (
            "Answer as a customer-facing airline assistant using only the provided policy context. "
            "Give the direct practical answer first. If the customer's exact ticket or flight status is needed, "
            "say what information is needed and explain the relevant policy rule briefly. "
            "If the context does not support the answer, say the current policy knowledge base cannot confirm it. "
            "Do not invent fees, exceptions, eligibility, guarantees, or citations."
        )
        return self.llm_client.complete(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Question: {question}\n\nPolicy context:\n{context}"},
            ]
        )

    @staticmethod
    def _tokens(text: str) -> set[str]:
        tokens = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", text.lower()))
        return {token for token in tokens if token not in PolicyRAG.STOPWORDS}

    def _summarize(self, question: str, context: str) -> str:
        question_tokens = self._tokens(question)
        sentences = re.split(r"(?<=[.!?。])\s+", context.replace("\n", " "))
        scored = []
        for sentence in sentences:
            score = len(question_tokens & self._tokens(sentence))
            if score:
                scored.append((score, sentence.strip()))
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = [sentence for _, sentence in scored[:3] if sentence]
        return " ".join(selected) if selected else context[:500]

    @staticmethod
    def _no_context(execution: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "answer": "I cannot confirm this from the current airline policy knowledge base.",
            "citations": [],
            "retrieval_scores": [],
            "execution": execution,
        }


def _citation(chunk: Dict[str, str]) -> Dict[str, str]:
    return {
        "source": chunk["source"],
        "section": chunk["section"],
        "chunk_id": chunk["chunk_id"],
    }


def _cache_matches(data: Dict[str, Any], expected: Dict[str, Any]) -> bool:
    return all(data.get(key) == value for key, value in expected.items()) and isinstance(data.get("chunks"), list)


def _sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cosine(left: List[float], right: List[float]) -> float:
    if len(left) != len(right) or not left or not right:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "section"


def _append_fallback(execution: Dict[str, Any], reason: str) -> None:
    if execution.get("fallback_reason"):
        execution["fallback_reason"] += f"; {reason}"
    else:
        execution["fallback_reason"] = reason
