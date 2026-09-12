from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from typing import Literal


class CustomerChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)
    customer_email: str
    message: str = Field(min_length=1, max_length=8000)


class StaffChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)
    staff_username: str
    airline_name: str
    message: str = Field(min_length=1, max_length=8000)


class ConfirmBookingRequest(BaseModel):
    booking_intent_id: int
    customer_email: str
    idempotency_key: str


class ConfirmCancellationRequest(BaseModel):
    action_id: str
    ticket_id: Optional[int] = None
    customer_email: str


class AgentResponse(BaseModel):
    answer: str
    citations: List[Dict[str, Any]] = []
    tool_calls: List[Dict[str, Any]] = []
    pending_confirmation: Optional[Dict[str, Any]] = None
    pending_booking_search: Optional[Dict[str, Any]] = None
    pending_cancellation: Optional[Dict[str, Any]] = None
    tables: Optional[List[Dict[str, Any]]] = None


class EvalRunRequest(BaseModel):
    suite_name: Literal["default", "p4"] = "default"
