from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import ensure_agent_schema, get_conn
from .rag import PolicyRAG
from .react_agent import ReActAgent
from .schemas import ConfirmBookingRequest, CustomerChatRequest, EvalRunRequest, StaffChatRequest

app = FastAPI(title="Airline AgentOps Service", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

rag = PolicyRAG(settings.rag_policy_path)
agent = ReActAgent(rag)


@app.on_event("startup")
def startup() -> None:
    ensure_agent_schema()


@app.get("/health")
def health():
    try:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                cur.fetchone()
        finally:
            conn.close()
        return {"ok": True, "service": "agent", "database": "ok", "policy_chunks": len(rag.chunks)}
    except Exception as exc:
        return {"ok": False, "service": "agent", "error": str(exc)}


@app.post("/api/agent/customer/chat")
def customer_chat(req: CustomerChatRequest):
    return agent.customer_chat(req.session_id, req.customer_email, req.message)


@app.post("/api/agent/staff/chat")
def staff_chat(req: StaffChatRequest):
    return agent.staff_chat(req.session_id, req.staff_username, req.airline_name, req.message)


@app.post("/api/agent/confirm-booking")
def confirm_booking(req: ConfirmBookingRequest):
    return agent.confirm_booking(req.booking_intent_id, req.customer_email, req.idempotency_key)


@app.post("/api/eval/run")
def run_eval(req: EvalRunRequest):
    from .eval_runner import run_eval_suite

    return run_eval_suite(req.suite_name, agent)

