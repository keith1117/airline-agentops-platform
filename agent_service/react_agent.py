import json
import re
import time
from datetime import date
from typing import Any, Dict, List, Optional

from .config import Settings, settings as default_settings
from .db import get_conn
from .llm import LLMClient, LLMRouter, NativeToolCallingRouter
from .rag import PolicyRAG, RAGConfigurationError
from .tool_registry import Tool, ToolRegistry
from .tools.customer_tools import (
    answer_policy_question,
    cancel_customer_ticket,
    confirm_booking,
    create_booking_intent,
    get_user_preferences,
    get_customer_ticket,
    get_customer_trips,
    parse_airports,
    preview_customer_ticket_cancellation,
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
    def __init__(self, rag: PolicyRAG, settings: Settings = default_settings, router: Optional[Any] = None) -> None:
        self.rag = rag
        self.settings = settings
        llm_client = LLMClient(settings)
        if router is not None and getattr(router, "router_kind", "json") == "native":
            self.native_router = router
            self.router = LLMRouter(llm_client)
        else:
            self.native_router = NativeToolCallingRouter(llm_client)
            self.router = router or LLMRouter(llm_client)
        self.registry = ToolRegistry()
        self._register_tools()

    def _register_tools(self) -> None:
        self.registry.register(Tool("search_flights", "Search available future flights.", ["customer"], search_flights, risk="safe_read"))
        self.registry.register(Tool("get_customer_trips", "Return a customer's trips.", ["customer"], get_customer_trips, risk="safe_read"))
        self.registry.register(Tool("get_customer_ticket", "Return one customer ticket by ticket ID.", ["customer"], get_customer_ticket, risk="safe_read"))
        self.registry.register(Tool("preview_customer_ticket_cancellation", "Preview cancellation fee and refund before cancelling a ticket.", ["customer"], preview_customer_ticket_cancellation, risk="safe_read"))
        self.registry.register(Tool("cancel_customer_ticket", "Cancel one customer ticket and calculate refund terms.", ["customer"], cancel_customer_ticket, risk="human_confirmed"))
        self.registry.register(Tool("create_booking_intent", "Create pending booking intent.", ["customer"], create_booking_intent, risk="controlled_write"))
        self.registry.register(Tool("confirm_booking", "Confirm a pending mock booking.", ["customer"], confirm_booking, risk="human_confirmed"))
        self.registry.register(Tool("remember_user_preference", "Save customer travel preferences.", ["customer"], remember_user_preference, risk="controlled_write"))
        self.registry.register(Tool("get_user_preferences", "Get customer travel preferences.", ["customer"], get_user_preferences, risk="safe_read"))
        self.registry.register(
            Tool(
                "answer_policy_question",
                "Answer policy questions from the knowledge base.",
                ["customer", "staff"],
                lambda question: answer_policy_question(self.rag, question),
                risk="safe_read",
            )
        )
        self.registry.register(Tool("get_sales_report", "Return monthly ticket sales.", ["staff"], get_sales_report, risk="safe_read"))
        self.registry.register(Tool("analyze_reviews", "Analyze ratings and comments.", ["staff"], analyze_reviews, risk="safe_read"))
        self.registry.register(Tool("get_flight_load_factor", "Return load factor by flight.", ["staff"], get_flight_load_factor, risk="safe_read"))
        self.registry.register(Tool("get_route_performance", "Return route performance.", ["staff"], get_route_performance, risk="safe_read"))

    def customer_chat(self, session_id: str, customer_email: str, message: str) -> Dict[str, Any]:
        started = time.time()
        tool_calls: List[Dict[str, Any]] = []
        citations: List[Dict[str, Any]] = []
        pending = None
        pending_cancellation = None
        pending_booking_search = None
        answer = ""
        error = None
        reasoning = "Classify customer request and call the safest allowed tool."
        execution = self._execution()
        execution["runtime_mode_used"] = self.settings.agent_runtime_mode
        try:
            lower = message.lower()
            if self._should_use_bounded_customer_runtime(lower, message):
                routed = self._bounded_customer_react(session_id, customer_email, message, tool_calls, execution)
                answer = routed["answer"]
                pending = routed.get("pending_confirmation")
                pending_cancellation = routed.get("pending_cancellation")
                pending_booking_search = routed.get("pending_booking_search")
            elif self._is_identity_question(lower):
                answer = f"You are currently logged in as customer {customer_email}."
                execution["request_path"] = "identity"
            elif self._is_cancel_ticket_request(lower) and self._extract_ticket_id(message) is None:
                answer = "I can cancel a specific ticket. Please provide your ticket number."
                execution.update({"request_path": "clarification", "router_used": "deterministic"})
            elif (ticket_id := self._extract_ticket_id(message)) is not None:
                routed = self._handle_ticket_followup(session_id, customer_email, ticket_id, message, tool_calls, execution)
                answer = routed["answer"]
                pending_cancellation = routed.get("pending_cancellation")
            elif self._is_policy_question(lower) and not self._is_payment_or_booking_transaction(lower):
                result = self._call_policy_tool("customer", message, tool_calls, execution, router_used="bypassed")
                answer = result["answer"]
                citations = result.get("citations", [])
            elif (routed := self._try_customer_llm_route(message, customer_email, tool_calls, execution)) is not None:
                answer = routed["answer"]
                citations = routed.get("citations", [])
                pending = routed.get("pending_confirmation")
                pending_cancellation = routed.get("pending_cancellation")
                pending_booking_search = routed.get("pending_booking_search")
            elif any(word in lower for word in ["trip", "order", "ticket", "my flight", "我的", "订单"]):
                execution.update({"request_path": "tool_routing", "router_used": "deterministic", "answer_mode_used": "backend_formatter"})
                result = self.registry.call("customer", "get_customer_trips", customer_email=customer_email)
                tool_calls.append({"name": "get_customer_trips", "args": {"customer_email": customer_email}, "result": result})
                answer = self._format_trips(result)
            elif any(word in lower for word in ["prefer", "remember", "usually", "preference", "偏好", "记住"]):
                execution.update({"request_path": "tool_routing", "router_used": "deterministic", "answer_mode_used": "backend_formatter"})
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
                execution.update({"request_path": "tool_routing", "router_used": "deterministic", "answer_mode_used": "backend_formatter"})
                routed = self._handle_booking_request({}, message, customer_email, tool_calls, execution, session_id=session_id)
                answer = routed["answer"]
                pending = routed.get("pending_confirmation")
                pending_booking_search = routed.get("pending_booking_search")
            elif self._is_customer_search_question(lower, message):
                execution.update({"request_path": "tool_routing", "router_used": "deterministic", "answer_mode_used": "backend_formatter"})
                dep, arr = parse_airports(message)
                period = self._extract_period(lower)
                max_price = self._extract_budget(message)
                airline = self._extract_airline(message)
                month = self._extract_month(message)
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
                    flight_number=None,
                    month=month,
                    period=period,
                    max_price=max_price,
                )
                tool_calls.append(
                    {
                        "name": "search_flights",
                        "args": {"departure_airport": dep, "arrival_airport": arr, "airline_name": airline, "month": month, "period": period, "max_price": max_price},
                        "result": result,
                    }
                )
                answer = self._format_flights(result)
            else:
                answer = self._customer_scope_fallback()
                execution["request_path"] = "scope_fallback"
        except Exception as exc:
            error = str(exc)
            answer = f"The agent hit a controlled error: {error}"
            execution["fallback_reason"] = execution.get("fallback_reason") or error
        self._ensure_trajectory(tool_calls, execution)
        self._append_final_answer(execution, answer)
        self._trace(session_id, "customer", customer_email, message, reasoning, tool_calls, answer, started, error, execution)
        return {
            "answer": answer,
            "citations": citations,
            "tool_calls": tool_calls,
            "pending_confirmation": pending,
            "pending_booking_search": pending_booking_search,
            "pending_cancellation": pending_cancellation,
            "execution": execution,
        }

    def staff_chat(self, session_id: str, staff_username: str, airline_name: str, message: str) -> Dict[str, Any]:
        started = time.time()
        tool_calls: List[Dict[str, Any]] = []
        answer = ""
        table = None
        error = None
        reasoning = "Classify staff analytics request and call staff-only reporting tools."
        execution = self._execution()
        execution["runtime_mode_used"] = self.settings.agent_runtime_mode
        try:
            lower = message.lower()
            if self._is_identity_question(lower):
                answer = f"You are currently logged in as staff user {staff_username} for {airline_name}."
                execution["request_path"] = "identity"
            elif self._is_policy_question(lower) and not self._is_payment_or_booking_transaction(lower):
                result = self._call_policy_tool("staff", message, tool_calls, execution, router_used="bypassed")
                answer = result["answer"]
            elif self._should_use_bounded_staff_runtime(lower):
                routed = self._bounded_staff_react(staff_username, airline_name, message, tool_calls, execution)
                answer = routed["answer"]
                table = routed.get("tables")
            elif (routed := self._try_staff_llm_route(message, airline_name, tool_calls, execution)) is not None:
                answer = routed["answer"]
                table = routed.get("tables")
            elif any(word in lower for word in ["review", "rating", "comment", "差评", "评分"]):
                execution.update({"request_path": "tool_routing", "router_used": "deterministic", "answer_mode_used": "backend_formatter"})
                result = self.registry.call("staff", "analyze_reviews", airline_name=airline_name)
                tool_calls.append({"name": "analyze_reviews", "args": {"airline_name": airline_name}, "result": result})
                table = result.get("summary")
                answer = self._format_review_analysis(result)
            elif any(word in lower for word in ["load", "capacity", "full", "seat", "载客", "满座"]):
                execution.update({"request_path": "tool_routing", "router_used": "deterministic", "answer_mode_used": "backend_formatter"})
                result = self.registry.call("staff", "get_flight_load_factor", airline_name=airline_name)
                tool_calls.append({"name": "get_flight_load_factor", "args": {"airline_name": airline_name}, "result": result})
                table = result.get("rows")
                answer = self._format_table("Highest load factor flights", result.get("rows", []))
            elif any(word in lower for word in ["route", "popular", "performance", "热门", "航线"]):
                execution.update({"request_path": "tool_routing", "router_used": "deterministic", "answer_mode_used": "backend_formatter"})
                result = self.registry.call("staff", "get_route_performance", airline_name=airline_name)
                tool_calls.append({"name": "get_route_performance", "args": {"airline_name": airline_name}, "result": result})
                table = result.get("rows")
                answer = self._format_table("Route performance", result.get("rows", []))
            elif any(word in lower for word in ["sales", "revenue", "report", "monthly", "last year", "ticket sales", "销售", "收入", "报表"]):
                execution.update({"request_path": "tool_routing", "router_used": "deterministic", "answer_mode_used": "backend_formatter"})
                result = self.registry.call("staff", "get_sales_report", airline_name=airline_name)
                tool_calls.append({"name": "get_sales_report", "args": {"airline_name": airline_name}, "result": result})
                table = result.get("rows")
                answer = self._format_table("Sales report", result.get("rows", []))
            else:
                answer = self._staff_scope_fallback()
                execution["request_path"] = "scope_fallback"
        except Exception as exc:
            error = str(exc)
            answer = f"The staff copilot hit a controlled error: {error}"
            execution["fallback_reason"] = execution.get("fallback_reason") or error
        self._ensure_trajectory(tool_calls, execution)
        self._append_final_answer(execution, answer)
        self._trace(session_id, "staff", staff_username, message, reasoning, tool_calls, answer, started, error, execution)
        return {"answer": answer, "tool_calls": tool_calls, "tables": table, "execution": execution}

    def confirm_booking(self, booking_intent_id: int, customer_email: str, idempotency_key: str) -> Dict[str, Any]:
        return self.registry.call(
            "customer",
            "confirm_booking",
            booking_intent_id=booking_intent_id,
            customer_email=customer_email,
            idempotency_key=idempotency_key,
        )

    def confirm_cancellation(self, customer_email: str, ticket_id: int) -> Dict[str, Any]:
        return self.registry.call(
            "customer",
            "cancel_customer_ticket",
            customer_email=customer_email,
            ticket_id=ticket_id,
        )

    def _should_use_bounded_customer_runtime(self, lower: str, message: str) -> bool:
        mode = self.settings.agent_runtime_mode
        if mode not in {"bounded_react", "auto"}:
            return False
        if self._is_cancel_ticket_request(lower):
            return True
        if mode == "bounded_react":
            return self._is_booking_preparation_goal(lower)
        return self._is_booking_preparation_goal(lower) and ("cheapest" in lower or "prepare" in lower)

    def _should_use_bounded_staff_runtime(self, lower: str) -> bool:
        mode = self.settings.agent_runtime_mode
        if mode not in {"bounded_react", "auto"}:
            return False
        route_terms = ["route", "routes", "popular", "performance", "sales", "revenue", "strong", "航线", "销售", "收入"]
        review_terms = ["review", "reviews", "rating", "ratings", "poor", "worst", "low-rated", "low rated", "差评", "评分"]
        return any(term in lower for term in route_terms) and any(term in lower for term in review_terms)

    @staticmethod
    def _is_booking_preparation_goal(lower: str) -> bool:
        booking_words = ["book", "buy", "purchase", "reserve", "booking", "prepare", "订", "买"]
        flight_words = ["flight", "flights", "航班"]
        return (
            any(word in lower for word in booking_words) and any(word in lower for word in flight_words)
        ) or bool(re.search(r"\bbook\s+(?:this|that|it|one)\b", lower))

    def _bounded_staff_react(
        self,
        staff_username: str,
        airline_name: str,
        message: str,
        tool_calls: List[Dict[str, Any]],
        execution: Dict[str, Any],
    ) -> Dict[str, Any]:
        execution.update(
            {
                "request_path": "bounded_react",
                "runtime_mode_used": "bounded_react",
                "router_used": "bounded_controller",
                "answer_mode_used": "backend_formatter",
                "step_count": 0,
                "stop_reason": None,
                "confirmation_required": False,
            }
        )
        if self.settings.max_agent_steps < 2:
            execution.update({"stop_reason": "max_steps_reached", "step_count": self.settings.max_agent_steps})
            self._trajectory_decision(execution, "The bounded staff runtime stopped because this analysis needs two tools.")
            return {"answer": "I need at least two bounded steps to compare route performance with review quality."}

        route_result = self._bounded_call(
            "staff",
            "get_route_performance",
            tool_calls,
            execution,
            decision_summary="Need route performance before comparing demand with customer review quality.",
            airline_name=airline_name,
        )
        review_result = self._bounded_call(
            "staff",
            "analyze_reviews",
            tool_calls,
            execution,
            decision_summary="Need review analysis to identify weak customer experience signals.",
            airline_name=airline_name,
        )
        execution.update(
            {
                "stop_reason": "final_answer",
                "step_count": len([s for s in execution["trajectory"] if s.get("type") == "action"]),
            }
        )
        answer, table = self._format_staff_route_review_analysis(route_result, review_result)
        return {"answer": answer, "tables": table}

    def _bounded_customer_react(
        self,
        session_id: str,
        customer_email: str,
        message: str,
        tool_calls: List[Dict[str, Any]],
        execution: Dict[str, Any],
    ) -> Dict[str, Any]:
        lower = message.lower()
        execution.update(
            {
                "request_path": "bounded_react",
                "runtime_mode_used": "bounded_react",
                "router_used": "bounded_controller",
                "answer_mode_used": "backend_formatter",
                "step_count": 0,
                "stop_reason": None,
                "confirmation_required": False,
            }
        )

        if self._is_cancel_ticket_request(lower):
            ticket_id = self._extract_ticket_id(message)
            if not ticket_id:
                execution.update({"stop_reason": "clarification"})
                self._trajectory_decision(execution, "Need a ticket number before preparing a cancellation preview.")
                return {"answer": "I can cancel a specific ticket. Please provide your ticket number."}
            return self._preview_cancellation(customer_email, ticket_id, tool_calls, execution)

        dep, arr = parse_airports(message)
        airline = self._extract_airline(message) or "United"
        period = self._extract_period(lower)
        month = self._extract_month(message)
        max_price = self._extract_budget(message)

        if self.settings.max_agent_steps < 2:
            execution.update({"stop_reason": "max_steps_reached", "step_count": self.settings.max_agent_steps})
            self._trajectory_decision(execution, "The bounded runtime stopped before executing tools because max steps is too low.")
            return {"answer": "I need at least two bounded steps to search flights and prepare a pending booking."}

        if self._has_specific_booking_target(message):
            self._trajectory_decision(execution, "The user provided a specific booking target or referred to the prior flight result.")
            routed = self._handle_booking_request({}, message, customer_email, tool_calls, execution, session_id=session_id)
            if routed.get("pending_booking_search"):
                execution.update(
                    {
                        "stop_reason": "booking_search_ready",
                        "confirmation_required": False,
                        "step_count": len([s for s in execution["trajectory"] if s.get("type") == "action"]),
                    }
                )
            elif routed.get("pending_confirmation"):
                execution.update(
                    {
                        "stop_reason": "confirmation_required",
                        "confirmation_required": True,
                        "step_count": len([s for s in execution["trajectory"] if s.get("type") == "action"]),
                    }
                )
            else:
                execution["stop_reason"] = execution.get("stop_reason") or "clarification"
            return routed

        self._bounded_call(
            "customer",
            "search_flights",
            tool_calls,
            execution,
            decision_summary="Need available bookable flights before preparing a booking intent.",
            departure_airport=dep,
            arrival_airport=arr,
            airline_name=airline,
            month=month,
            period=period,
            max_price=max_price,
        )
        search_result = tool_calls[-1]["result"]
        flights = search_result.get("flights") or []
        if not flights:
            execution.update({"stop_reason": "no_flights", "step_count": len([s for s in execution["trajectory"] if s.get("type") == "action"])})
            self._append_final_answer(execution, "I could not find a bookable matching flight in the current inventory.")
            return {"answer": "I could not find a bookable matching flight in the current inventory."}

        selected = self._select_cheapest_flight(flights)
        if not selected:
            execution.update({"stop_reason": "no_flights", "step_count": len([s for s in execution["trajectory"] if s.get("type") == "action"])})
            answer = "I found flight records, but none are bookable for a pending booking intent."
            self._append_final_answer(execution, answer)
            return {"answer": answer}

        execution.update(
            {
                "stop_reason": "booking_search_ready",
                "confirmation_required": False,
                "step_count": len([s for s in execution["trajectory"] if s.get("type") == "action"]),
            }
        )
        pending_booking_search = self._booking_search_payload(selected)
        answer = (
            f"I found the cheapest matching bookable flight: {selected['airline_name']} {selected['flight_number']} "
            f"from {selected['departure_airport']} to {selected['arrival_airport']} departing at "
            f"{selected['departure_date_time']} for ${selected['base_price']}. "
            "Use Book to continue on the Search Flights page and complete the purchase manually."
        )
        return {"answer": answer, "pending_booking_search": pending_booking_search}

    def _bounded_call(
        self,
        role: str,
        tool_name: str,
        tool_calls: List[Dict[str, Any]],
        execution: Dict[str, Any],
        decision_summary: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        risk = self.registry.risk_for(tool_name)
        if risk == "human_confirmed":
            execution.update({"stop_reason": "human_confirmed_tool_blocked", "confirmation_required": True})
            raise RuntimeError(f"Bounded runtime cannot execute human-confirmed tool: {tool_name}")
        if len([s for s in execution.get("trajectory", []) if s.get("type") == "action"]) >= self.settings.max_agent_steps:
            execution.update({"stop_reason": "max_steps_reached"})
            raise RuntimeError("Bounded runtime reached MAX_AGENT_STEPS.")
        self._trajectory_decision(execution, decision_summary)
        self._trajectory_action(execution, tool_name, kwargs)
        result = self.registry.call(role, tool_name, **kwargs)
        tool_calls.append({"name": tool_name, "args": kwargs, "result": result})
        self._trajectory_observation(execution, tool_name, result)
        return result

    @staticmethod
    def _select_cheapest_flight(flights: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        candidates = [
            flight
            for flight in flights
            if str(flight.get("status", "")).upper() != "CANCELLED" and int(flight.get("seats_left") or 0) > 0
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda flight: (float(flight.get("base_price") or 0), str(flight.get("departure_date_time") or "")))

    def _try_customer_llm_route(
        self,
        message: str,
        customer_email: str,
        tool_calls: List[Dict[str, Any]],
        execution: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        plan = self._route_or_fallback("customer", message, execution)
        if plan is None:
            return None
        try:
            return self._execute_customer_plan(plan, message, customer_email, tool_calls, execution)
        except RuntimeError as exc:
            if self._is_forced_tool_router_mode():
                raise
            execution["fallback_reason"] = f"{exc}; used deterministic router"
            return None

    def _try_staff_llm_route(
        self,
        message: str,
        airline_name: str,
        tool_calls: List[Dict[str, Any]],
        execution: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        plan = self._route_or_fallback("staff", message, execution)
        if plan is None:
            return None
        try:
            return self._execute_staff_plan(plan, message, airline_name, tool_calls, execution)
        except RuntimeError as exc:
            if self._is_forced_tool_router_mode():
                raise
            execution["fallback_reason"] = f"{exc}; used deterministic router"
            return None

    def _route_or_fallback(self, role: str, message: str, execution: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        mode = self._effective_tool_router_mode()
        if mode == "deterministic":
            return None
        if mode == "native":
            return self._route_with_router(self.native_router, "native", role, message, execution, forced=True)
        if mode == "json":
            return self._route_with_router(self.router, "llm", role, message, execution, forced=True)

        fallback_reasons = []
        native_plan = self._route_with_router(self.native_router, "native", role, message, execution, forced=False)
        if native_plan is not None:
            return native_plan
        if execution.get("fallback_reason"):
            fallback_reasons.append(execution["fallback_reason"])
            execution["fallback_reason"] = None
        json_plan = self._route_with_router(self.router, "llm", role, message, execution, forced=False)
        if json_plan is not None:
            if fallback_reasons:
                execution["fallback_reason"] = "; ".join(fallback_reasons)
            return json_plan
        if execution.get("fallback_reason"):
            fallback_reasons.append(execution["fallback_reason"])
        execution["fallback_reason"] = "; ".join(fallback_reasons) if fallback_reasons else "Tool router unavailable; used deterministic router"
        return None

    def _route_with_router(
        self,
        router: Any,
        router_used: str,
        role: str,
        message: str,
        execution: Dict[str, Any],
        forced: bool,
    ) -> Optional[Dict[str, Any]]:
        if not getattr(router, "enabled", lambda: True)():
            if forced:
                raise RuntimeError(f"{router_used} router is forced but LLM_API_KEY is not configured.")
            execution["fallback_reason"] = f"{router_used} router unavailable"
            return None
        try:
            plan = router.route(role, message, context={})
        except Exception as exc:
            if forced:
                raise RuntimeError(f"{router_used} router failed: {exc}") from exc
            execution["fallback_reason"] = f"{router_used} router failed: {exc}"
            return None
        if not forced and not plan.get("tool") and not plan.get("needs_clarification"):
            execution["fallback_reason"] = f"{router_used} router returned no tool"
            return None
        execution["router_used"] = router_used
        self._trajectory_reasoning(execution, f"{router_used} router selected {plan.get('tool') or 'no tool'} for intent {plan.get('intent')}.")
        return plan

    def _effective_tool_router_mode(self) -> str:
        if self.settings.tool_router_mode != "auto":
            return self.settings.tool_router_mode
        if self.settings.agent_router_mode == "llm":
            return "json"
        if self.settings.agent_router_mode == "deterministic":
            return "deterministic"
        return "auto"

    def _is_forced_tool_router_mode(self) -> bool:
        return self._effective_tool_router_mode() in {"native", "json"}

    def _execute_customer_plan(
        self,
        plan: Dict[str, Any],
        message: str,
        customer_email: str,
        tool_calls: List[Dict[str, Any]],
        execution: Dict[str, Any],
    ) -> Dict[str, Any]:
        if plan.get("needs_clarification"):
            if plan.get("tool") == "create_booking_intent" or self._is_payment_or_booking_transaction(message.lower()):
                return self._handle_booking_request(plan.get("args") or {}, message, customer_email, tool_calls, execution)
            execution["request_path"] = "clarification"
            return {"answer": plan.get("clarification_question") or "Can you provide more details?"}
        tool = plan.get("tool")
        args = plan.get("args") or {}
        if tool == "answer_policy_question":
            result = self._call_policy_tool("customer", args.get("question") or message, tool_calls, execution, router_used="llm")
            return {"answer": result["answer"], "citations": result.get("citations", [])}
        if tool == "search_flights":
            dep, arr = parse_airports(message)
            tool_args = {
                "departure_airport": args.get("departure_airport") or dep,
                "arrival_airport": args.get("arrival_airport") or arr,
                "airline_name": args.get("airline_name"),
                "flight_number": _normalize_flight_number(args.get("flight_number")),
                "travel_date": _normalize_travel_date(args.get("travel_date")),
                "month": _normalize_month(args.get("month")) or self._extract_month(message),
                "period": _normalize_period(args.get("period")) or self._extract_period(message.lower()),
                "max_price": args.get("max_price"),
            }
            self._trajectory_action(execution, "search_flights", tool_args)
            result = self.registry.call(
                "customer",
                "search_flights",
                **tool_args,
            )
            execution.update({"request_path": "tool_routing", "answer_mode_used": "backend_formatter"})
            tool_calls.append({"name": "search_flights", "args": tool_args, "result": result})
            self._trajectory_observation(execution, "search_flights", result)
            return {"answer": self._format_flights(result)}
        if tool == "get_customer_trips":
            self._trajectory_action(execution, "get_customer_trips", {"customer_email": customer_email})
            result = self.registry.call("customer", "get_customer_trips", customer_email=customer_email)
            execution.update({"request_path": "tool_routing", "answer_mode_used": "backend_formatter"})
            tool_calls.append({"name": "get_customer_trips", "args": {"customer_email": customer_email}, "result": result})
            self._trajectory_observation(execution, "get_customer_trips", result)
            return {"answer": self._format_trips(result)}
        if tool == "cancel_customer_ticket":
            ticket_id = args.get("ticket_id") or self._extract_ticket_id(message)
            if not ticket_id:
                execution["request_path"] = "clarification"
                return {"answer": "I can cancel a specific ticket. Please provide your ticket number."}
            return self._preview_cancellation(customer_email, int(ticket_id), tool_calls, execution)
        if tool == "remember_user_preference":
            if not self._explicit_memory_request(message.lower()):
                raise RuntimeError("LLM router attempted to save preferences without an explicit remember/save request.")
            result = self.registry.call(
                "customer",
                "remember_user_preference",
                customer_email=customer_email,
                departure_city=args.get("departure_city"),
                destination_city=args.get("destination_city"),
                max_budget=args.get("max_budget"),
                preferred_airline=args.get("preferred_airline"),
            )
            execution.update({"request_path": "tool_routing", "answer_mode_used": "backend_formatter"})
            tool_calls.append({"name": "remember_user_preference", "args": args, "result": result})
            return {"answer": "I saved your travel preferences for future searches."}
        if tool == "create_booking_intent":
            return self._handle_booking_request(args, message, customer_email, tool_calls, execution)
        if tool:
            raise RuntimeError(f"LLM router returned unsupported customer tool: {tool}")
        return {"answer": self._customer_scope_fallback()}

    def _handle_ticket_followup(
        self,
        session_id: str,
        customer_email: str,
        ticket_id: int,
        message: str,
        tool_calls: List[Dict[str, Any]],
        execution: Dict[str, Any],
    ) -> Dict[str, Any]:
        execution.update({"request_path": "tool_routing", "router_used": "deterministic", "answer_mode_used": "backend_formatter"})
        context = f"{message}\n{self._recent_session_text(session_id)}".lower()
        if self._is_cancel_ticket_request(context):
            return self._preview_cancellation(customer_email, ticket_id, tool_calls, execution)

        result = self.registry.call("customer", "get_customer_ticket", customer_email=customer_email, ticket_id=ticket_id)
        tool_calls.append({"name": "get_customer_ticket", "args": {"ticket_id": ticket_id}, "result": result})
        ticket = result.get("ticket")
        if not ticket:
            return {"answer": f"I could not find ticket {ticket_id} for your account."}

        if "refund" in context or "cancel" in context:
            return {"answer": self._format_ticket_refund_status(ticket)}
        if "baggage" in context or "bag" in context:
            return {"answer": self._format_ticket_baggage_status(ticket)}
        if "delay" in context or "status" in context:
            return {"answer": self._format_ticket_status(ticket)}
        return {"answer": self._format_ticket_status(ticket)}

    def _cancel_ticket(
        self,
        customer_email: str,
        ticket_id: int,
        tool_calls: List[Dict[str, Any]],
        execution: Dict[str, Any],
    ) -> Dict[str, Any]:
        execution.update({"request_path": "tool_routing", "answer_mode_used": "backend_formatter"})
        result = self.registry.call("customer", "cancel_customer_ticket", customer_email=customer_email, ticket_id=ticket_id)
        tool_calls.append({"name": "cancel_customer_ticket", "args": {"ticket_id": ticket_id}, "result": result})
        if "error" in result:
            return {"answer": result["error"]}
        return {"answer": self._format_cancellation_result(result)}

    def _preview_cancellation(
        self,
        customer_email: str,
        ticket_id: int,
        tool_calls: List[Dict[str, Any]],
        execution: Dict[str, Any],
    ) -> Dict[str, Any]:
        execution.update(
            {
                "request_path": "cancellation_preview",
                "answer_mode_used": "backend_formatter",
                "stop_reason": "cancellation_confirmation_required",
                "confirmation_required": True,
            }
        )
        self._trajectory_decision(
            execution,
            "Preview cancellation fee and estimated refund before requiring explicit cancellation confirmation.",
        )
        self._trajectory_action(execution, "preview_customer_ticket_cancellation", {"ticket_id": ticket_id})
        result = self.registry.call(
            "customer",
            "preview_customer_ticket_cancellation",
            customer_email=customer_email,
            ticket_id=ticket_id,
        )
        tool_calls.append({"name": "preview_customer_ticket_cancellation", "args": {"ticket_id": ticket_id}, "result": result})
        self._trajectory_observation(execution, "preview_customer_ticket_cancellation", result)
        if "error" in result:
            execution.update({"stop_reason": "tool_error", "confirmation_required": False})
            return {"answer": result["error"]}
        if result.get("already_cancelled"):
            execution.update({"stop_reason": "already_cancelled", "confirmation_required": False})
            return {"answer": self._format_cancellation_result(result), "pending_cancellation": None}
        return {"answer": self._format_cancellation_preview(result), "pending_cancellation": result}

    def _handle_booking_request(
        self,
        args: Dict[str, Any],
        message: str,
        customer_email: str,
        tool_calls: List[Dict[str, Any]],
        execution: Dict[str, Any],
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        execution.update({"request_path": "tool_routing", "answer_mode_used": "backend_formatter"})
        if self._is_book_this_one_request(message.lower()) and session_id:
            recent_flights = self._recent_search_flights(session_id)
            if len(recent_flights) == 1:
                return self._prepare_booking_search(recent_flights[0])
            if len(recent_flights) > 1:
                return {
                    "answer": (
                        "I found multiple recent flight options. Please choose one by providing the flight number "
                        "and departure time."
                    )
                }

        dep_from_text, arr_from_text = parse_airports(message)
        flight_number = _normalize_flight_number(args.get("flight_number")) or self._extract_flight_number(message)
        departure_time = _normalize_datetime(args.get("departure_date_time")) or self._extract_datetime(message)
        travel_date = (
            _normalize_travel_date(args.get("travel_date"))
            or self._extract_travel_date(message)
            or (departure_time[:10] if departure_time else None)
        )
        month = _normalize_month(args.get("month")) or self._extract_month(message)
        period = _normalize_period(args.get("period")) or self._extract_period(message.lower())
        airline = args.get("airline_name") or self._extract_airline(message) or "United"
        dep = args.get("departure_airport") or dep_from_text
        arr = args.get("arrival_airport") or arr_from_text

        search_result = None
        if flight_number or dep or arr or travel_date:
            search_result = self.registry.call(
                "customer",
                "search_flights",
                departure_airport=dep,
                arrival_airport=arr,
                airline_name=airline,
                flight_number=flight_number,
                travel_date=travel_date,
                month=month,
                period=period,
            )
            tool_calls.append(
                {
                    "name": "search_flights",
                    "args": {
                        "departure_airport": dep,
                        "arrival_airport": arr,
                        "airline_name": airline,
                        "flight_number": flight_number,
                        "travel_date": travel_date,
                        "month": month,
                        "period": period,
                    },
                    "result": search_result,
                }
            )

        flights = (search_result or {}).get("flights", [])
        matches = [
            row
            for row in flights
            if (not flight_number or str(row.get("flight_number", "")).upper() == flight_number)
            and (not departure_time or _normalize_datetime(row.get("departure_date_time")) == departure_time)
        ]

        if flight_number and departure_time:
            if not matches:
                answer = (
                    f"I could not find a bookable {airline} flight {flight_number} departing at {departure_time} "
                    "in the current inventory."
                )
                if flights:
                    answer += "\n\n" + self._format_flights(search_result or {})
                return {"answer": answer}
            return self._prepare_booking_search(matches[0])

        if len(matches) == 1:
            return self._prepare_booking_search(matches[0])

        if flight_number and not matches:
            date_suffix = f" on {travel_date}" if travel_date else ""
            return {"answer": f"I could not find a bookable {airline} flight {flight_number}{date_suffix} in the current inventory."}

        if flights:
            return {
                "answer": (
                    self._format_flights(search_result or {})
                    + "\n\nPlease choose one flight by providing the flight number and departure time."
                )
            }

        return {
            "answer": (
                "Which flight should I help you find? Please provide a route, date, or flight number so I can "
                "show matching flights before you purchase on the Search Flights page."
            )
        }

    def _prepare_booking_search(self, flight: Dict[str, Any]) -> Dict[str, Any]:
        answer = (
            f"I found {flight['airline_name']} flight {flight['flight_number']} from "
            f"{flight['departure_airport']} to {flight['arrival_airport']} departing at "
            f"{flight['departure_date_time']} for ${flight['base_price']}. "
            "Use Book to continue on the Search Flights page and complete the purchase manually."
        )
        return {"answer": answer, "pending_booking_search": self._booking_search_payload(flight)}

    @staticmethod
    def _booking_search_payload(flight: Dict[str, Any]) -> Dict[str, Any]:
        departure_date_time = _normalize_datetime(flight.get("departure_date_time")) or str(flight.get("departure_date_time"))
        return {
            "airline_name": flight.get("airline_name"),
            "flight_number": flight.get("flight_number"),
            "departure_airport": flight.get("departure_airport"),
            "arrival_airport": flight.get("arrival_airport"),
            "departure_date_time": departure_date_time,
            "departure_date": departure_date_time[:10] if departure_date_time else "",
        }

    def _create_pending_booking(
        self,
        customer_email: str,
        flight: Dict[str, Any],
        tool_calls: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        result = self.registry.call(
            "customer",
            "create_booking_intent",
            customer_email=customer_email,
            airline_name=flight["airline_name"],
            flight_number=flight["flight_number"],
            departure_date_time=_normalize_datetime(flight["departure_date_time"]) or str(flight["departure_date_time"]),
        )
        tool_calls.append(
            {
                "name": "create_booking_intent",
                "args": {
                    "airline_name": flight["airline_name"],
                    "flight_number": flight["flight_number"],
                    "departure_date_time": _normalize_datetime(flight["departure_date_time"]) or str(flight["departure_date_time"]),
                },
                "result": result,
            }
        )
        if "error" in result:
            return {"answer": result["error"]}
        answer = (
            f"I found {flight['airline_name']} flight {flight['flight_number']} from "
            f"{flight['departure_airport']} to {flight['arrival_airport']} departing at "
            f"{flight['departure_date_time']} for ${flight['base_price']}. "
            "I created a pending booking intent. Please confirm before the ticket is issued."
        )
        return {"answer": answer, "pending_confirmation": result}

    def _execute_staff_plan(
        self,
        plan: Dict[str, Any],
        message: str,
        airline_name: str,
        tool_calls: List[Dict[str, Any]],
        execution: Dict[str, Any],
    ) -> Dict[str, Any]:
        if plan.get("needs_clarification"):
            execution["request_path"] = "clarification"
            return {"answer": plan.get("clarification_question") or "Can you provide more details?"}
        tool = plan.get("tool")
        args = plan.get("args") or {}
        if tool == "answer_policy_question":
            result = self._call_policy_tool("staff", args.get("question") or message, tool_calls, execution, router_used="llm")
            return {"answer": result["answer"]}
        staff_tools = {
            "get_sales_report": lambda: self.registry.call("staff", "get_sales_report", airline_name=airline_name),
            "analyze_reviews": lambda: self.registry.call("staff", "analyze_reviews", airline_name=airline_name),
            "get_flight_load_factor": lambda: self.registry.call("staff", "get_flight_load_factor", airline_name=airline_name),
            "get_route_performance": lambda: self.registry.call("staff", "get_route_performance", airline_name=airline_name),
        }
        if tool in staff_tools:
            result = staff_tools[tool]()
            execution.update({"request_path": "tool_routing", "answer_mode_used": "backend_formatter"})
            tool_calls.append({"name": tool, "args": {"airline_name": airline_name, **args}, "result": result})
            table = result.get("rows") or result.get("summary")
            if tool == "analyze_reviews":
                answer = self._format_review_analysis(result)
            else:
                answer = self._format_table(tool.replace("_", " ").title(), table or [])
            return {"answer": answer, "tables": table}
        if tool:
            raise RuntimeError(f"LLM router returned unsupported staff tool: {tool}")
        return {"answer": self._staff_scope_fallback()}

    def _call_policy_tool(
        self,
        role: str,
        question: str,
        tool_calls: List[Dict[str, Any]],
        execution: Dict[str, Any],
        router_used: str,
    ) -> Dict[str, Any]:
        result = self.registry.call(role, "answer_policy_question", question=question)
        self._trajectory_action(execution, "answer_policy_question", {"question": question})
        tool_calls.append({"name": "answer_policy_question", "args": {"question": question}, "result": result})
        self._trajectory_observation(execution, "answer_policy_question", result)
        rag_execution = result.get("execution", {})
        execution.update(
            {
                "request_path": "policy_rag",
                "router_used": router_used,
                "retriever_used": rag_execution.get("retriever_used", execution.get("retriever_used", "none")),
                "answer_mode_used": rag_execution.get("answer_mode_used", execution.get("answer_mode_used", "none")),
                "fallback_reason": rag_execution.get("fallback_reason") or execution.get("fallback_reason"),
            }
        )
        return result

    @staticmethod
    def _execution() -> Dict[str, Any]:
        return {
            "request_path": "unknown",
            "router_used": "none",
            "retriever_used": "none",
            "answer_mode_used": "none",
            "fallback_reason": None,
            "runtime_mode_used": "single_step",
            "step_count": 0,
            "stop_reason": None,
            "confirmation_required": False,
            "trajectory": [],
        }

    @staticmethod
    def _trajectory_decision(execution: Dict[str, Any], content: str) -> None:
        execution.setdefault("trajectory", []).append({"type": "decision_summary", "content": content})

    @staticmethod
    def _trajectory_reasoning(execution: Dict[str, Any], content: str) -> None:
        execution.setdefault("trajectory", []).append({"type": "reasoning", "content": content})

    @staticmethod
    def _trajectory_action(execution: Dict[str, Any], tool: str, args: Dict[str, Any]) -> None:
        execution.setdefault("trajectory", []).append({"type": "action", "tool": tool, "args": args})

    @staticmethod
    def _trajectory_observation(execution: Dict[str, Any], tool: str, result: Dict[str, Any]) -> None:
        preview = result
        execution.setdefault("trajectory", []).append({"type": "observation", "tool": tool, "content": preview})

    @staticmethod
    def _append_final_answer(execution: Dict[str, Any], answer: str) -> None:
        trajectory = execution.setdefault("trajectory", [])
        if answer and not any(step.get("type") == "final_answer" for step in trajectory):
            trajectory.append({"type": "final_answer", "content": answer})

    @classmethod
    def _ensure_trajectory(cls, tool_calls: List[Dict[str, Any]], execution: Dict[str, Any]) -> None:
        trajectory = execution.setdefault("trajectory", [])
        if not trajectory:
            cls._trajectory_reasoning(
                execution,
                f"Handle request through {execution.get('request_path', 'unknown')} with {execution.get('router_used', 'none')} routing.",
            )
        if any(step.get("type") == "action" for step in trajectory):
            return
        for call in tool_calls:
            cls._trajectory_action(execution, call.get("name", "unknown_tool"), call.get("args") or {})
            cls._trajectory_observation(execution, call.get("name", "unknown_tool"), call.get("result") or {})

    def _trace(self, session_id, role, principal, message, reasoning, tool_calls, answer, started, error=None, execution=None) -> None:
        if not self.settings.agent_trace_enabled:
            return
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
                        reasoning + ("\nexecution: " + json.dumps(execution, default=str) if execution else ""),
                        json.dumps(tool_calls, default=str),
                        answer,
                        int((time.time() - started) * 1000),
                        error,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def _recent_session_text(self, session_id: str) -> str:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_message, final_answer
                    FROM agent_traces
                    WHERE session_id=%s
                    ORDER BY created_at DESC, id DESC
                    LIMIT 3
                    """,
                    (session_id,),
                )
                rows = cur.fetchall()
            return "\n".join(f"{row.get('user_message', '')}\n{row.get('final_answer', '')}" for row in rows)
        except Exception:
            return ""
        finally:
            conn.close()

    def _recent_search_flights(self, session_id: str) -> List[Dict[str, Any]]:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT tool_calls
                    FROM agent_traces
                    WHERE session_id=%s
                    ORDER BY created_at DESC, id DESC
                    LIMIT 5
                    """,
                    (session_id,),
                )
                rows = cur.fetchall()
            for row in rows:
                raw_calls = row.get("tool_calls") or "[]"
                try:
                    calls = json.loads(raw_calls)
                except Exception:
                    continue
                for call in calls:
                    if call.get("name") != "search_flights":
                        continue
                    result = call.get("result") or {}
                    flights = result.get("flights") or []
                    if flights:
                        return flights
            return []
        except Exception:
            return []
        finally:
            conn.close()

    @staticmethod
    def _is_policy_question(lower: str) -> bool:
        return any(word in lower for word in ["refund", "baggage", "bag", "delay", "cancel", "policy", "payment", "行李", "退款", "延误", "政策"])

    @staticmethod
    def _is_identity_question(lower: str) -> bool:
        return any(
            phrase in lower
            for phrase in [
                "what is my name",
                "what's my name",
                "who am i",
                "whoami",
                "my username",
                "my email",
                "logged in as",
                "我的名字",
                "我是谁",
            ]
        )

    @staticmethod
    def _is_customer_search_question(lower: str, message: str) -> bool:
        dep, arr = parse_airports(message)
        return bool(
            dep
            or arr
            or any(
                phrase in lower
                for phrase in [
                    "flight",
                    "flights",
                    "fly",
                    "search",
                    "find",
                    "next month",
                    "航班",
                    "机票",
                ]
            )
        )

    @staticmethod
    def _is_payment_or_booking_transaction(lower: str) -> bool:
        transaction_pattern = r"\b(book|buy|purchase|reserve|pay|checkout)\b|confirm booking|订|买|支付"
        informational_markers = ["policy", "rule", "method", "methods", "what", "how", "can i", "does", "refund", "fee"]
        return bool(re.search(transaction_pattern, lower)) and not any(marker in lower for marker in informational_markers)

    @staticmethod
    def _is_cancel_ticket_request(lower: str) -> bool:
        active_patterns = [
            r"\bplease\s+cancel\b",
            r"\bcancel\s+(?:my\s+)?(?:flight|ticket|booking|trip)\b",
            r"\b(?:flight|ticket|booking|trip)\s+cancellation\b",
            r"取消(?:我的)?(?:航班|机票|订单|行程)",
        ]
        return any(re.search(pattern, lower) for pattern in active_patterns)

    @staticmethod
    def _is_book_this_one_request(lower: str) -> bool:
        return bool(re.search(r"\bbook\s+(?:this|that|it|one)\b", lower))

    def _has_specific_booking_target(self, message: str) -> bool:
        lower = message.lower()
        return bool(self._extract_flight_number(message) or self._extract_travel_date(message) or self._is_book_this_one_request(lower))

    @staticmethod
    def _explicit_memory_request(lower: str) -> bool:
        return any(word in lower for word in ["remember", "save", "preference", "prefer", "记住", "保存", "偏好"])

    @staticmethod
    def _customer_scope_fallback() -> str:
        return (
            "I can only help with airline booking tasks, including flight search, your trips, airline policy questions, "
            "travel preferences, and booking handoffs. I can't answer that request from this airline system."
        )

    @staticmethod
    def _staff_scope_fallback() -> str:
        return (
            "I can only help with airline operations, including sales reports, review analysis, load-factor checks, "
            "route performance, and policy questions. I can't answer that request from this airline operations workspace."
        )

    @staticmethod
    def _extract_budget(message: str) -> Optional[float]:
        match = re.search(r"(?:under|below|less than|price\s*<|预算|低于)\s*\$?(\d+(?:\.\d+)?)", message.lower())
        return float(match.group(1)) if match else None

    @staticmethod
    def _extract_flight_number(message: str) -> Optional[str]:
        explicit = re.search(
            r"\bflight\s*(?:number\s*)?(?:of\s*)?((?=[A-Z0-9]*\d)[A-Z0-9]{2,10})\b",
            message,
            re.IGNORECASE,
        )
        if explicit:
            return explicit.group(1).upper()
        alphanumeric = re.search(
            r"\b((?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{2,10})\b",
            message,
            re.IGNORECASE,
        )
        return alphanumeric.group(1).upper() if alphanumeric else None

    @staticmethod
    def _extract_airline(message: str) -> Optional[str]:
        if "united" in message.lower():
            return "United"
        if "jetblue" in message.lower():
            return "JetBlue"
        return None

    @staticmethod
    def _extract_month(message: str) -> Optional[str]:
        month_names = {
            "jan": 1,
            "january": 1,
            "feb": 2,
            "february": 2,
            "mar": 3,
            "march": 3,
            "apr": 4,
            "april": 4,
            "may": 5,
            "jun": 6,
            "june": 6,
            "jul": 7,
            "july": 7,
            "aug": 8,
            "august": 8,
            "sep": 9,
            "sept": 9,
            "september": 9,
            "oct": 10,
            "october": 10,
            "nov": 11,
            "november": 11,
            "dec": 12,
            "december": 12,
        }
        lower = message.lower()
        month_match = None
        for name in sorted(month_names, key=len, reverse=True):
            if re.search(rf"\b{name}\b", lower):
                month_match = name
                break
        if not month_match:
            ym = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])\b", message)
            return ym.group(0) if ym else None

        month_num = month_names[month_match]
        year = None
        after = re.search(rf"\b{month_match}\b\D{{0,8}}(20\d{{2}})\b", lower)
        before = re.search(rf"\b(20\d{{2}})\D{{0,8}}\b{month_match}\b", lower)
        if after:
            year = int(after.group(1))
        elif before:
            year = int(before.group(1))
        else:
            today = date.today()
            year = today.year if month_num >= today.month else today.year + 1
        return f"{year}-{month_num:02d}"

    @staticmethod
    def _extract_period(lower: str) -> Optional[str]:
        if re.search(r"\bnext\s+month\b", lower):
            return "next_month"
        if re.search(r"\b(?:this|current)\s+year\b", lower):
            return "this_year"
        if re.search(r"\bnext\s+year\b", lower):
            return "next_year"
        return None

    @staticmethod
    def _extract_datetime(message: str) -> Optional[str]:
        match = re.search(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)", message)
        if not match:
            return None
        value = match.group(1).replace("T", " ")
        if len(value) == 16:
            value += ":00"
        return value

    @staticmethod
    def _extract_travel_date(message: str) -> Optional[str]:
        match = re.search(r"(\d{4}-\d{2}-\d{2})(?![ T]\d{2}:\d{2})", message)
        return match.group(1) if match else None

    @staticmethod
    def _extract_ticket_id(message: str) -> Optional[int]:
        match = re.search(r"(?:ticket|票|订单)\D{0,12}#?\s*(\d{1,10})\b", message, re.IGNORECASE)
        return int(match.group(1)) if match else None

    @staticmethod
    def _format_flights(result: Dict[str, Any]) -> str:
        rows = result.get("flights", [])
        if not rows:
            return "No matching future flights were found in the current inventory."
        lines = ["Here are matching available flights:"]
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
    def _format_ticket_status(ticket: Dict[str, Any]) -> str:
        return (
            f"Ticket {ticket['ticket_ID']}: {ticket['airline_name']} {ticket['flight_number']} "
            f"{ticket['departure_airport']} -> {ticket['arrival_airport']} departing at "
            f"{ticket['departure_date_time']} is currently {ticket['status']}."
        )

    def _format_ticket_refund_status(self, ticket: Dict[str, Any]) -> str:
        base = self._format_ticket_status(ticket)
        if ticket.get("status") == "CANCELLED":
            return (
                f"{base}\n\nBased on the refund policy, this ticket is eligible for refund review because "
                "the flight was cancelled by the airline."
            )
        return (
            f"{base}\n\nBased on the refund policy, this ticket is not currently eligible for an "
            "airline-cancelled-flight refund because the flight status is "
            f"{ticket['status']}. If you want a voluntary cancellation refund review, eligibility depends on "
            "the ticket rules attached to that fare."
        )

    def _format_ticket_baggage_status(self, ticket: Dict[str, Any]) -> str:
        base = self._format_ticket_status(ticket)
        return (
            f"{base}\n\nFor this booking, the standard baggage policy allows one carry-on bag and one personal item. "
            "Checked baggage eligibility and fees depend on the route, airline rules, and ticket class."
        )

    @staticmethod
    def _format_cancellation_result(result: Dict[str, Any]) -> str:
        status = result.get("flight_status")
        fee = float(result.get("cancellation_fee", 0))
        refund = float(result.get("refund_amount", 0))
        prefix = "This ticket was already cancelled." if result.get("already_cancelled") else "I cancelled this ticket."
        if status == "DELAYED":
            policy = "Because the flight is delayed, the cancellation fee is reduced."
        elif status == "CANCELLED":
            policy = "Because the airline cancelled the flight, no cancellation fee is charged."
        else:
            policy = "Because the flight is currently on time, the standard voluntary cancellation fee applies."
        route = ""
        if result.get("departure_airport") and result.get("arrival_airport"):
            route = f" {result['departure_airport']} -> {result['arrival_airport']}"
        return (
            f"{prefix}\n\n"
            f"Ticket {result['ticket_id']}: {result['airline_name']} {result['flight_number']}{route} departing at "
            f"{result['departure_date_time']} is currently {status}.\n\n"
            f"{policy} Cancellation fee: ${fee:.2f}. Estimated refund: ${refund:.2f}."
        )

    @staticmethod
    def _format_cancellation_preview(result: Dict[str, Any]) -> str:
        status = result.get("flight_status")
        fee = float(result.get("cancellation_fee", 0))
        refund = float(result.get("refund_amount", 0))
        if status == "DELAYED":
            policy = "Because the flight is delayed, the cancellation fee is reduced."
        elif status == "CANCELLED":
            policy = "Because the airline cancelled the flight, no cancellation fee is charged."
        else:
            policy = "Because the flight is currently on time, the standard voluntary cancellation fee applies."
        route = ""
        if result.get("departure_airport") and result.get("arrival_airport"):
            route = f" {result['departure_airport']} -> {result['arrival_airport']}"
        return (
            "Cancellation preview only. I have not cancelled this ticket yet.\n\n"
            f"Ticket {result['ticket_id']}: {result['airline_name']} {result['flight_number']}{route} departing at "
            f"{result['departure_date_time']} is currently {status}.\n\n"
            f"{policy} Cancellation fee: ${fee:.2f}. Estimated refund: ${refund:.2f}.\n\n"
            "Please confirm cancellation before I cancel this ticket."
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

    @staticmethod
    def _format_staff_route_review_analysis(
        route_result: Dict[str, Any],
        review_result: Dict[str, Any],
    ) -> tuple[str, List[Dict[str, Any]]]:
        routes = route_result.get("rows") or []
        reviews = review_result.get("summary") or []
        if not routes and not reviews:
            return "No route performance or review rows were found.", []

        top_route = routes[0] if routes else {}
        worst_review = reviews[0] if reviews else {}
        table: List[Dict[str, Any]] = []
        lines = []

        if top_route:
            route_label = f"{top_route.get('departure_airport')} -> {top_route.get('arrival_airport')}"
            tickets = top_route.get("tickets", 0)
            revenue = float(top_route.get("estimated_revenue") or 0)
            lines.append(
                f"Strongest route by ticket volume: {route_label} with {tickets} tickets "
                f"and estimated revenue ${revenue:.2f}."
            )
            table.append(
                {
                    "signal": "Strong route",
                    "route": route_label,
                    "tickets": tickets,
                    "estimated_revenue": revenue,
                    "flight_number": "",
                    "avg_rating": "",
                    "review_count": "",
                }
            )

        if worst_review:
            flight_number = worst_review.get("flight_number")
            avg_rating = worst_review.get("avg_rating")
            review_count = worst_review.get("review_count", 0)
            lines.append(
                f"Lowest-rated reviewed flight: {flight_number} with average rating "
                f"{float(avg_rating):.2f} across {review_count} reviews."
            )
            table.append(
                {
                    "signal": "Lowest-rated reviewed flight",
                    "route": "",
                    "tickets": "",
                    "estimated_revenue": "",
                    "flight_number": flight_number,
                    "avg_rating": float(avg_rating),
                    "review_count": review_count,
                }
            )

        if routes and reviews:
            lines.append(
                "Recommendation: prioritize investigation where high-demand routes and low-rated flight "
                "experience overlap; the current tools provide route demand and flight review signals as "
                "separate observations."
            )

        return "\n\n".join(lines), table


def _normalize_flight_number(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    return str(value).strip().upper()


def _normalize_datetime(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("T", " ")
    match = re.search(r"(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}(?::\d{2})?))?", text)
    if not match:
        return text
    date_part = match.group(1)
    time_part = match.group(2) or "00:00:00"
    if len(time_part) == 5:
        time_part += ":00"
    return f"{date_part} {time_part}"


def _normalize_travel_date(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else None


def _normalize_month(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text if re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", text) else None


def _normalize_period(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "next_month": "next_month",
        "this_year": "this_year",
        "current_year": "this_year",
        "next_year": "next_year",
    }
    return aliases.get(text)
