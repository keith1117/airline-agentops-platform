import json
import re
import time
from datetime import date
from typing import Any, Dict, List, Optional

from .config import settings
from .db import get_conn
from .rag import PolicyRAG
from .tool_registry import Tool, ToolRegistry
from .tools.customer_tools import (
    answer_policy_question,
    confirm_booking,
    create_booking_intent,
    get_user_preferences,
    get_customer_trips,
    parse_airports,
    remember_user_preference,
    search_flights,
)
from .tools.staff_tools import (
    analyze_reviews,
    get_flight_load_factor,
    get_route_performance,
    get_sales_report,
)


class ReActAgent:
    def __init__(self, rag: PolicyRAG) -> None:
        self.rag = rag
        self.registry = ToolRegistry()
        self._register_tools()

    def _register_tools(self) -> None:
        self.registry.register(Tool("search_flights", "Search available future flights.", ["customer"], search_flights))
        self.registry.register(Tool("get_customer_trips", "Return a customer's trips.", ["customer"], get_customer_trips))
        self.registry.register(Tool("create_booking_intent", "Create pending booking intent.", ["customer"], create_booking_intent))
        self.registry.register(Tool("confirm_booking", "Confirm a pending mock booking.", ["customer"], confirm_booking))
        self.registry.register(Tool("remember_user_preference", "Save customer travel preferences.", ["customer"], remember_user_preference))
        self.registry.register(Tool("get_user_preferences", "Get customer travel preferences.", ["customer"], get_user_preferences))
        self.registry.register(
            Tool(
                "answer_policy_question",
                "Answer policy questions from the knowledge base.",
                ["customer", "staff"],
                lambda question: answer_policy_question(self.rag, question),
            )
        )
        self.registry.register(Tool("get_sales_report", "Return monthly ticket sales.", ["staff"], get_sales_report))
        self.registry.register(Tool("analyze_reviews", "Analyze ratings and comments.", ["staff"], analyze_reviews))
        self.registry.register(Tool("get_flight_load_factor", "Return load factor by flight.", ["staff"], get_flight_load_factor))
        self.registry.register(Tool("get_route_performance", "Return route performance.", ["staff"], get_route_performance))

    def customer_chat(self, session_id: str, customer_email: str, message: str) -> Dict[str, Any]:
        started = time.time()
        tool_calls: List[Dict[str, Any]] = []
        citations: List[Dict[str, Any]] = []
        pending = None
        answer = ""
        error = None
        reasoning = "Classify customer request and call the safest allowed tool."
        try:
            lower = message.lower()
            if self._is_policy_question(lower):
                result = self.registry.call("customer", "answer_policy_question", question=message)
                tool_calls.append({"name": "answer_policy_question", "args": {"question": message}, "result": result})
                answer = result["answer"]
                citations = result.get("citations", [])
            elif any(word in lower for word in ["trip", "order", "ticket", "my flight", "我的", "订单"]):
                result = self.registry.call("customer", "get_customer_trips", customer_email=customer_email)
                tool_calls.append({"name": "get_customer_trips", "args": {"customer_email": customer_email}, "result": result})
                answer = self._format_trips(result)
            elif any(word in lower for word in ["prefer", "remember", "usually", "preference", "偏好", "记住"]):
                dep, arr = parse_airports(message)
                max_price = self._extract_budget(message)
                airline = self._extract_airline(message)
                result = self.registry.call(
                    "customer",
                    "remember_user_preference",
                    customer_email=customer_email,
                    departure_city=dep,
                    destination_city=arr,
                    max_budget=max_price,
                    preferred_airline=airline,
                )
                tool_calls.append({"name": "remember_user_preference", "args": {"departure_city": dep, "destination_city": arr, "max_budget": max_price, "preferred_airline": airline}, "result": result})
                saved_parts = []
                if dep and arr:
                    saved_parts.append(f"route {dep} -> {arr}")
                if max_price is not None:
                    saved_parts.append(f"max budget ${max_price:g}")
                if airline:
                    saved_parts.append(f"preferred airline {airline}")
                suffix = ", ".join(saved_parts) if saved_parts else "the available preferences"
                answer = f"I saved {suffix} for future searches."
            elif any(word in lower for word in ["book", "buy", "purchase", "reserve", "订", "买"]):
                flight_number = self._extract_flight_number(message)
                dep_time = self._extract_datetime(message)
                airline = self._extract_airline(message) or "United"
                if flight_number and dep_time:
                    result = self.registry.call(
                        "customer",
                        "create_booking_intent",
                        customer_email=customer_email,
                        airline_name=airline,
                        flight_number=flight_number,
                        departure_date_time=dep_time,
                    )
                    tool_calls.append({"name": "create_booking_intent", "args": {"flight_number": flight_number}, "result": result})
                    if "error" in result:
                        answer = result["error"]
                    else:
                        pending = result
                        answer = (
                            f"I created a pending booking intent for {airline} flight {flight_number}. "
                            "Please confirm before the mock ticket is issued."
                        )
                else:
                    dep, arr = parse_airports(message)
                    result = self.registry.call("customer", "search_flights", departure_airport=dep, arrival_airport=arr)
                    tool_calls.append({"name": "search_flights", "args": {"departure_airport": dep, "arrival_airport": arr}, "result": result})
                    answer = self._format_flights(result) + " Tell me the flight number and departure time to create a booking intent."
            else:
                dep, arr = parse_airports(message)
                period = "next_month" if "next month" in lower else None
                max_price = self._extract_budget(message)
                airline = self._extract_airline(message)
                if not dep and not arr:
                    prefs = self.registry.call("customer", "get_user_preferences", customer_email=customer_email)
                    tool_calls.append({"name": "get_user_preferences", "args": {"customer_email": customer_email}, "result": prefs})
                    pref = prefs.get("preferences") or {}
                    dep = pref.get("departure_city")
                    arr = pref.get("destination_city")
                    max_price = max_price if max_price is not None else pref.get("max_budget")
                    airline = airline or pref.get("preferred_airline")
                result = self.registry.call(
                    "customer",
                    "search_flights",
                    departure_airport=dep,
                    arrival_airport=arr,
                    airline_name=airline,
                    period=period,
                    max_price=max_price,
                )
                tool_calls.append(
                    {
                        "name": "search_flights",
                        "args": {"departure_airport": dep, "arrival_airport": arr, "airline_name": airline, "period": period, "max_price": max_price},
                        "result": result,
                    }
                )
                answer = self._format_flights(result)
        except Exception as exc:
            error = str(exc)
            answer = f"The agent hit a controlled error: {error}"
        self._trace(session_id, "customer", customer_email, message, reasoning, tool_calls, answer, started, error)
        return {"answer": answer, "citations": citations, "tool_calls": tool_calls, "pending_confirmation": pending}

    def staff_chat(self, session_id: str, staff_username: str, airline_name: str, message: str) -> Dict[str, Any]:
        started = time.time()
        tool_calls: List[Dict[str, Any]] = []
        answer = ""
        table = None
        error = None
        reasoning = "Classify staff analytics request and call staff-only reporting tools."
        try:
            lower = message.lower()
            if self._is_policy_question(lower):
                result = self.registry.call("staff", "answer_policy_question", question=message)
                tool_calls.append({"name": "answer_policy_question", "args": {"question": message}, "result": result})
                answer = result["answer"]
            elif any(word in lower for word in ["review", "rating", "comment", "差评", "评分"]):
                result = self.registry.call("staff", "analyze_reviews", airline_name=airline_name)
                tool_calls.append({"name": "analyze_reviews", "args": {"airline_name": airline_name}, "result": result})
                table = result.get("summary")
                answer = self._format_review_analysis(result)
            elif any(word in lower for word in ["load", "capacity", "full", "seat", "载客", "满座"]):
                result = self.registry.call("staff", "get_flight_load_factor", airline_name=airline_name)
                tool_calls.append({"name": "get_flight_load_factor", "args": {"airline_name": airline_name}, "result": result})
                table = result.get("rows")
                answer = self._format_table("Highest load factor flights", result.get("rows", []))
            elif any(word in lower for word in ["route", "popular", "performance", "热门", "航线"]):
                result = self.registry.call("staff", "get_route_performance", airline_name=airline_name)
                tool_calls.append({"name": "get_route_performance", "args": {"airline_name": airline_name}, "result": result})
                table = result.get("rows")
                answer = self._format_table("Route performance", result.get("rows", []))
            else:
                result = self.registry.call("staff", "get_sales_report", airline_name=airline_name)
                tool_calls.append({"name": "get_sales_report", "args": {"airline_name": airline_name}, "result": result})
                table = result.get("rows")
                answer = self._format_table("Sales report", result.get("rows", []))
        except Exception as exc:
            error = str(exc)
            answer = f"The staff copilot hit a controlled error: {error}"
        self._trace(session_id, "staff", staff_username, message, reasoning, tool_calls, answer, started, error)
        return {"answer": answer, "tool_calls": tool_calls, "tables": table}

    def confirm_booking(self, booking_intent_id: int, customer_email: str, idempotency_key: str) -> Dict[str, Any]:
        return self.registry.call(
            "customer",
            "confirm_booking",
            booking_intent_id=booking_intent_id,
            customer_email=customer_email,
            idempotency_key=idempotency_key,
        )

    def _trace(self, session_id, role, principal, message, reasoning, tool_calls, answer, started, error=None) -> None:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_sessions(id, role, principal)
                    VALUES(%s,%s,%s)
                    ON DUPLICATE KEY UPDATE updated_at=NOW()
                    """,
                    (session_id, role, principal),
                )
                cur.execute(
                    """
                    INSERT INTO agent_traces(session_id, role, principal, user_message, reasoning,
                                             tool_calls, final_answer, latency_ms, error)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        session_id,
                        role,
                        principal,
                        message,
                        reasoning,
                        json.dumps(tool_calls, default=str),
                        answer,
                        int((time.time() - started) * 1000),
                        error,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _is_policy_question(lower: str) -> bool:
        return any(word in lower for word in ["refund", "baggage", "bag", "delay", "cancel", "policy", "payment", "行李", "退款", "延误", "政策"])

    @staticmethod
    def _extract_budget(message: str) -> Optional[float]:
        match = re.search(r"(?:under|below|less than|price\s*<|预算|低于)\s*\$?(\d+(?:\.\d+)?)", message.lower())
        return float(match.group(1)) if match else None

    @staticmethod
    def _extract_flight_number(message: str) -> Optional[str]:
        match = re.search(r"\b(?:flight\s*)?([A-Z]?\d{2,5})\b", message, re.IGNORECASE)
        return match.group(1).upper() if match else None

    @staticmethod
    def _extract_airline(message: str) -> Optional[str]:
        if "united" in message.lower():
            return "United"
        if "jetblue" in message.lower():
            return "JetBlue"
        return None

    @staticmethod
    def _extract_datetime(message: str) -> Optional[str]:
        match = re.search(r"(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?)", message)
        if not match:
            return None
        value = match.group(1).replace("T", " ")
        if len(value) == 10:
            value += " 00:00:00"
        if len(value) == 16:
            value += ":00"
        return value

    @staticmethod
    def _format_flights(result: Dict[str, Any]) -> str:
        rows = result.get("flights", [])
        if not rows:
            return "No matching future flights were found in the current inventory."
        lines = ["Here are matching database-backed flights:"]
        for row in rows[:6]:
            lines.append(
                f"- {row['airline_name']} {row['flight_number']}: {row['departure_airport']} -> "
                f"{row['arrival_airport']} at {row['departure_date_time']}, price ${row['base_price']}, "
                f"seats left {row['seats_left']}."
            )
        return "\n".join(lines)

    @staticmethod
    def _format_trips(result: Dict[str, Any]) -> str:
        rows = result.get("trips", [])
        if not rows:
            return "No trips were found for this customer."
        return "\n".join(
            ["Here are this customer's recent trips:"]
            + [
                f"- Ticket {row['ticket_ID']}: {row['airline_name']} {row['flight_number']} "
                f"{row['departure_airport']} -> {row['arrival_airport']} at {row['departure_date_time']} ({row['status']})"
                for row in rows[:8]
            ]
        )

    @staticmethod
    def _format_table(title: str, rows: List[Dict[str, Any]]) -> str:
        if not rows:
            return f"{title}: no rows found."
        preview = "; ".join(str(row) for row in rows[:5])
        return f"{title}: {preview}"

    @staticmethod
    def _format_review_analysis(result: Dict[str, Any]) -> str:
        summary = result.get("summary", [])
        comments = result.get("comments", [])
        if not summary and not comments:
            return "No reviews found."
        return "Lowest-rated review summary: " + "; ".join(str(row) for row in summary[:5])
