# 分层落地方案：Airline AgentOps Platform

## Summary

目标是把现有 Airline Ticket Reservation System 升级为一个 **Production-like AI Agent MVP**，但按优先级交付：

- **P0：必须完成**。两周内保证可运行、可演示、可写进简历，重点是稳定的 ReAct Agent + Tool Calling + RAG + Web Demo。
- **P1：尽量完成**。增强项目的工程化、评估和简历说服力。
- **P2：可选增强**。只有 P0/P1 稳定后再做，避免为了压测、大规模数据或复杂 eval 影响核心 demo。

最终不追求真实航班库存和真实支付；使用 synthetic/mock data，但实现真实的工具边界、权限控制、确认流程、trace logging 和基础评估。

## P0：两周内必须完成

### 核心架构

采用双服务架构：

- 保留现有 **Flask Web App**，继续承载用户/员工页面。
- 新增 **FastAPI Agent Service**，负责 Agent API、工具调用、RAG、trace。
- Flask 通过 HTTP 调用 FastAPI。
- MySQL 继续作为主业务数据库。
- Vector store 使用本地 Chroma 或轻量持久化目录。

P0 不做大规模重构；只把 Agent 所需的业务能力抽成稳定 service/tool，避免改坏原有课程项目功能。

### Agent Demo

实现两个可演示入口：

- **Customer Booking Agent**
  - 自然语言搜索航班。
  - 查询用户已有订单。
  - 回答航空政策问题。
  - 创建购票意图 `PENDING_CONFIRMATION`。
  - 用户确认后才执行 mock booking。

- **Staff Operations Copilot**
  - 查询销售报表。
  - 分析评论/评分。
  - 查询航班载客情况或热门航线。
  - 只能调用员工权限工具。

实现轻量 ReAct-style runtime：

- `reasoning -> action/tool_call -> observation -> final_answer`
- 每轮最多 4 步，避免 demo 卡死。
- 工具调用必须走 tool registry。
- LLM 不能直接执行 SQL。
- 工具失败时返回清晰错误，而不是让 Agent 编造。

### P0 Tools

Customer tools：

- `search_flights`
- `get_customer_trips`
- `create_booking_intent`
- `confirm_booking`
- `answer_policy_question`

Staff tools：

- `get_sales_report`
- `analyze_reviews`
- `get_flight_load_factor`
- `get_route_performance`

### P0 RAG

实现航空政策知识库：

- 使用 Markdown 文档维护退款、行李、延误、购票确认、mock payment 规则。
- 文档切片、embedding、向量检索。
- 回答必须带 citation。
- 如果知识库没有依据，回答“无法从当前知识库确认”。

### P0 数据库增强

新增最小 Agent 表：

- `agent_sessions`
- `agent_traces`
- `booking_intents`

`booking_intents` 至少包含：

- `id`
- `customer_email`
- `airline_name`
- `flight_number`
- `departure_date_time`
- `status`
- `created_at`
- `confirmed_at`
- `idempotency_key`

购票流程：

- Agent 只能创建 pending booking intent。
- 用户显式确认后才写入 `Ticket`。
- 确认时检查航班存在、未起飞、未取消、未超售。
- mock payment 永远不连接真实支付。

### P0 Web Demo

在 Flask 里新增两个页面：

- `/customer/agent`
- `/staff/copilot`

页面要求简单稳定：

- 输入框 + 消息列表。
- 显示 Agent answer。
- 显示 tool calls 简要记录。
- 如果有 pending booking，显示确认按钮。
- 不追求复杂 UI，只保证面试演示清楚。

### P0 README 与简历素材

README 必须包含：

- 项目定位：Production-like AI Agent MVP。
- 架构图。
- Demo flows：
  - customer searches flight by natural language
  - customer asks refund/baggage policy via RAG
  - customer creates and confirms booking intent
  - staff asks sales/review analytics
- Agent tool list。
- RAG citation 示例。
- Trace log 示例。
- 明确说明：synthetic inventory + mock payment，不接真实航司和真实支付。

## P1：尽量完成

### Agent Memory

实现轻量 memory：

- 保存用户偏好：
  - departure city
  - destination city
  - max budget
  - preferred airline
- Agent 在后续搜索中可引用偏好，但必须允许用户覆盖。
- Memory 存入 `user_preferences` 表。

### Basic Agent Eval

实现小规模 eval，不追求复杂平台：

- 20-30 条 JSONL 任务。
- 覆盖 flight search、policy QA、booking intent、staff report、非法请求拒绝。
- 输出基础指标：
  - task success rate
  - tool call accuracy
  - citation presence rate
  - average steps
  - failed cases

不做自动大模型裁判；P1 可以先用 expected tool / expected answer keyword 做 deterministic eval。

### Docker Compose

提供一键启动：

- Flask app
- FastAPI agent service
- MySQL
- Chroma persistent volume 或本地 vector path

包含 `.env.example`，但不提交真实 API key。

### 测试

补充最关键测试：

- tool 参数校验
- customer/staff tool 权限
- booking intent confirmation
- no direct SQL from Agent
- RAG no-context fallback

### Trace Export

导出 ReAct trajectories：

- JSONL 格式。
- 可用于后续 SFT 数据准备。
- README 说明这是 SFT-ready trajectory logging，不宣称已经做了 SFT。

## P2：P0/P1 稳定后再做

### Load Testing

使用 Locust：

- 小规模模拟 50-100 users。
- 场景包括 search、RAG QA、customer chat、staff query。
- 只记录基础 P50/P95 latency、error rate。
- 不为了压测改动核心代码。

### Synthetic Data Generator

生成更多模拟数据：

- airports
- flights
- customers
- tickets
- reviews

默认规模控制在本地稳定可跑：

- 10k flights
- 50k tickets
- 5k reviews

百万级数据只作为可选扩展，不作为两周交付目标。

### Observability

可选增加：

- structured logs
- token usage logging
- request latency logging
- simple dashboard 或 metrics JSON

### 高阶 Eval / RL 说明

不实现真实 Agentic RL。

只做设计说明：

- reward signals：
  - task completion
  - correct tool call
  - fewer invalid actions
  - citation correctness
  - latency/cost
- 基于 failed traces 的 prompt/tool schema 调优。

## Public Interfaces

FastAPI P0 endpoints：

- `POST /api/agent/customer/chat`
  - input: `session_id`, `customer_email`, `message`
  - output: `answer`, `citations`, `tool_calls`, `pending_confirmation`

- `POST /api/agent/staff/chat`
  - input: `session_id`, `staff_username`, `airline_name`, `message`
  - output: `answer`, `tool_calls`, `tables`

- `POST /api/agent/confirm-booking`
  - input: `booking_intent_id`, `customer_email`, `idempotency_key`
  - output: `ticket_id`, `status`, `message`

- `GET /health`
  - output: service and database status

P1 endpoint：

- `POST /api/eval/run`
  - input: `suite_name`
  - output: summary metrics and failed cases

## Implementation Order

### Phase 1：P0 Foundation

1. 初始化 git。
2. 保留 Flask 现有功能。
3. 新建 FastAPI Agent Service。
4. 建立共享 DB config。
5. 增加 Agent 相关 SQL migration。
6. 实现 tool registry 和基础 trace logging。

### Phase 2：P0 Agent Demo

1. 实现 Customer tools。
2. 实现 Staff tools。
3. 实现 ReAct runtime。
4. 接入 OpenAI-compatible API。
5. 新增 Flask customer/staff chat 页面。
6. 完成 pending booking + confirmation flow。

### Phase 3：P0 RAG

1. 编写航空政策 Markdown。
2. 实现 chunking、embedding、Chroma retrieval。
3. 接入 `answer_policy_question`。
4. 在回答中展示 citation。
5. 完成 README demo 示例。

### Phase 4：P1 Enhancement

1. 增加 user memory。
2. 增加 basic eval runner。
3. 增加核心测试。
4. 增加 Docker Compose。
5. 导出 SFT-ready trajectories。

### Phase 5：P2 Optional

1. 加 Locust。
2. 加 synthetic data generator。
3. 加简单 metrics/logging。
4. 补充 benchmark 表。

## Test Plan

P0 acceptance tests：

- Customer can ask: “Find flights from SFO to LAX next month.”
- Agent calls `search_flights` and returns database-backed results.
- Customer can ask baggage/refund policy and receive cited RAG answer.
- Customer can create booking intent, then confirm it into a Ticket.
- Staff can ask sales/review question and receive database-backed summary.
- Customer cannot call staff tools.
- Staff cannot book tickets on behalf of customer through customer-only flow.
- Agent failure returns controlled error message.

P1 tests：

- Memory affects later search only when user has not overridden preference.
- Eval runner produces metrics JSON.
- Trace JSONL can be exported.
- Docker Compose starts all required services.

P2 tests：

- Locust smoke run completes without high error rate.
- Synthetic data generator creates valid referential data.

## Assumptions

- Main objective is ByteIntern-style AI Agent application development, not real airline commerce.
- P0 stability is more important than P1/P2 completeness.
- OpenAI-compatible API is the default LLM/embedding interface.
- Real SFT and Agentic RL are out of scope for the two-week build.
- Large-scale data and pressure testing are P2 only and must not delay the core Agent demo.
- The current project is not a git repo; implementation should start by initializing git so progress can be documented.
