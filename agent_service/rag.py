import re
from pathlib import Path
from typing import Dict, List


class PolicyRAG:
    """Small local retriever for stable demos without a vector DB dependency."""

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

    def __init__(self, policy_path: str) -> None:
        self.policy_path = Path(policy_path)
        self.chunks = self._load_chunks()

    def _load_chunks(self) -> List[Dict[str, str]]:
        if not self.policy_path.exists():
            return []
        text = self.policy_path.read_text(encoding="utf-8")
        sections = re.split(r"\n(?=## )", text)
        chunks: List[Dict[str, str]] = []
        for idx, section in enumerate(sections):
            header = section.strip().splitlines()[0].replace("#", "").strip()
            body = section.strip()
            if body:
                chunks.append(
                    {
                        "chunk_id": f"policy-{idx}",
                        "source": str(self.policy_path),
                        "section": header,
                        "text": body,
                    }
                )
        return chunks

    @staticmethod
    def _tokens(text: str) -> set[str]:
        tokens = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", text.lower()))
        return {token for token in tokens if token not in PolicyRAG.STOPWORDS}

    def query(self, question: str, limit: int = 3) -> Dict[str, object]:
        q_tokens = self._tokens(question)
        ranked = []
        for chunk in self.chunks:
            score = len(q_tokens & self._tokens(chunk["text"]))
            if score:
                ranked.append((score, chunk))
        ranked.sort(key=lambda item: item[0], reverse=True)
        hits = [chunk for _, chunk in ranked[:limit]]
        if not hits:
            return {
                "answer": "I cannot confirm this from the current airline policy knowledge base.",
                "citations": [],
            }
        context = "\n\n".join(hit["text"] for hit in hits)
        answer = (
            "Based on the airline policy knowledge base: "
            + self._summarize(question, context)
        )
        citations = [
            {
                "source": hit["source"],
                "section": hit["section"],
                "chunk_id": hit["chunk_id"],
            }
            for hit in hits
        ]
        return {"answer": answer, "citations": citations}

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
