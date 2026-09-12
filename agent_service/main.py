import time
import hashlib
from contextlib import asynccontextmanager

from fastapi import Request, HTTPException
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from itsdangerous import BadData
from .security import read_identity

from .actions import ActionError, record_handoffs, decide_action
from .config import settings
from .timezones import utc_now, utc_iso, business_timezone
from .agentops import load_agentops_dashboard
from .db import ensure_agent_schema, get_conn
from .metrics import MetricsCollector
from .rag import PolicyRAG
from .react_agent import ReActAgent
from .schemas import ConfirmBookingRequest, ConfirmCancellationRequest, CustomerChatRequest, EvalRunRequest, StaffChatRequest


@asynccontextmanager
async def lifespan(_: FastAPI):
    business_timezone()
    ensure_agent_schema()
    yield


app = FastAPI(title="Airline AgentOps Service", version="0.1.0", lifespan=lifespan)
@app.middleware("http")
async def authenticate_service(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        try:
            actor = read_identity(request.headers.get("X-Agent-Identity", ""))
        except BadData:
            return JSONResponse({"detail": "Authenticated service identity required."}, status_code=401)
        request.state.actor = actor
        path = request.url.path
        if path.startswith("/api/eval/"):
            allowed = actor["role"] == "operator"
        elif path.startswith("/api/agentops/") or path == "/api/metrics":
            allowed = actor["role"] in {"staff", "operator"}
        elif path.startswith("/api/agent/staff/"):
            allowed = actor["role"] == "staff"
        else:
            allowed = actor["role"] == "customer"
        if not allowed:
            return JSONResponse({"detail": "This role cannot access this endpoint."}, status_code=403)
    return await call_next(request)


@app.exception_handler(ActionError)
async def action_error_handler(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=409)


def require_principal(request, principal, airline=None):
    actor = request.state.actor
    if actor["principal"] != principal or (airline is not None and actor.get("airline") != airline):
        raise HTTPException(403, "Identity does not match the authenticated account.")


def scoped_session(role, principal, session_id):
    return hashlib.sha256(f"{role}:{principal}:{session_id}".encode()).hexdigest()


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
                cur.execute("SELECT @@session.time_zone AS time_zone, NOW() AS now_utc")
                clock = cur.fetchone()
        finally:
            conn.close()
        return {"ok": True, "service": "agent", "database": "ok", "policy_chunks": len(rag.chunks),
                "time": {"python_utc": utc_iso(utc_now()), "mysql_utc": utc_iso(clock["now_utc"]),
                         "mysql_session_timezone": clock["time_zone"], "business_timezone": business_timezone()}}
    except Exception as exc:
        return {"ok": False, "service": "agent", "error": str(exc)}


@app.get("/api/metrics")
def get_metrics():
    return metrics.snapshot()


@app.get("/api/agentops/dashboard")
def get_agentops_dashboard(
    request: Request,
    role: str = "",
    request_path: str = "",
    runtime_mode: str = "",
    outcome: str = "",
    limit: int = 50,
):
    return load_agentops_dashboard(
        metrics.snapshot(),
        airline_name=request.state.actor.get("airline", ""),
        role=role,
        request_path=request_path,
        runtime_mode=runtime_mode,
        outcome=outcome,
        limit=limit,
    )


@app.post("/api/agent/customer/chat")
def customer_chat(req: CustomerChatRequest, request: Request):
    require_principal(request, req.customer_email)
    session_id = scoped_session("customer", req.customer_email, req.session_id)
    result = agent.customer_chat(session_id, req.customer_email, req.message)
    record_handoffs(result, req.customer_email, session_id)
    return _with_tool_count(result)


@app.post("/api/agent/staff/chat")
def staff_chat(req: StaffChatRequest, request: Request):
    require_principal(request, req.staff_username, req.airline_name)
    result = agent.staff_chat(scoped_session("staff", req.staff_username, req.session_id), req.staff_username, req.airline_name, req.message)
    return _with_tool_count(result)


@app.post("/api/agent/confirm-booking")
def confirm_booking(req: ConfirmBookingRequest):
    raise HTTPException(410, "Complete bookings on the Search Flights checkout page.")


@app.post("/api/agent/confirm-cancellation")
def confirm_cancellation(req: ConfirmCancellationRequest, request: Request):
    require_principal(request, req.customer_email)
    return decide_action(req.action_id, req.customer_email, "confirm")


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
