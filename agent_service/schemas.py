from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class CustomerChatRequest(BaseModel):
    session_id: str
    customer_email: str
    message: str


class StaffChatRequest(BaseModel):
    session_id: str
    staff_username: str
    airline_name: str
    message: str


class ConfirmBookingRequest(BaseModel):
    booking_intent_id: int
    customer_email: str
    idempotency_key: str


class ConfirmCancellationRequest(BaseModel):
    ticket_id: int
    customer_email: str


class AgentResponse(BaseModel):
    answer: str
    citations: List[Dict[str, Any]] = []
    tool_calls: List[Dict[str, Any]] = []
    pending_confirmation: Optional[Dict[str, Any]] = None
    pending_cancellation: Optional[Dict[str, Any]] = None
    tables: Optional[List[Dict[str, Any]]] = None


class EvalRunRequest(BaseModel):
    suite_name: str = "default"
