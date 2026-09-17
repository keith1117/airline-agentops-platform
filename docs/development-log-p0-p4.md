# Airline AgentOps Platform: Complete P0–P4 Development Log

[English](development-log-p0-p4.md) | [中文](<development-log-p0-p4(Chinese).md>)

## Document Information

| Item | Details |
| --- | --- |
| Development status | P0–P4 complete |
| Implementation period | May 30, 2026 to September 12, 2026 |
| Final acceptance date | September 12, 2026 |
| Current baseline | P0–P4 completion release on `main` and `codex/p4-agentops-governance` |
| System boundary | Synthetic airline inventory, mock payment, and a local Docker demonstration environment |

This document consolidates the goals, implementation work, key decisions, milestone acceptance results, and final verification data for P0–P4. Milestone figures are historical acceptance snapshots; use the “Final Integrated Acceptance” section for the current project status.

## Phase Overview

| Phase | Primary objective | Main deliverables | Phase acceptance |
| --- | --- | --- | --- |
| P0 | Upgrade the traditional Flask/MySQL airline system into a demonstrable Agent MVP | FastAPI Agent, controlled tools, RAG, Customer Agent, Staff Copilot, traces, and mock confirmation | MySQL acceptance: `8 passed`; customer and staff browser flows passed |
| P1 | Add personalized memory, measurable evals, trajectory export, and a reproducible runtime | User preferences, 20-case eval, SFT-ready JSONL, core regressions, and Docker Compose | Initial eval: `20/20`; P0/P1 acceptance: `22 passed`; four Docker services connected |
| P2 | Establish observability, load validation, and scalable synthetic data | Metrics API/JSONL, Locust, 10k-flight generator, and curated demo seed | Final 20-user smoke: `2813` requests, `0` failures, P95 `33 ms`, `47.17 req/s` |
| P3 | Extend single-step routing into a bounded multi-step ReAct runtime | Booking preparation, cancellation preview, staff multi-tool analysis, auto runtime, and QA harness | Focused regression: `23 passed`; tool order, step limits, permissions, and stop reasons passed |
| P4 | Complete evaluation, AgentOps, durable human confirmation, security, time governance, and product polish | Eval metrics, dashboard, action queue, atomic checkout, signed identity, CSRF, UTC/IANA handling, and city search | Final local regression: `110 passed, 24 skipped`; Docker MySQL regression: `134 passed` |

## P0: Agent MVP Foundation

### Objectives

- Preserve the existing Flask/MySQL business features for flights, customers, staff, tickets, and reviews.
- Add a separate FastAPI Agent service instead of coupling Agent logic directly to Flask routes.
- Access business data through registered tools and prevent the model from executing SQL directly.
- Give customers flight search, trip lookup, policy Q&A, and safe booking-preparation capabilities.
- Give airline staff sales, review, load-factor, and route analytics.
- Return sourced policy answers through RAG and record Agent traces.
- Validate against a real MySQL instance rather than relying only on mocks.

### Implementation Results

- Established the Flask Web → FastAPI Agent → Tool Registry → MySQL service architecture.
- Added `/customer/agent` and `/staff/copilot` pages.
- Registered customer tools for flights, trips, tickets, policies, and booking-related operations.
- Registered staff tools for sales reports, review analysis, load factors, route performance, and policy lookup.
- Added a Markdown airline-policy knowledge base and citation response format.
- Added Agent data structures including `agent_sessions`, `agent_traces`, `booking_intents`, and `user_preferences`.
- Added a minimum future-flight seed so demo inventory does not expire with time.
- Disabled inherited environment proxies for Flask-to-Agent calls so external proxy settings cannot intercept localhost traffic.
- Changed MySQL connections to initialize lazily, allowing application imports before the database is ready.

### P0.5 Presentation Cleanup

- Refactored shared navigation, home-page flight search, authentication, customer pages, staff administration, and Agent conversation layouts.
- Introduced consistent cards, tables, status badges, and responsive styling.
- Added template smoke tests; the milestone result was `4 passed`, later absorbed into the full UI regression suite.

### Acceptance

| Acceptance item | Result |
| --- | --- |
| P0 MySQL acceptance | `8 passed` |
| Customer Agent | Flight search, RAG citations, and booking-confirmation entry point passed |
| Staff Copilot | Staff analytics tools and tabular results passed |
| Permission isolation | Customers cannot call staff-only tools; staff cannot execute customer booking tools |
| Agent health | Flask and FastAPI connected; database and policy knowledge base available |

### Main Commit

- `ed552a2` — Baseline P0/P1/P0.5 Agent platform

## P1: Memory, Evaluation, and Trace Export

### Objectives

- Let customers save preferred routes, airlines, and budgets and apply them when later requests omit those parameters.
- Establish deterministic Agent evaluation for task success, tool accuracy, citations, and step counts.
- Export successful and failed trajectories as JSONL suitable for future training-data selection.
- Add core regressions for RAG fallback, idempotent booking, and refund rules.
- Reproduce MySQL, seed, Agent, and Flask services through Docker Compose.

### Implementation Results

- Completed the persistent memory loop through `remember_user_preference` and `get_user_preferences`.
- Added a JSONL eval suite that checks expected tools, forbidden tools, answer keywords, and citation presence.
- Eval reports include totals, passed cases, task success rate, tool-call accuracy, citation rate, average steps, and failed cases.
- Trace export emits `user → assistant decision summary → tool → assistant final` records with session, role, principal, and tool metadata.
- Docker Compose provides MySQL 8, one-time seeding, the FastAPI Agent, Flask Web, and phpMyAdmin.

### Acceptance

| Acceptance item | Result |
| --- | --- |
| Initial deterministic eval | `20/20 passed` |
| Task success rate | `1.0` |
| Tool-call accuracy | `1.0` |
| Citation presence rate | `1.0` |
| Average steps | `1.1` |
| P0/P1 acceptance | `22 passed` |
| Docker runtime | MySQL, seed, Agent, and Web ran successfully; Web `5050` and Agent `8001` were reachable |

The P1 20-case eval is a milestone snapshot. The final eval contains 23 cases; see Final Integrated Acceptance.

## P2: Observability, Load, and Synthetic Data

### Objectives

- Add low-overhead metrics to FastAPI Agent requests without changing tool or business behavior.
- Build a repeatable small-scale Locust smoke workload.
- Generate large, distinguishable, reproducible synthetic datasets with intact foreign keys.
- Report verifiable latency, error rate, and data volume without claiming production capacity.

### Implementation Results

- Added an in-memory metrics collector and `logs/agent_metrics.jsonl` event log.
- `GET /api/metrics` aggregates request counts, latency, roles, tool calls, and errors.
- Locust covers customer flight search, customer policy Q&A, staff review analysis, staff sales reports, and metrics polling.
- The synthetic-data generator writes SQL by default and modifies MySQL only with `--apply`.
- Generated data uses the `SyntheticAir` airline, `SYN` prefixes, and separate demo email addresses to protect stable demo data.
- Added a smaller curated professional demo seed for human demonstrations.

### Data Volume

| Dataset | Airports | Flights | Customers | Tickets | Reviews |
| --- | ---: | ---: | ---: | ---: | ---: |
| Default synthetic generator | 24 | 10,000 | 2,000 | 50,000 | 5,000 |
| Small generator smoke | 5 | 12 | 8 | 20 | 6 |
| Curated Docker demo seed | 12 | 60 | 20 | 90 | 45 |

### Load Acceptance

The first development smoke used 2 users for 10 seconds to verify that the workload ran. During P4 closeout, the current authenticated configuration was tested again with 20 users for one minute; these are the final figures:

| Scenario | Requests | Failures | Average latency | P95 |
| --- | ---: | ---: | ---: | ---: |
| Customer flight search | 563 | 0 | 26 ms | 45 ms |
| Customer policy Q&A | 563 | 0 | 12 ms | 19 ms |
| Staff review analytics | 563 | 0 | 21 ms | 33 ms |
| Staff sales report | 562 | 0 | 18 ms | 28 ms |
| Metrics polling | 562 | 0 | 1 ms | 2 ms |
| **Total** | **2813** | **0** | **16 ms** | **33 ms** |

- Users: `20`
- Duration: `1m`
- Spawn rate: `5 users/s`
- Throughput: `47.17 requests/s`
- Failure rate: `0%`
- Agent metrics cross-check: `2813` requests, `0` errors, service average `14.39 ms`

This is a local Docker smoke benchmark for regression and demonstration. It is not a production SLA or capacity commitment.

### Main Commits

- `34f1155` — Complete P2 Agent observability and benchmarks
- `302cbdb` — Refresh demo seed and Agent fallback copy
- `bab7fee` — Prepare project for public GitHub release

## P3: Bounded ReAct Agent

### Objectives

- Add observation-driven multi-step execution alongside the stable single-step flow.
- Use `MAX_AGENT_STEPS`, role permissions, and tool risk to prevent infinite loops and unauthorized actions.
- Let the Agent prepare bookings and cancellations without completing high-risk transactions in ordinary chat.
- Let Staff Copilot combine multiple backend observations instead of guessing business data.
- Preserve controllable native, JSON, and deterministic-router fallbacks.

### P3.1 Booking Preparation

- Search bookable flights and observe the returned results.
- Select the cheapest or a specifically requested flight under the user's constraints.
- Ask the user for a flight number and departure time when multiple candidates remain ambiguous.
- Stop with `booking_search_ready`, display **Book**, and hand off to Search Flights checkout.
- Do not call `confirm_booking` or issue a Ticket from the conversation.

### P3.2 Cancellation Preview

- Enter clarification when the ticket ID is missing.
- Retrieve a ticket owned by the current customer and calculate the fee and estimated refund by status.
- Stop with `cancellation_confirmation_required`.
- Do not call `cancel_customer_ticket` in ordinary chat; cancellation occurs through a separate confirmed action.

### P3.3 Staff Multi-tool Copilot

- Combine `get_route_performance` and `analyze_reviews` for multi-tool analysis.
- Correlate sales and reviews by the same departure/arrival route so unrelated poorly rated flights are not assigned to a high-selling route.
- Use review analytics alone for review-only questions and sort in the direction requested by the user.

### P3.4 Auto Runtime and Stability Fixes

- `AGENT_RUNTIME_MODE=auto` selects between simple single-step and bounded multi-step flows.
- Added month/year/relative-date queries, alphanumeric flight numbers, active-trip boundaries, and report time windows.
- The Agent QA harness uses seeded prompt variants to check expected and forbidden tools, citations, confirmation, and request paths.
- Traces record decision summaries, actions, observations, stop reasons, and step counts without storing full chain-of-thought.

### Acceptance

| Acceptance item | Result |
| --- | --- |
| P3 bounded runtime tests | `23 passed` |
| Booking preparation | Search → observation → selection → checkout handoff passed |
| No result / ambiguous selection | No invalid handoff is created; returns no result or clarification |
| Cancellation | Preview does not modify the ticket; ordinary chat cannot execute the confirmation tool |
| Staff multi-tool | Tool order, route correlation, and role boundaries passed |
| Step and trace governance | Maximum steps, stop reason, and trajectory metadata passed |

### Main Commits

- `1f54aea` — Add bounded AgentOps runtime
- `6dc3414` — Add cancellation preview flow
- `d4b4485` — Route Agent booking to Search Flights checkout
- `ef05c8e` — Add bounded Staff Copilot flow
- `51b737a` — Add runtime auto mode
- `6d79eed` — Add Agent QA harness
- `2d3c3d7`, `788e385`, `165c75d` — Trip, report, and route-review correctness fixes

## P4: Evaluation, AgentOps, HITL, and Governance

### Objectives

- Add multi-step tasks, tool order, unauthorized rejection, and confirmation gates to Agent evaluation.
- Give staff a visual interface for traces, metrics, and bounded trajectories.
- Unify booking handoff and cancellation decisions in a persistent action queue.
- Strengthen service identity, CSRF, role and airline isolation, transactions, and sensitive-content boundaries.
- Standardize UTC storage, business-timezone boundaries, and airport/traveler IANA timezone presentation.
- Complete city-name search, Agent UI, and payment-copy product polish.

### P4.1 Agent Eval Upgrade

- Added multi-step success, tool-sequence accuracy, unauthorized rejection, confirmation-gate, and fallback-rate metrics.
- Failed cases retain execution metadata, failure type, and bounded trajectory.
- Dynamic future-ticket fixtures prevent eval drift caused by expired fixed ticket numbers or dates.

Phase result: P4 eval `6/6 passed`; multi-step, tool order, unauthorized rejection, and confirmation gate were all `1.0`; the full Docker regression at that milestone was `100 passed`.

### P4.2 AgentOps Dashboard

- Added a read-only FastAPI dashboard aggregation endpoint with filters for role, request path, runtime mode, and outcome.
- `/staff/agentops` shows trace count, average latency, average steps, fallback rate, errors, and confirmation gates.
- The trace viewer shows tools, stop reasons, runtime modes, and bounded trajectories while hiding full reasoning.
- Staff views hide customer request and response bodies while retaining operational metadata.

Phase result: permissions, filters, and desktop/mobile layouts passed; the full Docker regression at that milestone was `106 passed`.

### P4.3 Persistent Human-in-the-loop Queue

- Booking handoffs and cancellation previews use durable action IDs that expire after 30 minutes by default.
- Every pending, confirmed, rejected, expired, and failed state produces an audit event.
- Customer Pending Actions can operate only on the customer's own actions; Staff Action Queue can view only actions for the staff member's airline and cannot confirm on a customer's behalf.
- Checkout uses action, flight, and allocator row locks, price and preview validation, last-seat protection, and idempotent ticket results.
- Cancellation confirmation is bound to its original preview and stops if rules change or the preview expires.
- User-entered card numbers are validated only as 13–19 digits; the database stores only `MOCK-PAYMENT`.

Phase result: offline regression `90 passed, 23 skipped`; the Docker MySQL regression at that milestone was `113 passed`.

### P4.4 Governance, Security, and Timezone

- Every FastAPI `/api/*` endpoint requires a short-lived signed service identity, with separate customer, staff, and operator permissions.
- Principal and airline scope are independently verified server-side.
- Flask state-changing forms use session-bound CSRF tokens; the shared secret is persisted with restrictive permissions.
- Tool risk is classified as `safe_read`, `controlled_write`, or `human_confirmed`; the model cannot directly execute high-risk tools.
- The retired direct-booking API returns `410 Gone`; purchases can be completed only through Search Flights checkout.
- MySQL sessions, Python services, Docker, traces, and audit records use UTC.
- Flight input is interpreted as airport-local wall time and rejects DST gaps and unresolved ambiguous times.
- The browser detects an IANA timezone and allows an override; pages show both airport-local and traveler time.
- `this month`, `this year`, and custom report ranges are anchored to `BUSINESS_TIMEZONE`.

### P4.5 Final Product Polish

- Flight search accepts IATA codes, English and Chinese city names, and compatible code variants for the complete 24-airport catalog.
- The tool can query city names directly from the `Airport` table, so users are no longer required to enter IATA codes.
- Chinese relative periods `下个月`, `今年`, and `明年` follow the same date-window behavior as their English equivalents.
- Customer Agent and Staff Copilot use a full-width, single-column conversation panel with Demo prompts removed.
- Wide result tables scroll inside their message/card instead of widening the page.
- Demo card-number guidance was removed; invalid lengths return a concise `Invalid card number` error.

### Final P4 Acceptance

| Acceptance item | Result |
| --- | --- |
| Local deterministic regression | `110 passed, 24 skipped` |
| Docker MySQL full regression | `134 passed` |
| Basic Agent eval | `23/23 passed`; tool accuracy and citation presence `1.0` |
| Deterministic QA smoke | `10 passed, 0 failed` |
| Live native tool calling | `search_flights` call passed; both returned flights matched the database row by row |
| Embedding RAG / policy LLM | Embedding retrieval and grounded LLM answer passed; every citation belonged to a knowledge-base chunk |
| API failure fallback | Unavailable native/embedding APIs fell back to deterministic, keyword, and extractive paths while retaining fallback reason and citations |
| Responsive UI | Pending Actions, checkout, and AgentOps had no page-level horizontal overflow at `1440x900` or `390x844` |
| Time governance | UTC, IANA, and DST-aware date/report boundaries passed focused tests |

### Main Commits

- `f2a6ad4` — Add P4 Agent evaluation metrics
- `82839d1` — Add P4 AgentOps trace dashboard
- `6af63f4` — Add persistent human confirmation queue and atomic checkout
- `f40b7f5` — Harden Agent governance and timezone handling
- `46f1031` — Support city flight search and polish Agent UI
- `6b651dc` — Remove demo payment guidance
- `e1daf4a`, `1d43244` — Record authenticated load, live-model, and responsive smoke results
- `8b6c993` — Publish enterprise bilingual README

## Final Integrated Acceptance

| Category | Final status |
| --- | --- |
| Functional scope | P0–P4 complete |
| Customer capabilities | Search, policy, memory, trips, booking handoff, checkout, cancellation confirmation, and Pending Actions |
| Staff capabilities | Copilot analytics, reports, ratings, AgentOps, and Action Queue |
| Agent runtime | Native/JSON/deterministic routing; single-step/bounded/auto runtime |
| Security | Signed identity, CSRF, role/airline isolation, tool risk, transaction guards, and redaction |
| Data and time | MySQL source of truth, canonical UTC storage, IANA display, and DST-aware boundaries |
| Automated tests | Local `110 passed, 24 skipped`; Docker MySQL `134 passed` |
| Eval | `23/23 passed`; tool accuracy and citation presence `1.0` |
| Load | 20 users/1m, `2813` requests, `0` failures, P95 `33 ms` |
| Live model | Native routing, embedding RAG, grounded answers, and citation integrity passed |
| UI | Core P4 pages passed at desktop and 390px viewports |

## Final Boundaries

- The system does not connect to a real GDS, NDC, airline inventory, or ticketing system.
- Payment is mocked; no payment processor is contacted and no user card number is stored.
- Default inventory, customers, tickets, and reviews are local seed or synthetic data.
- The embedding index is a local JSON cache rather than a distributed vector database.
- Eval, trace export, and an SFT-ready data format are implemented, but no real SFT or Agentic RL training has been performed.
- Docker Compose is a local demonstration and acceptance environment, not a production deployment specification.

## Related Documentation

- [English project README](../README.md)
- [Chinese project README](../README.zh-CN.md)
- [P0–P2 original phase record](project_progress_report_p0.md)
- [P3/P4 design and implementation record](P3-P4.md)
- [Airline policy knowledge base](policies/airline_policy.md)
