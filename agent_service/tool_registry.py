from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List


class ToolAccessError(Exception):
    pass


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    roles: Iterable[str]
    handler: Callable[..., Dict[str, Any]]
    risk: str = "safe_read"


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def names_for_role(self, role: str) -> List[str]:
        return [name for name, tool in self._tools.items() if role in tool.roles]

    def risk_for(self, name: str) -> str:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name].risk

    def call(self, role: str, name: str, **kwargs: Any) -> Dict[str, Any]:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        tool = self._tools[name]
        if role not in tool.roles:
            raise ToolAccessError(f"Role '{role}' cannot call tool '{name}'")
        if tool.risk == "human_confirmed" or name == "create_booking_intent":
            raise ToolAccessError(f"Tool '{name}' requires the separate human confirmation workflow")
        return tool.handler(**kwargs)
