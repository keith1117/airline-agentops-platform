import json
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class MetricsCollector:
    def __init__(self, log_path: Optional[str] = None) -> None:
        self.log_path = log_path
        self._lock = threading.Lock()
        self._total_requests = 0
        self._error_count = 0
        self._total_latency_ms = 0
        self._endpoints: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "error_count": 0, "total_latency_ms": 0, "tool_calls": 0}
        )
        self._roles: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "tool_calls": 0, "error_count": 0})

    def record_request(
        self,
        *,
        endpoint: str,
        method: str,
        status_code: int,
        latency_ms: int,
        role: Optional[str] = None,
        tool_count: int = 0,
        error: bool = False,
    ) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "method": method,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "role": role or "unknown",
            "tool_count": tool_count,
            "error": error,
        }
        key = f"{method} {endpoint}"
        with self._lock:
            self._total_requests += 1
            self._total_latency_ms += latency_ms
            if error:
                self._error_count += 1

            endpoint_stats = self._endpoints[key]
            endpoint_stats["count"] += 1
            endpoint_stats["total_latency_ms"] += latency_ms
            endpoint_stats["tool_calls"] += tool_count
            if error:
                endpoint_stats["error_count"] += 1

            role_stats = self._roles[role or "unknown"]
            role_stats["count"] += 1
            role_stats["tool_calls"] += tool_count
            if error:
                role_stats["error_count"] += 1

            if self.log_path:
                path = Path(self.log_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as fp:
                    fp.write(json.dumps(event, default=str) + "\n")

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            endpoints = {key: self._summarize_stats(value) for key, value in self._endpoints.items()}
            roles = {key: dict(value) for key, value in self._roles.items()}
            return {
                "total_requests": self._total_requests,
                "error_count": self._error_count,
                "avg_latency_ms": self._avg(self._total_latency_ms, self._total_requests),
                "endpoints": endpoints,
                "roles": roles,
            }

    @classmethod
    def _summarize_stats(cls, stats: Dict[str, Any]) -> Dict[str, Any]:
        summarized = dict(stats)
        summarized["avg_latency_ms"] = cls._avg(stats["total_latency_ms"], stats["count"])
        del summarized["total_latency_ms"]
        return summarized

    @staticmethod
    def _avg(total: int, count: int) -> float:
        if count == 0:
            return 0
        return round(total / count, 2)
