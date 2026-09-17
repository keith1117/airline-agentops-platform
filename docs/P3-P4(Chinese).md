# P3/P4 Bounded AgentOps Implementation Record

[English](P3-P4.md) | [中文](<P3-P4(Chinese).md>)

> **Status:** P0–P4 development is complete. This document is retained as the design rationale, implementation history, and acceptance record for the bounded AgentOps phases.

## Summary

当前项目已经是一个真实的 AI Agent 应用：有 LLM/native tool-calling adapter、JSON router、RAG、memory、tools、trace、eval 和 Docker。但现有 runtime 主要还是 **single-step routing + backend workflow**，还不是完整的 observation-driven multi-step Agent loop。

下一阶段目标分两层：

- **P3：Bounded Autonomous ReAct Agent**  
  把当前 single-step Agent 升级为受控多步 Agent：`plan/action -> tool execution -> observation -> next action/final`，但限制最大步数、工具权限和交易确认边界。
- **P4：AgentOps Governance + Evaluation + Human-in-the-loop**  
  在 P3 稳定后做治理、评估、可观测性和人工确认队列，让项目更像企业级 Agent 平台，而不是继续堆功能。

默认策略：**不做 infinite autonomous agent**。航空订票涉及交易、取消、退款和权限，最终形态应是 bounded autonomous multi-step Agent。

## P3 Key Changes

### P3.1 Bounded ReAct Booking Preparation

优先实现一个稳定 vertical slice，不一次性重写所有 agent flow。

新增运行模式：

```env
AGENT_RUNTIME_MODE=single_step | bounded_react
MAX_AGENT_STEPS=4
```

默认保持：

```env
AGENT_RUNTIME_MODE=single_step
```

`bounded_react` 先作为显式启用模式，稳定后再考虑 `auto`。

首个支持场景：

```text
Find the cheapest United flight from SFO to LAX next month and prepare a booking.
```

目标执行链：

```text
User goal
-> select search_flights
-> observe available flights
-> rank/select cheapest valid flight
-> stop with booking_search_ready
-> display a Book handoff button
-> user continues on the Search Flights page
-> user manually reviews the exact flight and enters payment details
```

实现边界：

- LLM/native router 负责选择下一步 action，不直接执行 SQL 或交易。
- 后端仍通过 tool registry 执行工具、校验权限、格式化业务结果。
- Customer Agent 不在聊天中创建或确认购票；它只能展示可购航班并跳转到 Search Flights 页面。
- `create_booking_intent` / `confirm_booking` 不进入 customer chat loop。购票必须通过 Search Flights 页面由用户手动提交 payment 信息。
- `cancel_customer_ticket` 在 P3.1 不进入 loop，只保留现有路径。
- 不记录完整 chain-of-thought；trace 字段使用 `decision_summary` / `action` / `observation` / `stop_reason`。

建议新增或调整的核心位置：

- `agent_service/config.py`：加入 `AGENT_RUNTIME_MODE`。
- `agent_service/react_agent.py` 或新建 `agent_service/bounded_runtime.py`：实现 bounded loop。
- `agent_service/tool_registry.py`：加入工具风险等级。

工具风险等级：

```text
safe_read:
  search_flights
  get_customer_trips
  get_customer_ticket
  get_user_preferences
  answer_policy_question
  staff analytics tools

controlled_write:
  remember_user_preference

human_confirmed:
  cancel_customer_ticket
```

### P3.2 Cancellation Preview Flow

在 P3.1 稳定后扩展取消流程，但仍保持确认边界。

目标链路：

```text
User asks to cancel flight
-> ask for ticket_id if missing
-> get_customer_ticket
-> calculate refund preview
-> stop with cancellation_confirmation_required
-> user confirms through separate confirmation action
```

要求：

- Agent 可以解释取消费用和预计退款。
- 不允许普通 chat loop 直接取消机票。
- ON_TIME / DELAYED / CANCELLED 的退款规则继续由后端工具决定，不由 LLM 编造。

### P3.3 Staff Multi-step Copilot

在 customer bounded flow 稳定后再做 staff 多步分析。

示例：

```text
Which route has strong sales but poor reviews?
```

目标链路：

```text
get_route_performance
-> analyze_reviews
-> combine observations
-> final recommendation
```

要求：

- staff only tools 只能由 staff role 调用。
- customer 永远不能进入 staff analytics 工具。
- 最终分析可由 LLM总结，但数据必须来自后端工具 observation。

### P3.4 Optional Runtime Auto Mode

已增加：

```env
AGENT_RUNTIME_MODE=auto
```

语义：

- 简单请求继续走 single-step。
- 需要多步工具协作的请求走 bounded_react。
- 如果 auto 分类不稳定，保留显式 `single_step` / `bounded_react` 作为演示和测试主路径。

### P3 Completion Status

P3.1、P3.2、P3.3 和 P3.4 的计划功能均已实现：

- customer booking preparation 使用 bounded search/observation/selection，并 handoff 到 Search Flights checkout。
- cancellation 使用 preview + explicit confirmation，普通 chat loop 不直接取消。
- staff copilot 支持 route performance + review analysis 多工具链。
- `auto` runtime 可以在 single-step 与 bounded ReAct 之间选择。
- step limit、tool risk、role permission、trajectory 和 stop reason 已覆盖专项测试。

当前状态为：**P4 implementation complete**。P4.1 eval、P4.2 AgentOps dashboard、P4.3 persistent human confirmation queue、P4.4 governance hardening 和跨时区时间治理均已实现；离线确定性回归通过，Docker MySQL acceptance 命令保留用于有 Docker daemon 权限的环境。

## P4 Key Changes

P4 只在 P3 通过后开始，不抢 P3 时间。

### Agent Eval Upgrade

扩展现有 eval：

- 多步任务成功率。
- 工具顺序准确率。
- 越权调用拒绝率。
- confirmation gate 命中率。
- RAG citation rate。
- fallback rate。
- failed trace case list。

新增 bounded ReAct eval cases：

```text
Search -> booking_search_ready handoff
Search no result -> no booking handoff
Cancel request missing ticket -> clarification
Cancel preview -> no direct cancellation
Staff route + review analysis -> combined answer
Customer staff-tool request -> denied
```

#### P4.1 Completion Status

Agent Eval Upgrade 已实现：

- 新增多步任务成功率、工具顺序准确率、越权拒绝率、confirmation gate 命中率、fallback rate 和指标分母统计。
- failed cases 包含 execution metadata、失败类型与 bounded trajectory，便于定位具体失败步骤。
- P4 场景集使用只读动态 future-ticket fixture，避免取消预览测试因固定票号过期而失效。
- Docker MySQL P4 eval：`6/6 passed`；multi-step、tool order、unauthorized rejection、confirmation gate 均为 `1.0`。
- 完整 Docker MySQL 回归：`100 passed`。

### AgentOps Dashboard / Trace Viewer

把现有 trace、metrics、trajectory 做成更清晰的调试视图：

- request_path
- runtime_mode_used
- router_used
- tools_used
- step_count
- stop_reason
- fallback_reason
- latency
- confirmation_required

这可以先是简单 HTML/debug 页面，不需要复杂前端。

#### P4.2 Completion Status

AgentOps Dashboard / Trace Viewer 已实现：

- FastAPI 新增只读 dashboard 聚合接口，可按 role、request path、runtime mode 和 outcome 筛选最近的 Agent traces。
- Staff Web 新增权限保护的 `/staff/agentops` 页面，展示 trace 数量、平均延迟、平均步数、fallback rate、错误数量和 confirmation gate 数量。
- Dashboard 同时展示当前 Agent service 的 endpoint request metrics、tool-call count 和平均延迟。
- Trace viewer 展示 request path、runtime、router、tools、step count、stop reason、fallback/error 和 bounded trajectory。
- 页面只展示简短 decision/action/observation metadata，不暴露原始 reasoning 或完整 chain-of-thought。
- 已验证桌面端、390px 移动端、筛选交互和 staff-only access；完整 Docker MySQL 回归：`106 passed`。

### P4.3 Human-in-the-loop Queue

增加面向 demo 的人工确认视图：

- pending booking handoffs / checkout starts
- pending cancellation previews
- confirmed / rejected actions
- audit trail

原则：

- LLM 可以建议动作。
- 用户或 staff 明确确认后才执行高风险动作；购票必须在 Search Flights checkout 页面完成。

#### P4.3 Completion Status

- 已实现持久化 booking handoff、checkout start、cancellation preview、确认/拒绝/过期/失败状态与逐项审计历史。
- Customer Pending Actions 仅操作本人动作；Staff Action Queue 仅查看本航司记录，不能替客户确认交易。
- 购票必须先进入 Search Flights checkout；付款提交使用 action、flight、ticket-id allocator 行锁，重复提交返回同一票号，最后一个座位不能超售。
- 取消确认绑定原始 preview；退款条件改变或预览过期时停止执行。交易结果与审计记录同事务提交。
- 付款仅保存 `MOCK-PAYMENT`，不存用户输入的卡号。
- 离线回归 `90 passed, 23 skipped`；Docker MySQL 全量回归 `113 passed`。

### P4.4 Governance / Safety Hardening

补充企业级 Agent 边界说明和实现：

- tool risk category
- role-based tool permission
- transaction guardrails
- audit log
- unsupported request refusal
- no direct SQL from LLM
- no real payment / no real airline inventory

#### P4.4 Completion Status

- FastAPI `/api/*` requests require a short-lived signed service identity and enforce customer, staff, and operator scopes, including airline isolation for dashboards.
- Flask sessions use a persistent restrictive-permission secret, secure cookie flags, and session-bound CSRF tokens on every state-changing form.
- High-risk model tools are blocked from direct registry execution; booking confirmation over HTTP is retired with `410 Gone` and purchase remains a user-driven checkout flow.
- Trace and dashboard responses redact customer content from staff views while retaining operational metadata and auditability.
- Pydantic request bounds, evaluation suite validation, and controlled action errors provide explicit failure behavior at service boundaries.

### P4.5 Final Product Polish

- Customer flight search accepts IATA codes and supported English or Chinese city names, including the complete 24-airport synthetic catalog and legacy `BEI`/`PEK` and `HKG`/`HKA` code variants.
- The search tool can also match city names directly against the `Airport` table, so routed tool calls are not restricted to IATA-only input.
- Chinese relative periods (`下个月`, `今年`, `明年`) preserve the same date-window behavior as their English equivalents.
- Customer Agent and Staff Copilot use a single full-width conversation panel; wide result tables scroll within their message card, and the development-oriented Demo prompts panels have been removed.
- Final verification: local regression `110 passed, 24 skipped`; Docker MySQL full regression `134 passed`; Playwright confirmed the Chinese `旧金山` to `洛杉矶` flow returns `SFO` to `LAX` inventory and both Agent pages render without Demo prompts.

### Time Governance and Dynamic User Timezone

统一系统内部时间语义，同时允许用户跨时区使用，不把应用永久固定在开发者当前所在地。

目标设计：

```text
Backend / MySQL canonical time
-> store and compare timestamps in UTC
-> detect or accept the user's IANA timezone
-> convert timestamps only for display and user-entered local dates
```

要求：

- 后端、Agent service、Docker 和 MySQL 使用 UTC 作为内部标准时间。
- 数据库存储和时间比较使用 timezone-aware UTC timestamps，逐步替换无时区的 `datetime.now()` / `date.today()` 假设。
- 前端通过浏览器检测当前 IANA timezone，例如 `America/New_York` 或 `Asia/Shanghai`，并允许用户覆盖。
- 航班时间保留出发机场和到达机场的当地时区语义，避免把航班当地时间误认为用户当前时区。
- `this month`、`this year` 和报表边界必须明确使用业务配置时区，而不是随开发者电脑时区变化。
- trace 和 audit log 使用 UTC；用户页面展示转换后的本地时间和时区标识。
- Docker 默认启动时各服务必须具有一致、可验证的时区配置。

#### Time Governance Completion Status

- MySQL sessions, Python services, Docker containers, trace export, and action audit timestamps use UTC; `/health` reports both Python and MySQL clocks.
- Flight input accepts airport-local wall times, rejects DST gaps and unresolved ambiguous times, and displays airport and traveler zones separately.
- Browser timezone detection plus `/preferences/timezone` allows a persisted IANA override; date searches and reports use DST-aware UTC bounds.
- `this month`, `this year`, and custom report ranges are anchored to `BUSINESS_TIMEZONE`, independent of the host machine timezone.
- P4 security/timezone tests pass in the local deterministic suite; MySQL transaction and clock tests remain enabled for the Docker acceptance command.

## Test Plan

P3.1 必须先通过：

- `single_step` 模式下现有 P0/P1/P2 测试不回归。
- `bounded_react` 模式下，订票准备 flow 至少调用 `search_flights`，然后返回 `booking_search_ready`。
- 无可购航班时，不返回 booking handoff，也不创建 booking intent。
- `MAX_AGENT_STEPS` 能阻止循环失控。
- bounded loop 中 `create_booking_intent` / `confirm_booking` 不会被 customer chat 执行。
- bounded loop 中 `cancel_customer_ticket` 在 P3.1 被拒绝或转 clarification。
- customer 不能调用 staff tools。
- trace 包含 `decision_summary`、`action`、`observation`、`stop_reason`，不包含完整 chain-of-thought。
- native/json/deterministic router fallback 仍然可用。
- Docker MySQL 完整测试继续通过。

P3.2 必须补充：

- ticket missing -> clarification。
- ticket found -> refund preview。
- ON_TIME / DELAYED refund fee rules 正确。
- cancellation preview 不直接修改 ticket 状态。
- 只有确认动作才执行真正取消。

P3.3 必须补充：

- staff multi-tool sequence 正确。
- staff answer 只基于工具 observation。
- customer 越权请求被拒绝。

P4 必须补充：

- eval report 可输出 summary metrics。
- trace viewer 能展示 bounded ReAct steps。
- human-in-the-loop queue 能列出 pending actions。
- UTC 存储和跨时区显示测试通过，Python、MySQL 与 Docker 的时间边界一致。
- `this month` / `this year` 报表在配置业务时区下不会因用户旅行或容器时区改变而漂移。
- 航班出发/到达时间能按机场当地时区和用户显示时区正确转换。
- README 更新为项目文档，不写面试话术。

## Assumptions

- P3.1/P3.2/P3.3/P3.4 是当前已实施的 P3 vertical slices；后续 P3 工作应继续保持小步验证。
- P3 不追求无限 autonomous agent，而是 bounded autonomous multi-step Agent。
- P3 默认仍可保持 `single_step`，`auto` 作为显式可选模式，避免 demo 行为漂移。
- LLM/native tool calling 只负责选择工具和组织回答，业务执行仍由后端工具负责。
- Customer Agent 不执行购票；购票只能通过 Search Flights 页面由用户手动 review flight 并提交 payment 信息。
- `cancel_customer_ticket` 这类高风险动作必须 confirmation-gated。
- 不实现真实支付、真实航司 API、真实 SFT、真实 Agentic RL。
- P4 在 P3 稳定并测试通过后再开始。
