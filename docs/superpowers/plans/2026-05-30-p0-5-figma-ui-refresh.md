# P0.5 Figma-Inspired UI Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh the existing Flask/Jinja airline reservation website so it visually matches the referenced Figma flight-booking style while preserving all P0/P1 Agent functionality.

**Architecture:** Keep the current Flask/Jinja app and CSS-only styling system. Add reusable presentation helpers and CSS components, then update templates page-by-page without changing database schema, Agent tools, RAG, Eval, Docker, or booking logic.

**Tech Stack:** Flask, Jinja templates, plain CSS, existing MySQL-backed pages, existing FastAPI Agent service.

---

## Scope And Guardrails

This is a P0.5 presentation cleanup. It must not implement P2 features.

Do not change:
- `agent_service/react_agent.py`
- `agent_service/tools/*`
- `sql/*.sql`
- `eval/default.jsonl`
- Docker service topology
- Booking confirmation semantics
- Existing route URLs

Allowed changes:
- `static/main.css`
- `templates/*.html`
- small Flask presentation helpers in `app.py`
- README screenshots/demo notes if needed

Visual target from Figma:
- full-bleed travel hero for public landing
- dark navy overlay and navigation
- white floating search/interaction panels
- warm orange CTA buttons
- clean operational cards and tables
- 8px radius for product UI surfaces
- concise, screenshot-friendly AI chat output

---

## File Structure

- `static/main.css`
  - Owns all visual design tokens and reusable classes.
  - Add page layouts, navigation, hero, cards, forms, tables, status chips, and AI chat styles.

- `templates/layout.html`
  - Owns shared navigation shell.
  - Add role-aware nav styling and optional `body_class` support.

- `templates/index.html`
  - Public landing page inspired by the Figma hero/search module.

- `templates/login.html`, `templates/register_customer.html`, `templates/register_staff.html`
  - Auth screens with centered card over a travel-inspired background.

- `templates/customer_home.html`, `templates/customer_search.html`, `templates/customer_reviews.html`, `templates/customer_agent.html`
  - Customer dashboard, search, reviews, and AI Agent pages.

- `templates/staff_home.html`, `templates/staff_copilot.html`, `templates/staff_reports.html`, `templates/staff_create_flight.html`, `templates/staff_change_status.html`, `templates/staff_add_airplane.html`, `templates/staff_view_ratings.html`, `templates/staff_customers.html`
  - Staff dashboard and operations pages.

- `app.py`
  - Only add presentation helpers if templates need role/body metadata.

- `tests/test_ui_templates.py`
  - New smoke tests for template rendering with representative context.

---

## Task 1: Add Visual Tokens And Base Components

**Files:**
- Modify: `static/main.css`

- [ ] **Step 1: Add design tokens at the top of CSS**

Insert this block before the existing `body` rule:

```css
:root {
  --color-navy: #071f3f;
  --color-navy-2: #0e315e;
  --color-orange: #f28c38;
  --color-orange-dark: #d96f1f;
  --color-sky: #eaf4ff;
  --color-mist: #f5f7fb;
  --color-border: #dce3ec;
  --color-text: #14213d;
  --color-muted: #667085;
  --color-success: #237a57;
  --color-warning: #b75d16;
  --shadow-soft: 0 16px 40px rgba(7, 31, 63, 0.12);
  --shadow-card: 0 8px 24px rgba(7, 31, 63, 0.08);
  --radius: 8px;
  --content-max: 1180px;
}
```

- [ ] **Step 2: Replace the global body/nav baseline**

Replace the existing `body` and `nav a` rules with:

```css
body {
  margin: 0;
  font-family: Montserrat, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  color: var(--color-text);
  background: var(--color-mist);
}

body::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(circle at top left, rgba(242, 140, 56, 0.08), transparent 30%),
    radial-gradient(circle at top right, rgba(14, 49, 94, 0.08), transparent 28%);
  z-index: -1;
}

a { color: inherit; }
nav a { margin-right: 0; }
```

- [ ] **Step 3: Add reusable shell/card/button/table classes**

Append this block after the flash rule:

```css
.site-shell { min-height: 100vh; }
.site-nav {
  max-width: var(--content-max);
  margin: 18px auto 0;
  padding: 14px 18px;
  border-radius: var(--radius);
  background: rgba(255, 255, 255, 0.92);
  box-shadow: var(--shadow-card);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 18px;
}
.brand-mark { font-weight: 800; letter-spacing: 0.02em; color: var(--color-navy); text-decoration: none; }
.nav-links { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
.nav-links a {
  text-decoration: none;
  color: var(--color-navy);
  font-weight: 650;
  font-size: 14px;
  padding: 8px 10px;
  border-radius: var(--radius);
}
.nav-links a:hover { background: var(--color-sky); }
.nav-logout { color: var(--color-orange-dark) !important; }
.page-wrap { max-width: var(--content-max); margin: 28px auto 64px; padding: 0 18px; }
.page-header { display: flex; justify-content: space-between; gap: 18px; align-items: end; margin-bottom: 18px; }
.page-kicker { color: var(--color-orange-dark); font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em; font-size: 12px; }
.page-title { margin: 4px 0 0; font-size: 38px; line-height: 1.08; color: var(--color-navy); }
.card {
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-card);
  padding: 18px;
}
.grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }
.btn, button, input[type="submit"] {
  border: 0;
  border-radius: var(--radius);
  background: var(--color-orange);
  color: #fff;
  font-weight: 750;
  padding: 10px 14px;
  cursor: pointer;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.btn:hover, button:hover, input[type="submit"]:hover { background: var(--color-orange-dark); }
.btn-secondary { background: var(--color-navy); }
.btn-secondary:hover { background: var(--color-navy-2); }
.data-table { width: 100%; border-collapse: collapse; background: #fff; }
.data-table th, .data-table td { padding: 10px 12px; border-bottom: 1px solid var(--color-border); text-align: left; }
.data-table th { color: var(--color-muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }
.status-chip {
  display: inline-flex;
  border-radius: 999px;
  padding: 4px 9px;
  font-size: 12px;
  font-weight: 800;
  background: var(--color-sky);
  color: var(--color-navy);
}
```

- [ ] **Step 4: Add responsive baseline**

Append:

```css
@media (max-width: 780px) {
  .site-nav { margin: 0; border-radius: 0; align-items: flex-start; flex-direction: column; }
  .page-title { font-size: 30px; }
  .grid-2, .grid-3 { grid-template-columns: 1fr; }
  .page-header { align-items: flex-start; flex-direction: column; }
}
```

- [ ] **Step 5: Run CSS grep check**

Run:

```bash
rg -n "border-radius: (1[2-9]|[2-9][0-9])px|purple|violet|bokeh|orb" static/main.css
```

Expected: no matches except intentional existing lines if they are not part of new UI.

---

## Task 2: Upgrade Shared Layout Navigation

**Files:**
- Modify: `templates/layout.html`

- [ ] **Step 1: Replace raw navigation with styled shell**

Replace the current navigation/content wrapper with this structure while keeping existing role checks:

```html
<body>
  <div class="site-shell">
    <nav class="site-nav">
      <a class="brand-mark" href="{{ url_for('index') }}">Airline AgentOps</a>
      <div class="nav-links">
        <a href="{{ url_for('index') }}">Home</a>
        {% if session.get('role') == 'customer' %}
          <a href="{{ url_for('customer_home') }}">My Flights</a>
          <a href="{{ url_for('customer_agent') }}">AI Agent</a>
          <a href="{{ url_for('customer_search') }}">Search</a>
          <a href="{{ url_for('customer_reviews') }}">My Reviews</a>
          <a class="nav-logout" href="{{ url_for('logout') }}">Logout</a>
        {% elif session.get('role') == 'staff' %}
          <a href="{{ url_for('staff_home') }}">Staff</a>
          <a href="{{ url_for('staff_copilot') }}">AI Copilot</a>
          <a href="{{ url_for('staff_create_flight') }}">Create Flight</a>
          <a href="{{ url_for('staff_change_status') }}">Change Status</a>
          <a href="{{ url_for('staff_add_airplane') }}">Add Airplane</a>
          <a href="{{ url_for('staff_view_ratings') }}">Ratings</a>
          <a href="{{ url_for('staff_reports') }}">Reports</a>
          <a class="nav-logout" href="{{ url_for('logout') }}">Logout</a>
        {% else %}
          <a href="{{ url_for('login') }}">Sign In</a>
          <a class="btn" href="{{ url_for('register_customer') }}">Sign Up</a>
        {% endif %}
      </div>
    </nav>

    <main class="page-wrap">
      {% with messages=get_flashed_messages() %}
        {% if messages %}<ul class="flash">{% for m in messages %}<li>{{ m }}</li>{% endfor %}</ul>{% endif %}
      {% endwith %}
      {% block content %}{% endblock %}
    </main>
  </div>
</body>
```

- [ ] **Step 2: Render smoke test**

Run:

```bash
PYTHONPATH=. .venv/bin/python - <<'PY'
from app import app
with app.test_request_context('/'):
    app.jinja_env.get_template('layout.html')
print('layout template loaded')
PY
```

Expected:

```text
layout template loaded
```

---

## Task 3: Redesign Public Landing Page

**Files:**
- Modify: `templates/index.html`
- Modify: `static/main.css`

- [ ] **Step 1: Replace landing content with Figma-inspired hero**

Use this HTML inside `{% block content %}`:

```html
<section class="hero">
  <div class="hero-overlay">
    <p class="page-kicker">Production-like AI Agent MVP</p>
    <h1>Book smarter flights with AI assistance.</h1>
    <p class="hero-copy">Search synthetic airline inventory, ask cited policy questions, and confirm mock bookings through a controlled Agent workflow.</p>
    <div class="hero-actions">
      <a class="btn" href="{{ url_for('login') }}">Start Demo</a>
      <a class="btn btn-secondary" href="{{ url_for('register_customer') }}">Create Customer</a>
    </div>
  </div>
  <div class="hero-search card">
    <div class="search-tab">Flights</div>
    <div class="search-grid">
      <div><span>From</span><strong>SFO</strong></div>
      <div><span>To</span><strong>LAX</strong></div>
      <div><span>Date</span><strong>Next month</strong></div>
      <a class="btn" href="{{ url_for('customer_search') }}">Search Flights</a>
    </div>
  </div>
</section>

<section class="grid-3 landing-stats">
  <div class="card"><span>Agent Tools</span><strong>9</strong><p>Role-guarded tool calls for customer and staff workflows.</p></div>
  <div class="card"><span>Eval Cases</span><strong>20</strong><p>Deterministic checks for tool accuracy, citations, and task success.</p></div>
  <div class="card"><span>Acceptance</span><strong>18 passed</strong><p>P0/P1 tested against MySQL and Docker Compose.</p></div>
</section>
```

- [ ] **Step 2: Add landing CSS**

Append:

```css
.hero {
  position: relative;
  min-height: 620px;
  border-radius: var(--radius);
  overflow: hidden;
  background:
    linear-gradient(90deg, rgba(7, 31, 63, 0.82), rgba(7, 31, 63, 0.32)),
    url("https://images.unsplash.com/photo-1436491865332-7a61a109cc05?auto=format&fit=crop&w=1800&q=80");
  background-size: cover;
  background-position: center;
  box-shadow: var(--shadow-soft);
}
.hero-overlay { max-width: 740px; padding: 96px 54px; color: #fff; }
.hero h1 { margin: 0; font-size: 58px; line-height: 1.05; letter-spacing: 0; }
.hero-copy { font-size: 18px; line-height: 1.55; max-width: 620px; color: rgba(255, 255, 255, 0.88); }
.hero-actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 26px; }
.hero-search {
  position: absolute;
  left: 54px;
  right: 54px;
  bottom: 42px;
}
.search-tab { font-weight: 800; color: var(--color-navy); margin-bottom: 14px; }
.search-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; align-items: center; }
.search-grid div { border-right: 1px solid var(--color-border); padding-right: 14px; }
.search-grid span, .landing-stats span { color: var(--color-muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 800; }
.search-grid strong, .landing-stats strong { display: block; margin-top: 6px; font-size: 24px; color: var(--color-navy); }
.landing-stats { margin-top: 22px; }
.landing-stats p { color: var(--color-muted); margin-bottom: 0; line-height: 1.45; }
@media (max-width: 780px) {
  .hero { min-height: 720px; }
  .hero-overlay { padding: 54px 24px; }
  .hero h1 { font-size: 40px; }
  .hero-search { left: 18px; right: 18px; bottom: 18px; }
  .search-grid { grid-template-columns: 1fr; }
  .search-grid div { border-right: 0; border-bottom: 1px solid var(--color-border); padding-bottom: 10px; }
}
```

- [ ] **Step 3: Browser check**

Open:

```text
http://127.0.0.1:5050/
```

Expected:
- full travel hero visible in first viewport
- search panel visible in first viewport
- no text overflow on desktop width

---

## Task 4: Refresh Auth Screens

**Files:**
- Modify: `templates/login.html`
- Modify: `templates/register_customer.html`
- Modify: `templates/register_staff.html`
- Modify: `static/main.css`

- [ ] **Step 1: Wrap login form in auth layout**

Use this structure around the existing form fields:

```html
<section class="auth-page">
  <div class="auth-card card">
    <p class="page-kicker">Welcome back</p>
    <h1 class="page-title">Sign in</h1>
    <p class="muted">Access customer booking tools or staff operations.</p>
    <!-- existing login form goes here -->
  </div>
</section>
```

- [ ] **Step 2: Wrap both registration pages similarly**

Use:

```html
<section class="auth-page">
  <div class="auth-card card">
    <p class="page-kicker">Create account</p>
    <h1 class="page-title">Customer registration</h1>
    <!-- existing customer registration form goes here -->
  </div>
</section>
```

For staff:

```html
<section class="auth-page">
  <div class="auth-card card">
    <p class="page-kicker">Airline operations</p>
    <h1 class="page-title">Staff registration</h1>
    <!-- existing staff registration form goes here -->
  </div>
</section>
```

- [ ] **Step 3: Add auth CSS**

Append:

```css
.auth-page {
  min-height: 680px;
  display: grid;
  place-items: center;
  border-radius: var(--radius);
  background:
    linear-gradient(rgba(7, 31, 63, 0.55), rgba(7, 31, 63, 0.55)),
    url("https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1600&q=80");
  background-size: cover;
  background-position: center;
}
.auth-card { width: min(460px, calc(100% - 32px)); }
.auth-card form { display: grid; gap: 12px; margin-top: 16px; }
input, select, textarea {
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 10px 12px;
  font: inherit;
  background: #fff;
}
label { font-weight: 650; color: var(--color-navy); }
```

- [ ] **Step 4: Template smoke render**

Run:

```bash
PYTHONPATH=. .venv/bin/python - <<'PY'
from app import app
for name in ['login.html', 'register_customer.html', 'register_staff.html']:
    with app.test_request_context('/'):
        app.jinja_env.get_template(name).render()
print('auth templates rendered')
PY
```

Expected:

```text
auth templates rendered
```

---

## Task 5: Refresh Customer Pages

**Files:**
- Modify: `templates/customer_home.html`
- Modify: `templates/customer_search.html`
- Modify: `templates/customer_reviews.html`
- Modify: `static/main.css`

- [ ] **Step 1: Add consistent page headers**

At the top of each customer page content block, add:

```html
<div class="page-header">
  <div>
    <p class="page-kicker">Customer workspace</p>
    <h1 class="page-title">My Flights</h1>
    <p class="muted">Track upcoming trips, search flights, and continue through the AI Agent.</p>
  </div>
  <a class="btn" href="{{ url_for('customer_agent') }}">Open AI Agent</a>
</div>
```

Use page-specific title/copy:
- `customer_home.html`: `My Flights`
- `customer_search.html`: `Search Flights`
- `customer_reviews.html`: `My Reviews`

- [ ] **Step 2: Convert flight/search results to card/table styling**

For tables, use class:

```html
<table class="data-table">
```

For each purchase/review action button, use existing form action but rely on global `button` styling.

- [ ] **Step 3: Add customer card accents**

Append:

```css
.trip-card {
  display: grid;
  gap: 8px;
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-card);
  padding: 16px;
}
.route-line { display: flex; align-items: center; gap: 10px; font-weight: 800; color: var(--color-navy); }
.route-line span { color: var(--color-orange-dark); }
.price-text { color: var(--color-navy); font-size: 20px; font-weight: 850; }
```

- [ ] **Step 4: Customer page visual check**

Open:

```text
http://127.0.0.1:5050/customer/search
http://127.0.0.1:5050/customer/agent
```

Expected:
- nav and page header match landing visual language
- no raw table borders from browser default
- CTA buttons use orange/navy styling

---

## Task 6: Refresh AI Agent And Copilot Pages

**Files:**
- Modify: `templates/customer_agent.html`
- Modify: `templates/staff_copilot.html`
- Modify: `static/main.css`

- [ ] **Step 1: Add page headers**

Customer:

```html
<div class="page-header">
  <div>
    <p class="page-kicker">AI Booking Assistant</p>
    <h1 class="page-title">Customer Booking Agent</h1>
    <p class="muted">Search flights, ask cited policy questions, and confirm mock bookings.</p>
  </div>
</div>
```

Staff:

```html
<div class="page-header">
  <div>
    <p class="page-kicker">AgentOps Copilot</p>
    <h1 class="page-title">Staff Operations Copilot</h1>
    <p class="muted">Ask for sales, review, load-factor, or route analysis for {{ airline }}.</p>
  </div>
</div>
```

- [ ] **Step 2: Wrap chat and prompts in two-column layout**

Use this structure:

```html
<div class="agent-layout">
  <section class="agent-panel card">
    <!-- existing messages and input form -->
  </section>
  <aside class="demo-panel card">
    <h3>Demo prompts</h3>
    <!-- existing prompt list -->
  </aside>
</div>
```

- [ ] **Step 3: Add AI page CSS**

Append:

```css
.agent-layout { display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 18px; align-items: start; }
.agent-panel { max-width: none; }
.demo-panel h3 { margin-top: 0; color: var(--color-navy); }
.demo-panel ul { padding-left: 18px; color: var(--color-muted); line-height: 1.55; }
.agent-message { box-shadow: none; }
.agent-message.assistant { border-color: #cfe3d4; }
.agent-message.user { border-color: #d7e4ff; }
.agent-table { border-radius: var(--radius); overflow: hidden; }
.agent-table th { background: var(--color-navy); color: #fff; }
@media (max-width: 900px) { .agent-layout { grid-template-columns: 1fr; } }
```

- [ ] **Step 4: AI page checks**

Open:

```text
http://127.0.0.1:5050/customer/agent
http://127.0.0.1:5050/staff/copilot
```

Expected:
- tool calls remain collapsible
- citations render as pills
- staff tables render as readable tables, not raw dictionaries
- pending booking confirmation remains visible and clearly labeled mock payment

---

## Task 7: Refresh Staff Operational Pages

**Files:**
- Modify: `templates/staff_home.html`
- Modify: `templates/staff_reports.html`
- Modify: `templates/staff_create_flight.html`
- Modify: `templates/staff_change_status.html`
- Modify: `templates/staff_add_airplane.html`
- Modify: `templates/staff_view_ratings.html`
- Modify: `templates/staff_customers.html`
- Modify: `static/main.css`

- [ ] **Step 1: Add staff page headers**

Use this pattern at the top of every staff page:

```html
<div class="page-header">
  <div>
    <p class="page-kicker">Airline operations</p>
    <h1 class="page-title">Reports</h1>
    <p class="muted">Monitor revenue, routes, ratings, and operational status.</p>
  </div>
  <a class="btn btn-secondary" href="{{ url_for('staff_copilot') }}">Open AI Copilot</a>
</div>
```

Set titles per page:
- `staff_home.html`: `Staff Dashboard`
- `staff_reports.html`: `Reports`
- `staff_create_flight.html`: `Create Flight`
- `staff_change_status.html`: `Change Flight Status`
- `staff_add_airplane.html`: `Add Airplane`
- `staff_view_ratings.html`: `Ratings`
- `staff_customers.html`: `Customers`

- [ ] **Step 2: Style operational tables**

Change all staff tables to:

```html
<table class="data-table">
```

- [ ] **Step 3: Style filter/forms**

Wrap forms in:

```html
<div class="card">
  <form class="filters">
    <!-- existing fields -->
  </form>
</div>
```

- [ ] **Step 4: Staff visual check**

Open:

```text
http://127.0.0.1:5050/staff
http://127.0.0.1:5050/staff/reports
http://127.0.0.1:5050/staff/change-status
```

Expected:
- staff pages feel like a dashboard, not raw HTML forms
- tables remain dense and scannable
- no cards nested inside cards unless it is a repeated item or form panel

---

## Task 8: Add Template Smoke Tests

**Files:**
- Create: `tests/test_ui_templates.py`

- [ ] **Step 1: Add smoke tests**

Create:

```python
from app import app, present_agent_messages


def render_template(name, **context):
    with app.test_request_context("/"):
        return app.jinja_env.get_template(name).render(**context)


def test_public_and_auth_templates_render():
    for name in ["index.html", "login.html", "register_customer.html", "register_staff.html"]:
        html = render_template(name)
        assert "<form" in html or "Book smarter flights" in html


def test_agent_templates_render_structured_messages():
    messages = present_agent_messages([
        {
            "role": "assistant",
            "content": "Sales report raw fallback",
            "meta": {
                "tables": [{"month": "2026-05", "tickets": 1, "estimated_revenue": 420.0}],
                "tool_calls": [{"name": "get_sales_report", "args": {"airline_name": "United"}, "result": {"count": 1}}],
            },
        },
        {
            "role": "assistant",
            "content": "Policy answer",
            "meta": {
                "citations": [{"section": "Refund Policy", "chunk_id": "policy-2"}],
                "tool_calls": [{"name": "answer_policy_question", "args": {"question": "refund"}, "result": {"citations": [1]}}],
            },
        },
    ])

    customer = render_template("customer_agent.html", messages=messages, agent_url="http://agent:8001")
    staff = render_template("staff_copilot.html", messages=messages, airline="United", agent_url="http://agent:8001")

    assert "agent-table" in customer
    assert "citation-pill" in customer
    assert "agent-table" in staff
    assert "Tool calls" in staff
```

- [ ] **Step 2: Run smoke tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_ui_templates.py -q
```

Expected:

```text
2 passed
```

---

## Task 9: Full Verification

**Files:**
- Read-only verification across the project.

- [ ] **Step 1: Run no-DB tests**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_agent_core.py tests/test_p1_docker_config.py tests/test_ui_templates.py -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 2: Rebuild Docker stack**

Run:

```bash
docker compose down
docker compose up --build
```

Expected:
- MySQL becomes healthy.
- seed service exits with code 0.
- Agent service runs on container port 8001.
- Flask service runs on container port 5000.
- Browser reaches Flask through `http://127.0.0.1:5050`.

- [ ] **Step 3: Run full acceptance suite from local terminal**

Run:

```bash
PYTHONPATH=. RUN_P0_ACCEPTANCE=1 RUN_P1_MEMORY=1 RUN_P1_EVAL=1 RUN_P1_TRACE=1 RUN_P1_CORE=1 \
MYSQL_HOST=127.0.0.1 MYSQL_PORT=3307 MYSQL_USER=root MYSQL_PASSWORD=root \
MYSQL_DB="Airline Ticket Reservation System" \
.venv/bin/python -m pytest tests -q
```

Expected:

```text
18 passed
```

- [ ] **Step 4: Manual screenshot checklist**

Open:

```text
http://127.0.0.1:5050/
http://127.0.0.1:5050/customer/search
http://127.0.0.1:5050/customer/agent
http://127.0.0.1:5050/staff/copilot
http://127.0.0.1:5050/staff/reports
```

Confirm:
- landing first viewport includes hero image and search panel
- customer search is usable without horizontal overflow
- customer agent shows citations and booking confirmation clearly
- staff copilot shows table data, not raw dict output
- staff reports/dashboard pages have consistent nav, cards, and tables

---

## Task 10: Documentation Update

**Files:**
- Modify: `README.md`
- Modify: `docs/project_progress_report_p0.md`

- [ ] **Step 1: Add P0.5 note to README**

Add under the project summary:

```markdown
P0.5 adds a Figma-inspired visual refresh for portfolio presentation: travel hero, refined navigation, dashboard cards, readable tables, and polished Agent/Copilot chat panels. It is presentation-only and does not change Agent behavior.
```

- [ ] **Step 2: Add P0.5 status to progress report**

Add:

```markdown
## 11. P0.5 Presentation Cleanup

P0.5 updates the visual presentation of the Flask/Jinja website based on a flight-booking Figma reference. The scope is limited to UI styling, template layout, and screenshot readiness. Agent behavior, database schema, booking confirmation, eval, and Docker topology remain unchanged.
```

- [ ] **Step 3: Final doc grep**

Run:

```bash
rg -n "P0.5|Figma-inspired|18 passed|mock payment|synthetic" README.md docs
```

Expected:
- README and progress report mention P0.5.
- Boundaries still mention mock payment and synthetic data.

---

## Self-Review

Spec coverage:
- Figma visual direction: covered by Tasks 1, 3, 4, 5, 6, 7.
- No core Agent changes: covered by Scope And Guardrails and verification.
- All major site pages: covered by Tasks 3 through 7.
- Tests and Docker verification: covered by Tasks 8 and 9.
- Documentation: covered by Task 10.

Placeholder scan:
- No task uses placeholder language or undefined future work.
- Each implementation task specifies exact files and expected checks.

Type consistency:
- New CSS classes are consistently referenced across tasks.
- New smoke tests use existing `app` and `present_agent_messages`.
