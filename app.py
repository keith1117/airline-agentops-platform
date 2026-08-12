import os, hashlib, uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash
import pymysql.cursors
import requests
from pymysql.cursors import DictCursor
from dotenv import load_dotenv
from typing import Any, Dict, Optional, Tuple, List
from agent_service.db import ensure_agent_schema
from agent_service.reporting import resolve_sales_window
from agent_service.tools.customer_tools import cancel_customer_ticket

load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("SECRET_KEY", "dev")

DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "8889")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", "root"),
    "db": os.getenv("MYSQL_DB", "Airline Ticket Reservation System"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": True,
}


class LazyMySQLConnection:
    def __init__(self, config):
        self.config = config
        self._conn = None

    def _connect(self):
        if self._conn is None:
            self._conn = pymysql.connect(**self.config)
        else:
            self._conn.ping(reconnect=True)
        return self._conn

    def cursor(self):
        return self._connect().cursor()

    def commit(self):
        return self._connect().commit()

    def rollback(self):
        return self._connect().rollback()


conn = LazyMySQLConnection(DB_CONFIG)

AGENT_SERVICE_URL = os.getenv("AGENT_SERVICE_URL", "http://localhost:8001").rstrip("/")
agent_http = requests.Session()
agent_http.trust_env = False

# ---------------- helpers ----------------
md5 = lambda s: hashlib.md5(s.encode("utf-8")).hexdigest()

def as_customer():
    return session.get("role") == "customer"

def as_staff():
    return session.get("role") == "staff"

def agent_post(path, payload):
    try:
        resp = agent_http.post(f"{AGENT_SERVICE_URL}{path}", json=payload, timeout=45)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {
            "answer": f"Agent service unavailable or failed: {exc}",
            "tool_calls": [],
            "citations": [],
            "pending_confirmation": None,
        }

def append_agent_message(key, role, content, meta=None):
    messages = session.get(key, [])
    messages.append({"role": role, "content": content, "meta": meta or {}})
    session[key] = messages[-16:]
    session.modified = True

TABLE_LABELS = {
    "airline_name": "Airline",
    "flight_number": "Flight",
    "departure_date_time": "Departure",
    "arrival_date_time": "Arrival",
    "departure_airport": "From",
    "arrival_airport": "To",
    "base_price": "Price",
    "seats_left": "Seats Left",
    "ticket_ID": "Ticket",
    "status": "Status",
    "month": "Month",
    "tickets": "Tickets",
    "estimated_revenue": "Revenue",
    "avg_rating": "Avg Rating",
    "review_count": "Reviews",
    "seats": "Seats",
    "sold": "Sold",
    "load_factor_pct": "Load %",
}

TOOL_LABELS = {
    "search_flights": "Flight search",
    "get_customer_trips": "Trip lookup",
    "cancel_customer_ticket": "Ticket cancellation",
    "create_booking_intent": "Booking intent",
    "confirm_booking": "Booking confirmation",
    "answer_policy_question": "Policy RAG",
    "get_sales_report": "Sales report",
    "analyze_reviews": "Review analysis",
    "get_flight_load_factor": "Load factor",
    "get_route_performance": "Route performance",
    "get_user_preferences": "Memory lookup",
    "save_user_preferences": "Memory update",
}


def _label(key: str) -> str:
    return TABLE_LABELS.get(key, key.replace("_", " ").title())


def _fmt_cell(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _table_from_rows(title: str, rows: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return None
    columns = list(rows[0].keys())
    return {
        "title": title,
        "columns": [{"key": key, "label": _label(key)} for key in columns],
        "rows": [{key: _fmt_cell(row.get(key)) for key in columns} for row in rows[:8]],
        "total": len(rows),
    }


def _tool_result_count(result: Any) -> Optional[int]:
    if not isinstance(result, dict):
        return None
    for key in ("count",):
        if key in result:
            return result[key]
    for key in ("flights", "trips", "rows", "summary", "comments"):
        value = result.get(key)
        if isinstance(value, list):
            return len(value)
    return None


def _summarize_tool_calls(tool_calls: Any) -> List[Dict[str, Any]]:
    if not isinstance(tool_calls, list):
        return []
    summaries = []
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        name = call.get("name", "tool")
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        count = _tool_result_count(call.get("result"))
        summaries.append(
            {
                "name": name,
                "label": TOOL_LABELS.get(name, name),
                "args": {key: _fmt_cell(value) for key, value in args.items() if value not in (None, "")},
                "count": count,
            }
        )
    return summaries


def _agent_table(meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tables = meta.get("tables")
    if tables:
        tool_name = ""
        if meta.get("tool_calls"):
            tool_name = meta["tool_calls"][0].get("name", "")
        title = TOOL_LABELS.get(tool_name, "Table data")
        return _table_from_rows(title, tables)

    for call in meta.get("tool_calls", []) or []:
        if not isinstance(call, dict) or not isinstance(call.get("result"), dict):
            continue
        name = call.get("name", "")
        result = call["result"]
        if name == "search_flights":
            return _table_from_rows("Flight results", result.get("flights"))
        if name == "get_customer_trips":
            return _table_from_rows("Trip lookup", result.get("trips"))
    return None


def _agent_display_content(message: Dict[str, Any], table: Optional[Dict[str, Any]]) -> str:
    content = message.get("content", "")
    meta = message.get("meta") or {}
    if message.get("role") != "assistant":
        return content
    if table and meta.get("tables"):
        total = table.get("total", 0)
        return f"{table['title']} retrieved {total} row{'s' if total != 1 else ''} from the database."
    if meta.get("pending_booking_search"):
        pending = meta["pending_booking_search"]
        return (
            f"Bookable flight found: {pending.get('airline_name')} "
            f"{pending.get('flight_number')} at {pending.get('departure_date_time')}."
        )
    return content


def present_agent_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    presented = []
    for message in messages:
        item = dict(message)
        item["meta"] = message.get("meta") or {}
        table = _agent_table(item["meta"])
        item["table"] = table
        item["tool_summaries"] = _summarize_tool_calls(item["meta"].get("tool_calls"))
        item["display_content"] = _agent_display_content(item, table)
        presented.append(item)
    return presented


def _policy_sections() -> List[Dict[str, str]]:
    policy_path = os.path.join(app.root_path, "docs", "policies", "airline_policy.md")
    with open(policy_path, encoding="utf-8") as fh:
        text = fh.read()
    sections = []
    current = None
    for line in text.splitlines():
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            if current:
                current["body"] = "\n".join(current["lines"]).strip()
                sections.append(current)
            current = {"title": line.replace("## ", "", 1).strip(), "lines": []}
        elif current is not None:
            current["lines"].append(line)
    if current:
        current["body"] = "\n".join(current["lines"]).strip()
        sections.append(current)
    return sections


def _visible_customer_trip_sql(extra_where: str = "") -> str:
    suffix = f" {extra_where}" if extra_where else ""
    return f"""
        SELECT t.ticket_ID, f.airline_name, f.flight_number, f.departure_date_time,
               f.departure_airport, f.arrival_airport, f.arrival_date_time, f.status
        FROM Ticket t
        JOIN Flight f
          ON t.airline_name=f.airline_name
         AND t.flight_number=f.flight_number
         AND t.departure_date_time=f.departure_date_time
        LEFT JOIN ticket_cancellations c
          ON c.customer_email=t.customer_email
         AND c.ticket_id=t.ticket_ID
        WHERE t.customer_email=%s
          AND f.departure_date_time >= NOW()
          AND c.id IS NULL
          {suffix}
        ORDER BY f.departure_date_time
    """


def _next_ticket_id_sql() -> str:
    return """
        SELECT COALESCE(MAX(ticket_id), 0) + 1 AS next_id
        FROM (
            SELECT ticket_ID AS ticket_id FROM Ticket
            UNION
            SELECT ticket_id FROM ticket_cancellations
        ) used_ticket_ids
    """

def build_staff_query(
    airline: str,
    period: str,
    start_date: str,
    end_date: str,
    from_ap: str,
    to_ap: str,
    from_city: str,
    to_city: str,
):
   
    period = (period or "").strip().lower()
    from_ap = (from_ap or "").strip().upper()
    to_ap   = (to_ap or "").strip().upper()
    from_city = (from_city or "").strip()
    to_city   = (to_city or "").strip()
    start_date = (start_date or "").strip()
    end_date   = (end_date or "").strip()

    where = ["f.airline_name = %s"]
    params = [airline]

    if start_date and end_date:
        if end_date < start_date:
            start_date, end_date = end_date, start_date
        where.append("f.departure_date_time >= %s")
        where.append("f.departure_date_time < DATE_ADD(%s, INTERVAL 1 DAY)")
        params.extend([start_date, end_date])
    else:
        if period == "current":
            where.append("DATE(f.departure_date_time) = CURRENT_DATE")
        elif period == "future":
            where.append("f.departure_date_time >= CURRENT_TIMESTAMP")
        elif period == "past":
            where.append("f.departure_date_time < CURRENT_TIMESTAMP")
        else:
            where.append("f.departure_date_time >= CURRENT_DATE")
            where.append("f.departure_date_time < DATE_ADD(CURRENT_DATE, INTERVAL 30 DAY)")

    if from_ap:
        where.append("f.departure_airport = %s")
        params.append(from_ap)

    if to_ap:
        where.append("f.arrival_airport = %s")
        params.append(to_ap)

    if from_city:
        where.append("da.city LIKE %s")
        params.append(f"%{from_city}%")

    if to_city:
        where.append("aa.city LIKE %s")
        params.append(f"%{to_city}%")

    sql = """
    SELECT f.flight_number,
           f.departure_date_time, f.arrival_date_time,
           f.departure_airport,   f.arrival_airport,
           f.status
    FROM Flight f
    JOIN Airport da ON da.code = f.departure_airport
    JOIN Airport aa ON aa.code = f.arrival_airport
    WHERE {where}
    ORDER BY f.departure_date_time
    """.format(where=" AND ".join(where))

    return sql, params
    

# ---------------- public home & search ----------------
@app.get("/")
def index():
    return render_template("index.html")

@app.route("/search", methods=["GET", "POST"])
def public_search():
    if request.method == "GET":
        return render_template("customer_search.html", rows=[])
    dep = request.form.get("depart", "").upper().strip()
    arr = request.form.get("arrive", "").upper().strip()
    date = request.form.get("date", "").strip()  # YYYY-MM-DD
    sql = (
        "SELECT airline_name, flight_number, departure_date_time, arrival_date_time, base_price, "
        "departure_airport, arrival_airport, status "
        "FROM Flight WHERE departure_date_time >= NOW() AND status != 'CANCELLED'"
    )
    args = []
    if dep:
        sql += " AND departure_airport=%s"; args.append(dep)
    if arr:
        sql += " AND arrival_airport=%s"; args.append(arr)
    if date:
        sql += " AND DATE(departure_date_time)=%s"; args.append(date)
    sql += " ORDER BY departure_date_time"
    with conn.cursor() as cur:
        cur.execute(sql, tuple(args))
        rows = cur.fetchall()
    return render_template("customer_search.html", rows=rows, dep=dep, arr=arr, date=date)

# ---------------- registration ----------------
@app.route("/register/customer", methods=["GET", "POST"])
def register_customer():
    if request.method == "GET":
        return render_template("register_customer.html")
    email = request.form.get("email", "").strip().lower()
    name  = request.form.get("name", "").strip()
    pwd_raw = request.form.get("password", "")
    if not email or not pwd_raw:
        flash("Email & password required")
        return redirect(url_for("register_customer"))
    pwd_md5 = md5(pwd_raw)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM Customer WHERE email=%s", (email,))
        if cur.fetchone():
            flash("Email already exists")
            return redirect(url_for("register_customer"))
        cur.execute(
            "INSERT INTO Customer(email, name, password) VALUES(%s,%s,%s)",
            (email, name, pwd_md5),
        )
    conn.commit()
    flash("Registered. Please login.")
    return redirect(url_for("login"))

@app.route("/register/staff", methods=["GET", "POST"])
def register_staff():
    if request.method == "GET":
        return render_template("register_staff.html")
    username = request.form.get("username", "").strip()
    airline  = request.form.get("airline", "").strip()
    pwd_raw  = request.form.get("password", "")
    if not username or not airline or not pwd_raw:
        flash("username/airline/password required")
        return redirect(url_for("register_staff"))
    pwd_md5 = md5(pwd_raw)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM Airline WHERE name=%s", (airline,))
        if not cur.fetchone():
            flash("Airline not found")
            return redirect(url_for("register_staff"))
        cur.execute("SELECT 1 FROM Airline_Staff WHERE username=%s", (username,))
        if cur.fetchone():
            flash("Username exists")
            return redirect(url_for("register_staff"))
        cur.execute(
            "INSERT INTO Airline_Staff(username, password, airline_name) VALUES(%s,%s,%s)",
            (username, pwd_md5, airline),
        )
    conn.commit()
    flash("Staff registered.")
    return redirect(url_for("login"))

# ---------------- login/logout ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    role = request.form.get("role")
    user = request.form.get("username", "")
    pwd  = request.form.get("password", "")
    pwd_md5 = md5(pwd)
    if role == "customer":
        with conn.cursor() as cur:
            cur.execute("SELECT email, name, password FROM Customer WHERE email=%s", (user,))
            row = cur.fetchone()
        # allow md5 or legacy plain (for any preloaded sample rows)
        if not row or (row["password"] not in (pwd_md5, pwd)):
            flash("Invalid credentials")
            return redirect(url_for("login"))
        
        session.update({"role":"customer", "email": row["email"], "display": row.get("name") or row["email"]})
        return redirect(url_for("customer_home"))
    
    elif role == "staff":
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT username, password, airline_name
                FROM Airline_Staff
                WHERE (username = %s OR email_address = %s)
                LIMIT 1
                """,
                (user, user)
            )
            row = cur.fetchone()
        if not row or (row["password"] not in (pwd_md5, pwd)):
            flash("Invalid credentials")
            return redirect(url_for("login"))
        session.update({"role":"staff", "username":row["username"], "airline":row["airline_name"]})
        return redirect(url_for("staff_home"))
    else:
        flash("Choose a role")
        return redirect(url_for("login"))

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.get("/policy")
def policy_center():
    return render_template("policy.html", sections=_policy_sections())

# ---------------- customer use cases ----------------
@app.get("/customer")
def customer_home():
    if not as_customer():
        return redirect(url_for("login"))
    ensure_agent_schema(retries=1, delay_seconds=0)
    email = session["email"]
    with conn.cursor() as cur:
        cur.execute(_visible_customer_trip_sql(), (email,))
        flights = cur.fetchall()
    return render_template("customer_home.html", name=session["display"], flights=flights)


@app.post("/customer/ticket/cancel")
def customer_cancel_ticket():
    if not as_customer():
        return redirect(url_for("login"))
    ensure_agent_schema(retries=1, delay_seconds=0)
    ticket_id_raw = request.form.get("ticket_id", "").strip()
    if not ticket_id_raw.isdigit():
        flash("Choose a valid ticket to cancel.")
        return redirect(url_for("customer_home"))
    result = cancel_customer_ticket(session["email"], int(ticket_id_raw))
    if "error" in result:
        flash(result["error"])
    else:
        flash(
            f"Ticket #{result['ticket_id']} cancelled. "
            f"Cancellation fee ${result['cancellation_fee']:.2f}; estimated refund ${result['refund_amount']:.2f}."
        )
    return redirect(url_for("customer_home"))

@app.route("/customer/agent", methods=["GET", "POST"])
def customer_agent():
    if not as_customer():
        return redirect(url_for("login"))

    session.setdefault("customer_agent_session_id", f"cust-{uuid.uuid4().hex[:12]}")
    chat_key = "customer_agent_messages"

    if request.method == "POST":
        message = request.form.get("message", "").strip()
        if message:
            append_agent_message(chat_key, "user", message)
            result = agent_post(
                "/api/agent/customer/chat",
                {
                    "session_id": session["customer_agent_session_id"],
                    "customer_email": session["email"],
                    "message": message,
                },
            )
            append_agent_message(chat_key, "assistant", result.get("answer", ""), result)
        return redirect(url_for("customer_agent", _anchor="agent-bottom"))

    return render_template(
        "customer_agent.html",
        messages=present_agent_messages(session.get(chat_key, [])),
        agent_url=AGENT_SERVICE_URL,
    )

@app.post("/customer/agent/confirm")
def customer_agent_confirm():
    if not as_customer():
        return redirect(url_for("login"))
    chat_key = "customer_agent_messages"
    booking_intent_id = request.form.get("booking_intent_id")
    idempotency_key = request.form.get("idempotency_key")
    result = agent_post(
        "/api/agent/confirm-booking",
        {
            "booking_intent_id": int(booking_intent_id),
            "customer_email": session["email"],
            "idempotency_key": idempotency_key,
        },
    )
    append_agent_message(chat_key, "assistant", result.get("message", str(result)), result)
    return redirect(url_for("customer_agent", _anchor="agent-bottom"))


@app.post("/customer/agent/confirm-cancellation")
def customer_agent_confirm_cancellation():
    if not as_customer():
        return redirect(url_for("login"))
    chat_key = "customer_agent_messages"
    ticket_id = request.form.get("ticket_id")
    result = agent_post(
        "/api/agent/confirm-cancellation",
        {
            "ticket_id": int(ticket_id),
            "customer_email": session["email"],
        },
    )
    if "error" in result:
        answer = result["error"]
    else:
        answer = (
            f"Ticket #{result['ticket_id']} cancelled. "
            f"Cancellation fee ${result['cancellation_fee']:.2f}; estimated refund ${result['refund_amount']:.2f}."
        )
    append_agent_message(chat_key, "assistant", answer, result)
    return redirect(url_for("customer_agent", _anchor="agent-bottom"))

@app.route("/customer/search", methods=["GET", "POST"])
def customer_search():
    if request.method == "GET" and not request.args:
        return render_template("customer_search.html", rows=[])
    source = request.form if request.method == "POST" else request.args
    dep = source.get("depart", "").upper().strip()
    arr = source.get("arrive", "").upper().strip()
    date = source.get("date", "").strip()
    flight_number = source.get("flight_number", "").strip()
    sql = (
        "SELECT airline_name, flight_number, departure_date_time, arrival_date_time, base_price, departure_airport, arrival_airport, status "
        "FROM Flight WHERE departure_date_time >= NOW() AND status != 'CANCELLED'"
    )
    args = []
    if dep: sql += " AND departure_airport=%s"; args.append(dep)
    if arr: sql += " AND arrival_airport=%s"; args.append(arr)
    if flight_number: sql += " AND flight_number=%s"; args.append(flight_number)
    if date: sql += " AND DATE(departure_date_time)=%s"; args.append(date)
    sql += " ORDER BY departure_date_time"
    with conn.cursor() as cur:
        cur.execute(sql, tuple(args))
        rows = cur.fetchall()
    return render_template("customer_search.html", rows=rows, dep=dep, arr=arr, date=date)

@app.post("/customer/purchase")
def customer_purchase():
    if not as_customer():
        return redirect(url_for("login"))
    ensure_agent_schema(retries=1, delay_seconds=0)

    email   = session["email"]
    airline = request.form.get("airline_name", "").strip()
    flight  = request.form.get("flight_number", "").strip()
    dep_dt  = request.form.get("departure_date_time", "").strip()

    name_on_card = request.form.get("name_on_card", email).strip()
    card_type    = request.form.get("card_type", "Credit").strip()
    card_number  = request.form.get("card_number", "").strip()
    exp_date     = request.form.get("expiration_date", "").strip()  # YYYY-MM-DD

    if not (airline and flight and dep_dt and card_number and exp_date):
        flash("Missing fields")
        return redirect(url_for("customer_search"))

    with conn.cursor() as cur:
        cur.execute("""
            SELECT status, departure_date_time
            FROM Flight
            WHERE airline_name=%s AND flight_number=%s AND departure_date_time=%s
            LIMIT 1
        """, (airline, flight, dep_dt))
        row = cur.fetchone()
        if not row:
            flash("Flight not found")
            return redirect(url_for("customer_search"))

        if row["status"] == "CANCELLED":
            flash("Cannot purchase: this flight is CANCELLED.")
            return redirect(url_for("customer_search"))

        cur.execute("SELECT NOW() AS now_ts")
        now_ts = cur.fetchone()["now_ts"]
        if row["departure_date_time"] <= now_ts:
            flash("Cannot purchase: this flight has already departed.")
            return redirect(url_for("customer_search"))

        cur.execute("SELECT name FROM Customer WHERE email=%s", (email,))
        row = cur.fetchone()
        if not row:
            flash("No information found for the currently logged-in user.")
            return redirect(url_for("customer_search"))

        account_name = (row["name"] or "").strip()
        norm = lambda s: " ".join((s or "").split()).lower()
        if norm(name_on_card) != norm(account_name):
            flash("The name on the card must match the account name.")
            return redirect(url_for("customer_search"))

        if not card_number.isdigit():
            flash("Card numbers can only contain numbers.")
            return redirect(url_for("customer_search"))
        
        if not (13 <= len(card_number) <= 19):
            flash("Card number length must be between 13 and 19 digits.")
            return redirect(url_for("customer_search"))

        cur.execute(_next_ticket_id_sql())
        next_id = cur.fetchone()["next_id"]

        cur.execute(
            """
            INSERT INTO Ticket(
                ticket_ID, customer_email, airline_name, flight_number, departure_date_time,
                card_type, card_number, name_on_card, expiration_date, purchase_date_time
            )
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            """,
            (next_id, email, airline, flight, dep_dt,
             card_type, card_number, name_on_card, exp_date),
        )

        cur.execute(
            _visible_customer_trip_sql("AND t.ticket_ID=%s"),
            (email, next_id),
        )
        visible_ticket = cur.fetchone()
        if not visible_ticket:
            cur.execute(
                "DELETE FROM Ticket WHERE ticket_ID=%s AND customer_email=%s",
                (next_id, email),
            )
            conn.commit()
            flash("Purchase could not be completed because the ticket is not visible in My Flights.")
            return redirect(url_for("customer_search"))

    conn.commit()
    flash(f"Ticket purchased (#{next_id})")
    return redirect(url_for("customer_home"))

@app.get("/customer/reviews")
def customer_reviews():
    if not as_customer():
        return redirect(url_for("login"))
    with conn.cursor() as cur:
        cur.execute(
            "SELECT flight_number, airline_name, departure_date_time, rating, comment, created_at "
            "FROM Review WHERE customer_email=%s ORDER BY created_at DESC",
            (session["email"],),
        )
        rows = cur.fetchall()
    return render_template("customer_reviews.html", rows=rows)

@app.post("/customer/review")
def save_review():
    if not as_customer():
        return redirect(url_for("login"))
    email = session["email"]
    airline = request.form.get("airline_name")
    flight  = request.form.get("flight_number")
    dep_dt  = request.form.get("departure_date_time")
    rating  = int(request.form.get("rating", "0"))
    comment = request.form.get("comment", "").strip()
    if rating < 1 or rating > 5:
        flash("Rating must be 1..5")
        return redirect(url_for("customer_home"))
    with conn.cursor() as cur:
        # upsert via try delete+insert
        cur.execute(
            "DELETE FROM Review WHERE customer_email=%s AND airline_name=%s AND flight_number=%s AND departure_date_time=%s",
            (email, airline, flight, dep_dt),
        )
        cur.execute(
            "INSERT INTO Review(customer_email, airline_name, flight_number, departure_date_time, rating, comment, created_at) "
            "VALUES(%s,%s,%s,%s,%s,%s,NOW())",
            (email, airline, flight, dep_dt, rating, comment),
        )
    conn.commit()
    flash("Review saved")
    return redirect(url_for("customer_reviews"))

@app.post("/customer/review/delete")
def delete_review():
    if not as_customer():
        return redirect(url_for("login"))
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM Review WHERE customer_email=%s AND airline_name=%s AND flight_number=%s AND departure_date_time=%s",
            (session["email"], request.form.get("airline_name"), request.form.get("flight_number"), request.form.get("departure_date_time")),
        )
    conn.commit()
    flash("Review deleted")
    return redirect(url_for("customer_reviews"))

# ---------------- staff use cases ----------------
@app.get("/staff")
def staff_home():
    if session.get("role") != "staff":
        return redirect(url_for("login"))

    airline = session.get("airline")

    period      = request.args.get("period")         # current|future|past|range|None
    start_date  = request.args.get("start_date")
    end_date    = request.args.get("end_date")
    from_ap     = request.args.get("from_airport")
    to_ap       = request.args.get("to_airport")
    from_city   = request.args.get("from_city")
    to_city     = request.args.get("to_city")

    sql, params = build_staff_query(
        airline, period, start_date, end_date, from_ap, to_ap, from_city, to_city
    )

    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return render_template(
        "staff_home.html",
        rows=rows,
        airline=airline,
        filters={
            "period": period or "",
            "start_date": start_date or "",
            "end_date": end_date or "",
            "from_airport": from_ap or "",
            "to_airport": to_ap or "",
            "from_city": from_city or "",
            "to_city": to_city or "",
        },
    )

@app.route("/staff/copilot", methods=["GET", "POST"])
def staff_copilot():
    if not as_staff():
        return redirect(url_for("login"))

    session.setdefault("staff_agent_session_id", f"staff-{uuid.uuid4().hex[:12]}")
    chat_key = "staff_agent_messages"

    if request.method == "POST":
        message = request.form.get("message", "").strip()
        if message:
            append_agent_message(chat_key, "user", message)
            result = agent_post(
                "/api/agent/staff/chat",
                {
                    "session_id": session["staff_agent_session_id"],
                    "staff_username": session["username"],
                    "airline_name": session["airline"],
                    "message": message,
                },
            )
            append_agent_message(chat_key, "assistant", result.get("answer", ""), result)
        return redirect(url_for("staff_copilot", _anchor="agent-bottom"))

    return render_template(
        "staff_copilot.html",
        messages=present_agent_messages(session.get(chat_key, [])),
        airline=session.get("airline"),
        agent_url=AGENT_SERVICE_URL,
    )

@app.get("/staff/customers")
def staff_customers():
    if session.get("role") != "staff":
        return redirect(url_for("login"))

    airline = session.get("airline")
    flight  = request.args.get("flight_number")
    dep_dt  = request.args.get("departure_date_time")

    if not (airline and flight and dep_dt):
        flash("Missing flight keys")
        return redirect(url_for("staff_home"))

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.email, c.name, t.card_type, t.card_number, t.name_on_card
            FROM Ticket t
            JOIN Customer c ON c.email = t.customer_email
            WHERE t.airline_name=%s AND t.flight_number=%s AND t.departure_date_time=%s
            ORDER BY c.name
            """,
            (airline, flight, dep_dt),
        )
        customers = cur.fetchall()

    return render_template(
        "staff_customers.html",
        airline=airline,
        flight_number=flight,
        departure_date_time=dep_dt,
        customers=customers,
    )

@app.route("/staff/create-flight", methods=["GET", "POST"])
def staff_create_flight():
    if not as_staff():
        return redirect(url_for("login"))

    airline = session["airline"]

    if request.method == "GET":
        with conn.cursor() as cur:
            cur.execute("""
                SELECT flight_number, departure_date_time, arrival_date_time,
                       departure_airport, arrival_airport, status
                FROM Flight
                WHERE airline_name=%s
                  AND departure_date_time >= NOW()
                  AND departure_date_time < DATE_ADD(NOW(), INTERVAL 30 DAY)
                ORDER BY departure_date_time
            """, (airline,))
            rows = cur.fetchall()
        return render_template("staff_create_flight.html", airline=airline, rows=rows)

    data = {
        "airline_name": airline,
        "flight_number": request.form.get("flight_number", "").strip(),
        "departure_date_time": request.form.get("departure_date_time", "").strip(),
        "arrival_date_time": request.form.get("arrival_date_time", "").strip(),
        "base_price": request.form.get("base_price", "0").strip(),
        "departure_airport": request.form.get("departure_airport", "").upper().strip(),
        "arrival_airport": request.form.get("arrival_airport", "").upper().strip(),
        "airplane_id_number": request.form.get("airplane_id_number", "").strip(),
        "status": request.form.get("status", "ON_TIME"),
    }

    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM Airplane WHERE airline_name=%s AND id_number=%s",
            (airline, data["airplane_id_number"]),
        )
        if not cur.fetchone():
            flash("Plane does not belong to your airline")
            return redirect(url_for("staff_create_flight"))

        cur.execute(
            """
            INSERT INTO Flight(airline_name, flight_number, departure_date_time, arrival_date_time,
                               base_price, departure_airport, arrival_airport, airplane_id_number, status)
            VALUES(%(airline_name)s, %(flight_number)s, %(departure_date_time)s, %(arrival_date_time)s,
                   %(base_price)s, %(departure_airport)s, %(arrival_airport)s, %(airplane_id_number)s, %(status)s)
            """,
            data,
        )

    conn.commit()
    flash("Flight created")

    return redirect(url_for("staff_create_flight"))


@app.route("/staff/change-status", methods=["GET", "POST"])
def staff_change_status():
    if not as_staff():
        return redirect(url_for("login"))
    if request.method == "GET":
        return render_template("staff_change_status.html")
    airline = session["airline"]
    flight  = request.form.get("flight_number", "").strip()
    dep_dt  = request.form.get("departure_date_time", "").strip()
    status  = request.form.get("status", "ON_TIME")
    with conn.cursor() as cur:
        cur.execute("SELECT airline_name FROM Flight WHERE airline_name=%s AND flight_number=%s AND departure_date_time=%s",
                    (airline, flight, dep_dt))
        if not cur.fetchone():
            flash("Flight not found / not your airline")
            return redirect(url_for("staff_change_status"))
        cur.execute("UPDATE Flight SET status=%s WHERE airline_name=%s AND flight_number=%s AND departure_date_time=%s",
                    (status, airline, flight, dep_dt))
    conn.commit()
    flash("Status updated")
    return redirect(url_for("staff_home"))

@app.route("/staff/add-airplane", methods=["GET", "POST"])
def staff_add_airplane():
    if not as_staff():
        return redirect(url_for("login"))

    airline = session["airline"]

    if request.method == "GET":
        return render_template("staff_add_airplane.html", airline=airline)

    plane = request.form.get("id_number", "").strip().upper()
    seats = request.form.get("seats", "").strip()
    maker = request.form.get("manufacturer", "").strip()
    age   = request.form.get("age", "").strip()

    if not plane or not seats.isdigit() or not age.isdigit():
        flash("Invalid form: plane id / seats / age are required and must be numeric where applicable.")
        return redirect(url_for("staff_add_airplane"))

    seats_i = int(seats)
    age_i   = int(age)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM Airplane WHERE airline_name=%s AND id_number=%s",
            (airline, plane)
        )
        if cur.fetchone():
            flash("Airplane already exists for this airline.")
            return redirect(url_for("staff_add_airplane"))

        cur.execute(
            """
            INSERT INTO Airplane (id_number, airline_name, seats, manufacturer, age)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (plane, airline, seats_i, maker, age_i)
        )

    conn.commit()
    flash("Airplane added")
    return redirect(url_for("staff_home"))


@app.get("/staff/ratings")

def staff_ratings():
    if not as_staff():
        return redirect(url_for("login"))
    airline = session["airline"]
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT f.airline_name, f.flight_number, f.departure_date_time,
                   AVG(r.rating) AS avg_rating, COUNT(*) AS cnt
            FROM Flight f LEFT JOIN Review r
              ON f.airline_name=r.airline_name AND f.flight_number=r.flight_number AND f.departure_date_time=r.departure_date_time
            WHERE f.airline_name=%s
            GROUP BY f.airline_name, f.flight_number, f.departure_date_time
            ORDER BY f.flight_number, f.departure_date_time
            """,
            (airline,),
        )
        summary = cur.fetchall()
        cur.execute(
            """
            SELECT r.customer_email, r.airline_name, r.flight_number, r.departure_date_time, r.rating, r.comment, r.created_at
            FROM Review r WHERE r.airline_name=%s ORDER BY r.created_at DESC
            """,
            (airline,),
        )
        comments = cur.fetchall()
    return render_template("staff_view_ratings.html", summary=summary, comments=comments)

@app.route("/staff/reports", methods=["GET", "POST"])
def staff_reports():
    if not as_staff():
        return redirect(url_for("login"))
    airline = session["airline"]
    rows = None
    range_label = None
    if request.method == "POST":
        mode = request.form.get("mode")
        start = request.form.get("start")
        end = request.form.get("end")
        window = resolve_sales_window(mode, start_date=start, end_date=end)
        range_label = window["label"]
        with conn.cursor() as cur:
            if mode == "range":
                cur.execute(
                    """
                    SELECT DATE(t.purchase_date_time) AS day, 
                    COUNT(*) AS tickets
                    FROM Ticket t
                    WHERE t.airline_name=%s 
                      AND t.purchase_date_time >= %s
                      AND t.purchase_date_time < %s
                      AND t.purchase_date_time <= NOW()
                    GROUP BY DATE(t.purchase_date_time)
                    ORDER BY day
                    """,
                    (airline, window["start_date"], window["end_date"]),
                )
                rows = cur.fetchall()
            elif mode in {"last_month", "last_year"}:
                cur.execute(
                    """
                    SELECT DATE_FORMAT(t.purchase_date_time, '%%Y-%%m') AS ym, 
                    COUNT(*) AS tickets
                    FROM Ticket t
                    WHERE t.airline_name=%s 
                      AND t.purchase_date_time >= %s
                      AND t.purchase_date_time < %s
                      AND t.purchase_date_time <= NOW()
                    GROUP BY ym 
                    ORDER BY ym
                    """,
                    (airline, window["start_date"], window["end_date"]),
                )
                rows = cur.fetchall()
    return render_template("staff_reports.html", rows=rows, range_label=range_label)

# health
@app.get("/health")
def health():
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1"); cur.fetchone()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=bool(int(os.getenv("FLASK_DEBUG", "1"))),
    )
