from typing import List, Dict

import requests

from .config import settings


class LLMClient:
    def enabled(self) -> bool:
        return bool(settings.openai_api_key)

    def complete(self, messages: List[Dict[str, str]]) -> str:
        if not self.enabled():
            return ""
        url = settings.openai_base_url.rstrip("/") + "/chat/completions"
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={"model": settings.llm_model, "messages": messages, "temperature": 0.2},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

