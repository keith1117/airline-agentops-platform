import time
from contextlib import asynccontextmanager

from fastapi import Request
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import ensure_agent_schema, get_conn
from .metrics import MetricsCollector
from .rag import PolicyRAG
from .react_agent import ReActAgent
from .schemas import ConfirmBookingRequest, CustomerChatRequest, EvalRunRequest, StaffChatRequest


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_agent_schema()
    yield


app = FastAPI(title="Airline AgentOps Service", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

rag = PolicyRAG(settings.rag_policy_path)
agent = ReActAgent(rag)
metrics = MetricsCollector(settings.metrics_log_path)


@app.middleware("http")
async def collect_metrics(request: Request, call_next):
    started = time.perf_counter()
    status_code = 500
    role = _infer_role(request.url.path)
    tool_count = 0
    error = False
    try:
        response = await call_next(request)
        status_code = response.status_code
        tool_count = int(response.headers.get("X-Agent-Tool-Count", "0"))
        error = status_code >= 500
        return response
    except Exception:
        error = True
        raise
    finally:
        latency_ms = int((time.perf_counter() - started) * 1000)
        metrics.record_request(
            endpoint=request.url.path,
            method=request.method,
            status_code=status_code,
            latency_ms=latency_ms,
            role=role,
            tool_count=tool_count,
            error=error,
        )


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


@app.get("/api/metrics")
def get_metrics():
    return metrics.snapshot()


@app.post("/api/agent/customer/chat")
def customer_chat(req: CustomerChatRequest):
    result = agent.customer_chat(req.session_id, req.customer_email, req.message)
    return _with_tool_count(result)


@app.post("/api/agent/staff/chat")
def staff_chat(req: StaffChatRequest):
    result = agent.staff_chat(req.session_id, req.staff_username, req.airline_name, req.message)
    return _with_tool_count(result)


@app.post("/api/agent/confirm-booking")
def confirm_booking(req: ConfirmBookingRequest):
    return agent.confirm_booking(req.booking_intent_id, req.customer_email, req.idempotency_key)


@app.post("/api/eval/run")
def run_eval(req: EvalRunRequest):
    from .eval_runner import run_eval_suite

    return run_eval_suite(req.suite_name, agent)


def _infer_role(path: str) -> str:
    if "/customer/" in path:
        return "customer"
    if "/staff/" in path:
        return "staff"
    return "system"


def _with_tool_count(result):
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse

    tool_count = len(result.get("tool_calls", [])) if isinstance(result, dict) else 0
    return JSONResponse(content=jsonable_encoder(result), headers={"X-Agent-Tool-Count": str(tool_count)})
