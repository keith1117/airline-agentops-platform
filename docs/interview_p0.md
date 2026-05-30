# Airline AgentOps Platform Interview Notes

## 1-Minute Pitch

I upgraded a traditional Flask/MySQL airline reservation project into a production-like AI Agent MVP. The system keeps the original reservation workflow, but adds a FastAPI Agent service that can answer customer and staff requests through controlled tool calls. Customers can search flights, ask policy questions through RAG, create a pending booking intent, and confirm a mock ticket. Staff can ask analytics questions such as worst-reviewed flights or route performance. The key engineering focus is not real airline commerce, but safe Agent application design: tool boundaries, role-based access, RAG citations, confirmation before irreversible actions, and acceptance tests.

## Technical Highlights

- Dual-service architecture: Flask web app plus FastAPI Agent service.
- ReAct-style routing: classify request, call a registered tool, observe result, return answer.
- Tool registry with role guards so customers cannot call staff analytics tools.
- RAG policy QA backed by a Markdown airline policy knowledge base with citations.
- Safe booking flow: Agent creates `PENDING_CONFIRMATION`; ticket is written only after explicit user confirmation.
- Mock payment boundary: no real payment processor or airline inventory integration.
- Trace logging through `agent_sessions`, `agent_traces`, and `booking_intents`.
- Agent Memory stores customer route, budget, and airline preferences, then applies them when later searches omit those details.
- P1 Basic Eval adds a deterministic 20-task suite measuring task success rate, tool-call accuracy, citation presence rate, average steps, and failed cases.
- Trace export produces SFT-ready JSONL trajectories for future prompt/tool-schema tuning or supervised fine-tuning data preparation.
- Docker Compose runs MySQL, the seed service, the FastAPI Agent service, and the Flask web app.
- P0/P1 acceptance tests verify 18 core behaviors against MySQL.

## Engineering Trade-Offs

- I kept Flask for the existing web app to avoid destabilizing the original project, and added FastAPI only for the Agent layer.
- I used deterministic request routing for P0 stability instead of relying on LLM planning for every demo path.
- I used a lightweight local RAG retriever for demo reliability; a vector DB can be added later after P0 is stable.
- I chose mock payment and synthetic inventory because real airline booking requires GDS/NDC, payment compliance, refunds, fraud checks, and operational support outside the scope of an internship portfolio project.
- I prioritized acceptance-tested demo flows over large-scale load tests or complex eval infrastructure.

## Known Limitations

- The current P0 demo does not connect to real airline inventory or real payment.
- The RAG retriever is lightweight and local; it is sufficient for policy QA demo but not a full production search stack.
- Agent planning is intentionally constrained to keep demos stable.
- Load testing, real SFT, and Agentic RL are not implemented in the current portfolio scope.
- The UI is functional and demo-oriented, not a polished product interface.

## Future Work

- Add a vector database-backed RAG pipeline with retrieval metrics.
- Add larger Agent Eval suites with citation correctness and failure clustering.
- Expand the current deterministic Basic Eval suite with harder multi-step tasks and regression tracking.
- Add a deployable cloud demo.
- Add Locust load testing after the P0 web demo is stable.
- Use exported traces and failed cases to improve prompts and tool schemas.
- Add stronger authentication, rate limits, structured logs, and observability dashboards.
