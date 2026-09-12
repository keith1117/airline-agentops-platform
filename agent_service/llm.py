import json
import re
from typing import Any, Dict, List, Optional

import requests

from .config import Settings, settings as default_settings


class LLMConfigurationError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def enabled(self) -> bool:
        return bool(self.settings.llm_api_key)

    def complete(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        if not self.enabled():
            raise LLMConfigurationError("LLM_API_KEY is not configured.")
        url = self.settings.llm_base_url.rstrip("/") + "/chat/completions"
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.settings.llm_model, "messages": messages, "temperature": temperature},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def complete_json(self, messages: List[Dict[str, str]], temperature: float = 0.0) -> Dict[str, Any]:
        content = self.complete(messages, temperature=temperature)
        return parse_json_object(content)

    def complete_tool_call(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        temperature: float = 0.0,
    ) -> Optional[Dict[str, Any]]:
        if not self.enabled():
            raise LLMConfigurationError("LLM_API_KEY is not configured.")
        url = self.settings.llm_base_url.rstrip("/") + "/chat/completions"
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.llm_model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": temperature,
            },
            timeout=30,
        )
        resp.raise_for_status()
        message = resp.json()["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return None
        call = tool_calls[0]
        function = call.get("function") or {}
        args = function.get("arguments") or "{}"
        return {"name": function.get("name"), "args": parse_json_object(args)}


class EmbeddingClient:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def enabled(self) -> bool:
        return bool(self.settings.embedding_api_key)

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not self.enabled():
            raise LLMConfigurationError("EMBEDDING_API_KEY is not configured.")
        url = self.settings.embedding_base_url.rstrip("/") + "/embeddings"
        payload: Dict[str, Any] = {"model": self.settings.embedding_model, "input": texts}
        if self.settings.embedding_dimensions is not None:
            payload["dimensions"] = self.settings.embedding_dimensions
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.settings.embedding_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        vectors = sorted(data["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in vectors]


def parse_json_object(content: str) -> Dict[str, Any]:
    stripped = content.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, flags=re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("LLM response must be a JSON object.")
    return data


class LLMRouter:
    CUSTOMER_TOOLS = [
        "search_flights",
        "get_customer_trips",
        "cancel_customer_ticket",
        "create_booking_intent",
        "remember_user_preference",
        "answer_policy_question",
    ]
    STAFF_TOOLS = [
        "get_sales_report",
        "analyze_reviews",
        "get_flight_load_factor",
        "get_route_performance",
        "answer_policy_question",
    ]

    def __init__(self, client: Optional[LLMClient] = None) -> None:
        self.client = client or LLMClient()

    def enabled(self) -> bool:
        return self.client.enabled()

    def route(self, role: str, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        tools = self.CUSTOMER_TOOLS if role == "customer" else self.STAFF_TOOLS
        system = (
            "You are a routing planner for an airline AgentOps system. "
            "Return only JSON with keys intent, tool, args, needs_clarification, clarification_question. "
            "Choose one registered tool or null. Do not execute SQL or transactions. "
            "Use answer_policy_question only for informational airline policy questions. "
            "Use create_booking_intent only as a routing label for booking or purchase requests; "
            "the backend must only display a bookable flight and hand off to the Search Flights page, not complete checkout in chat. "
            "Set needs_clarification if flight details are missing. "
            "For month-level flight searches, put the resolved month in args.month as YYYY-MM when the user states a month. "
            "For year-level flight searches, put args.period as this_year or next_year. Do not put a bare year in travel_date. "
            "For staff sales reports, put args.period as this_month, last_month, this_year, last_year, past_month, or past_year. "
            "If the staff provides two exact report dates, put them in args.start_date and args.end_date as YYYY-MM-DD. "
            "Use cancel_customer_ticket only when the customer asks to cancel a specific existing ticket and a ticket_id is available; otherwise ask for the ticket number. "
            "Never choose confirm_booking. "
            "Use remember_user_preference only when the user explicitly asks to remember or save a preference. "
            f"Allowed tools for this role: {', '.join(tools)}."
        )
        user = {
            "role": role,
            "message": message,
            "context": context or {},
            "schema": {
                "intent": "short intent label",
                "tool": "allowed tool name or null",
                "args": "object of tool arguments",
                "needs_clarification": "boolean",
                "clarification_question": "string or null",
            },
        }
        plan = self.client.complete_json(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.0,
        )
        return normalize_plan(plan)


class NativeToolCallingRouter:
    router_kind = "native"

    def __init__(self, client: Optional[LLMClient] = None) -> None:
        self.client = client or LLMClient()

    def enabled(self) -> bool:
        return self.client.enabled()

    def route(self, role: str, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        tools = native_tool_schemas(role)
        system = (
            "You are an airline AgentOps tool router. Choose a tool only when the user request clearly "
            "belongs to airline booking, customer trips, airline policy, travel preferences, or staff analytics. "
            "Do not call tools for unrelated requests. Never confirm a booking directly. "
            "Use policy tools only for informational policy questions. For booking or payment transactions, route to booking tools "
            "only so the backend can display a flight and hand off to manual checkout; do not imply chat can complete a purchase."
        )
        call = self.client.complete_tool_call(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps({"role": role, "message": message, "context": context or {}}, ensure_ascii=False)},
            ],
            tools=tools,
            temperature=0.0,
        )
        if not call or not call.get("name"):
            return normalize_plan({"intent": "unknown", "tool": None, "args": {}, "needs_clarification": False})
        return normalize_plan(
            {
                "intent": call["name"],
                "tool": call["name"],
                "args": call.get("args") or {},
                "needs_clarification": False,
                "clarification_question": None,
            }
        )


def native_tool_schemas(role: str) -> List[Dict[str, Any]]:
    names = LLMRouter.CUSTOMER_TOOLS if role == "customer" else LLMRouter.STAFF_TOOLS
    schemas = {
        "search_flights": {
            "description": "Search available future flights in the airline database.",
            "properties": {
                "departure_airport": {"type": "string"},
                "arrival_airport": {"type": "string"},
                "airline_name": {"type": "string"},
                "travel_date": {"type": "string", "description": "Exact date as YYYY-MM-DD only. Do not use this for bare years."},
                "month": {"type": "string", "description": "YYYY-MM for month-level searches such as August 2026"},
                "period": {"type": "string", "description": "Optional period: next_month, this_year, or next_year"},
                "max_price": {"type": "number"},
            },
        },
        "get_customer_trips": {"description": "Return the authenticated customer's recent trips.", "properties": {}},
        "cancel_customer_ticket": {
            "description": "Request a cancellation preview. The backend requires a separate human confirmation before cancelling.",
            "properties": {"ticket_id": {"type": "integer"}},
            "required": ["ticket_id"],
        },
        "create_booking_intent": {
            "description": "Route a customer booking or purchase request for a specific flight. The backend displays a bookable flight and hands off to the Search Flights page instead of completing checkout in chat.",
            "properties": {
                "airline_name": {"type": "string"},
                "flight_number": {"type": "string"},
                "departure_date_time": {"type": "string"},
                "departure_airport": {"type": "string"},
                "arrival_airport": {"type": "string"},
                "travel_date": {"type": "string"},
                "month": {"type": "string", "description": "YYYY-MM for month-level searches"},
            },
        },
        "remember_user_preference": {
            "description": "Save travel preferences only when the user explicitly asks to remember or save them.",
            "properties": {
                "departure_city": {"type": "string"},
                "destination_city": {"type": "string"},
                "max_budget": {"type": "number"},
                "preferred_airline": {"type": "string"},
            },
        },
        "answer_policy_question": {
            "description": "Answer informational airline policy questions using the policy knowledge base.",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
        "get_sales_report": {
            "description": "Return a staff ticket sales report for the requested time range.",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["this_month", "last_month", "this_year", "last_year", "past_month", "past_year"],
                },
                "start_date": {"type": "string", "description": "Custom range start as YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "Custom range inclusive end as YYYY-MM-DD"},
            },
        },
        "analyze_reviews": {
            "description": "Analyze staff airline reviews and ratings by flight or route.",
            "properties": {
                "target": {"type": "string", "enum": ["flight", "route"]},
                "order": {"type": "string", "enum": ["worst", "best"]},
            },
        },
        "get_flight_load_factor": {"description": "Return staff load-factor analytics.", "properties": {}},
        "get_route_performance": {"description": "Return staff route performance analytics.", "properties": {}},
    }
    result = []
    for name in names:
        schema = schemas[name]
        result.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": schema["description"],
                    "parameters": {
                        "type": "object",
                        "properties": schema.get("properties", {}),
                        "required": schema.get("required", []),
                        "additionalProperties": False,
                    },
                },
            }
        )
    return result


def normalize_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "intent": str(plan.get("intent") or "unknown"),
        "tool": plan.get("tool"),
        "args": plan.get("args") if isinstance(plan.get("args"), dict) else {},
        "needs_clarification": bool(plan.get("needs_clarification")),
        "clarification_question": plan.get("clarification_question"),
    }
