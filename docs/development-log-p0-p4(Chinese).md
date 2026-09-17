# Airline AgentOps Platform：P0–P4 完整开发日志

[English](development-log-p0-p4.md) | [中文](<development-log-p0-p4(Chinese).md>)

## 文档信息

| 项目 | 内容 |
| --- | --- |
| 开发状态 | P0–P4 已全部完成 |
| 实施周期 | 2026-05-30 至 2026-09-12 |
| 最终验收日期 | 2026-09-12 |
| 当前基线 | `main` 与 `codex/p4-agentops-governance` 的 P0–P4 完成版本 |
| 系统边界 | 合成航空库存、模拟支付、本地 Docker 演示环境 |

本文档整合 P0–P4 的阶段目标、实施内容、关键决策、阶段验收与最终复验数据。阶段数字代表当时的验收快照；项目当前状态以“最终综合验收”中的数据为准。

## 阶段总览

| 阶段 | 核心目标 | 主要交付物 | 阶段验收 |
| --- | --- | --- | --- |
| P0 | 将传统 Flask/MySQL 航空系统升级为可演示的 Agent MVP | FastAPI Agent、受控工具、RAG、Customer Agent、Staff Copilot、trace、模拟确认 | MySQL acceptance `8 passed`，客户与员工 Agent 浏览器流程通过 |
| P1 | 增加个性化记忆、可量化 eval、trajectory export 与可复现运行环境 | 用户偏好、20-case eval、SFT-ready JSONL、核心回归、Docker Compose | 初始 eval `20/20`，P0/P1 acceptance `22 passed`，Docker 四服务联通 |
| P2 | 建立可观测性、负载验证和可扩展合成数据能力 | Metrics API/JSONL、Locust、10k-flight generator、curated demo seed | 最终 20-user smoke：`2813` 请求、`0` 失败、P95 `33 ms`、`47.17 req/s` |
| P3 | 将 single-step routing 扩展为有边界的多步 ReAct runtime | Booking preparation、取消预览、员工多工具分析、auto runtime、QA harness | 专项回归 `23 passed`；工具顺序、步数限制、权限和 stop reason 通过 |
| P4 | 完成 eval、AgentOps、持久人工确认、安全、时区和产品收尾 | Eval metrics、dashboard、action queue、原子 checkout、signed identity、CSRF、UTC/IANA、城市查询 | 最终本地回归 `110 passed, 24 skipped`；Docker MySQL 回归 `134 passed` |

## P0：Agent MVP 基础

### 阶段目标

- 保留原有 Flask/MySQL 航班、客户、员工、机票和评价业务。
- 新增独立 FastAPI Agent 服务，避免把 Agent 逻辑直接耦合进 Web route。
- 使用注册工具访问业务数据，禁止模型直接执行 SQL。
- 为客户提供航班查询、行程查询、政策问答和安全购票准备能力。
- 为航司员工提供销售、评价、客座率和航线分析能力。
- 使用 RAG 返回有来源的政策回答，并记录 Agent trace。
- 通过真实 MySQL acceptance，而不只依赖 mock。

### 实施结果

- 建立 Flask Web → FastAPI Agent → Tool Registry → MySQL 的双服务结构。
- 新增 `/customer/agent` 与 `/staff/copilot` 页面。
- 注册客户工具：航班、行程、机票、政策和购票相关操作。
- 注册员工工具：销售报表、评价分析、客座率、航线表现和政策查询。
- 建立 Markdown 航空政策知识库和 citation 返回格式。
- 新增 `agent_sessions`、`agent_traces`、`booking_intents` 和 `user_preferences` 等 Agent 数据结构。
- 增加最小未来航班 seed，解决原始演示数据随时间过期的问题。
- Flask 调用 Agent 时关闭环境代理继承，解决 localhost 请求被外部代理影响的问题。
- 将 MySQL 连接调整为延迟建立，保证应用在数据库尚未就绪时仍可正常 import。

### P0.5 展示层整理

- 重构公共导航、首页航班搜索、登录注册、客户页面、员工后台和 Agent 对话布局。
- 使用统一卡片、表格、状态标签与响应式样式。
- 增加模板 smoke tests；阶段验收为 `4 passed`，后续随功能增长纳入完整 UI 回归。

### 阶段验收

| 验收项 | 结果 |
| --- | --- |
| P0 MySQL acceptance | `8 passed` |
| Customer Agent | 航班查询、RAG citation、购票确认入口通过 |
| Staff Copilot | 员工分析工具和表格结果通过 |
| 权限隔离 | Customer 无法调用 staff-only tools；Staff 不执行客户购票工具 |
| Agent 健康检查 | Flask 与 FastAPI 联通，数据库和政策知识库可用 |

### 主要提交

- `ed552a2` — Baseline P0/P1/P0.5 Agent platform

## P1：Memory、Eval 与 Trace Export

### 阶段目标

- 让客户保存常用航线、航司和预算偏好，并在后续查询缺少参数时自动应用。
- 建立 deterministic Agent eval，量化 task success、tool accuracy、citation 和 steps。
- 将成功和失败 trajectory 导出为可供未来训练筛选的 JSONL。
- 增加核心回归，覆盖 RAG fallback、幂等购票和退款规则。
- 用 Docker Compose 固化 MySQL、seed、Agent 与 Flask 的运行环境。

### 实施结果

- `remember_user_preference` 与 `get_user_preferences` 完成持久化记忆闭环。
- 建立 JSONL eval suite，并检查 expected tools、forbidden tools、答案关键字和 citation presence。
- Eval 输出 total、passed、task success rate、tool-call accuracy、citation rate、average steps 和 failed cases。
- Trace export 输出 `user → assistant decision summary → tool → assistant final` 格式，并携带 session、role、principal 和 tool metadata。
- Docker Compose 提供 MySQL 8、一次性 seed、FastAPI Agent、Flask Web 和 phpMyAdmin。

### 阶段验收

| 验收项 | 结果 |
| --- | --- |
| 初始 deterministic eval | `20/20 passed` |
| Task success rate | `1.0` |
| Tool-call accuracy | `1.0` |
| Citation presence rate | `1.0` |
| Average steps | `1.1` |
| P0/P1 acceptance | `22 passed` |
| Docker runtime | MySQL、seed、Agent、Web 均成功运行；Web `5050`、Agent `8001` 可访问 |

说明：P1 的 20-case eval 是阶段快照；最终 eval 已扩展为 23 个用例，见最终综合验收。

## P2：Observability、Load 与 Synthetic Data

### 阶段目标

- 对 FastAPI Agent 请求增加低开销 metrics，不改变工具和业务行为。
- 建立可重复执行的小规模 Locust smoke workload。
- 生成大规模但可区分、可重复、保持外键完整性的合成数据。
- 给出可核验的延迟、错误率和数据规模，不声明生产级容量。

### 实施结果

- 增加内存 metrics collector 和 `logs/agent_metrics.jsonl` 事件日志。
- `GET /api/metrics` 汇总请求数、延迟、角色、工具调用和错误数。
- Locust 覆盖客户航班查询、客户政策问答、员工评价分析、员工销售报表和 metrics polling。
- 合成数据生成器默认只写 SQL；仅使用 `--apply` 时修改 MySQL。
- 生成数据使用 `SyntheticAir`、`SYN` 前缀和独立 demo email，避免覆盖稳定演示数据。
- 新增较小的专业演示 seed，保持主数据库适合人工演示。

### 数据规模

| 数据集 | Airport | Flight | Customer | Ticket | Review |
| --- | ---: | ---: | ---: | ---: | ---: |
| 默认 synthetic generator | 24 | 10,000 | 2,000 | 50,000 | 5,000 |
| 小型 generator smoke | 5 | 12 | 8 | 20 | 6 |
| Curated Docker demo seed | 12 | 60 | 20 | 90 | 45 |

### 负载验收

初次开发 smoke 使用 2 users/10s，验证 workload 能运行；P4 收尾阶段使用当前鉴权配置重新执行 20 users/1m，作为最终数据：

| 场景 | 请求数 | 失败数 | 平均延迟 | P95 |
| --- | ---: | ---: | ---: | ---: |
| Customer flight search | 563 | 0 | 26 ms | 45 ms |
| Customer policy QA | 563 | 0 | 12 ms | 19 ms |
| Staff review analytics | 563 | 0 | 21 ms | 33 ms |
| Staff sales report | 562 | 0 | 18 ms | 28 ms |
| Metrics polling | 562 | 0 | 1 ms | 2 ms |
| **总计** | **2813** | **0** | **16 ms** | **33 ms** |

- 用户数：`20`
- 运行时间：`1m`
- Spawn rate：`5 users/s`
- 吞吐量：`47.17 requests/s`
- 失败率：`0%`
- Agent metrics 复核：`2813` requests、`0` errors、service average `14.39 ms`

该数据是本地 Docker smoke benchmark，用于回归和演示，不是生产 SLA 或容量承诺。

### 主要提交

- `34f1155` — Complete P2 Agent observability and benchmarks
- `302cbdb` — Refresh demo seed and Agent fallback copy
- `bab7fee` — Prepare project for public GitHub release

## P3：Bounded ReAct Agent

### 阶段目标

- 在稳定 single-step flow 之外提供 observation-driven 多步执行。
- 使用 `MAX_AGENT_STEPS`、角色权限和工具风险阻止无限循环与越权操作。
- 让 Agent 可以准备购票和取消，但不能在普通 chat 中完成高风险交易。
- 让 Staff Copilot 能组合多个后端 observation，而不是依靠模型猜测业务数据。
- 保留 native、JSON 与 deterministic router 的可控 fallback。

### P3.1 Booking Preparation

- 搜索可购买航班并观察返回结果。
- 根据用户约束选择最低价或指定航班。
- 多个候选且选择不明确时要求用户指定 flight number 和 departure time。
- 以 `booking_search_ready` 停止，展示 **Book** 并跳转 Search Flights checkout。
- 对话不调用 `confirm_booking`，也不直接签发 Ticket。

### P3.2 Cancellation Preview

- 缺少 ticket ID 时进入 clarification。
- 查询属于当前客户的 ticket，按状态计算费用和预计退款。
- 以 `cancellation_confirmation_required` 停止。
- 普通 chat 不调用 `cancel_customer_ticket`；实际取消交给独立确认操作。

### P3.3 Staff Multi-tool Copilot

- 将 `get_route_performance` 与 `analyze_reviews` 组合为多工具分析。
- 按相同 departure/arrival route 关联销售与评价，避免把无关低评分航班错误归入高销售航线。
- 纯评价问题仅使用 review analytics，并按用户要求的方向排序。

### P3.4 Auto Runtime 与稳定性修复

- `AGENT_RUNTIME_MODE=auto` 在 simple single-step 和 bounded multi-step 之间选择。
- 增加 month/year/relative-date 查询、字母数字 flight number、active-trip 边界和报表时间窗口。
- Agent QA harness 使用 seeded prompt variants 检查 expected/forbidden tools、citation、confirmation 和 request path。
- Trace 记录 decision summary、action、observation、stop reason 和 step count，不保存完整 chain-of-thought。

### 阶段验收

| 验收项 | 结果 |
| --- | --- |
| P3 bounded runtime tests | `23 passed` |
| Booking preparation | Search → observation → selection → checkout handoff 通过 |
| No-result/ambiguous selection | 不创建错误 handoff；返回无结果或 clarification |
| Cancellation | Preview 不修改 ticket；确认工具不会被普通 chat 执行 |
| Staff multi-tool | 工具顺序、route correlation 和 role boundary 通过 |
| Step/trace governance | 最大步数、stop reason、trajectory metadata 通过 |

### 主要提交

- `1f54aea` — Add bounded AgentOps runtime
- `6dc3414` — Add cancellation preview flow
- `d4b4485` — Route Agent booking to Search Flights checkout
- `ef05c8e` — Add bounded Staff Copilot flow
- `51b737a` — Add runtime auto mode
- `6d79eed` — Add Agent QA harness
- `2d3c3d7`、`788e385`、`165c75d` — Trip、report 与 route-review correctness fixes

## P4：Evaluation、AgentOps、HITL 与 Governance

### 阶段目标

- 将多步任务、工具顺序、越权拒绝和 confirmation gate 纳入 Agent eval。
- 为 trace、metrics 和 bounded trajectory 提供员工可视化页面。
- 使用持久化 action queue 统一 booking handoff 与 cancellation decision。
- 强化服务身份、CSRF、角色与航司隔离、事务和敏感内容边界。
- 统一 UTC 存储、业务时区边界和机场/旅客 IANA 时区显示。
- 完成城市名称查询、Agent UI 和 payment copy 等最终产品收尾。

### P4.1 Agent Eval Upgrade

- 增加 multi-step success、tool sequence accuracy、unauthorized rejection、confirmation gate 和 fallback rate。
- Failed case 保存 execution metadata、failure type 和 bounded trajectory。
- 使用动态 future-ticket fixture，避免固定票号或日期过期导致 eval 漂移。

阶段结果：P4 eval `6/6 passed`；multi-step、tool order、unauthorized rejection 和 confirmation gate 均为 `1.0`；当时完整 Docker 回归为 `100 passed`。

### P4.2 AgentOps Dashboard

- FastAPI 增加只读 dashboard 聚合接口，可按 role、request path、runtime mode 和 outcome 筛选。
- `/staff/agentops` 展示 trace 数、平均延迟、平均步数、fallback rate、errors 和 confirmation gates。
- Trace viewer 展示工具、stop reason、运行模式和 bounded trajectory，同时隐藏完整 reasoning。
- Staff view 隐藏客户 request/response 正文，只保留运行元数据。

阶段结果：权限、筛选、桌面与移动布局通过；当时完整 Docker 回归为 `106 passed`。

### P4.3 Persistent Human-in-the-loop Queue

- Booking handoff 和 cancellation preview 使用 durable action ID，默认 30 分钟过期。
- 每个 pending、confirmed、rejected、expired、failed 状态均写入 audit event。
- Customer Pending Actions 仅能操作本人 action；Staff Action Queue 仅能查看本航司 action，不能代客户确认。
- Checkout 使用 action/flight/allocator 行锁、票价和 preview 校验、最后座位保护及幂等 ticket result。
- Cancellation confirmation 绑定原始 preview；规则变化或 preview 过期时停止执行。
- 用户输入卡号仅校验 13–19 位数字，数据库只保存 `MOCK-PAYMENT`。

阶段结果：离线回归 `90 passed, 23 skipped`；当时 Docker MySQL 回归 `113 passed`。

### P4.4 Governance、Security 与 Timezone

- 所有 FastAPI `/api/*` 需要短时 signed service identity；customer、staff、operator 权限分离。
- Principal 和 airline scope 在服务端独立验证。
- Flask state-changing forms 使用 session-bound CSRF token；共享 secret 以限制权限持久化。
- Tool risk 分为 `safe_read`、`controlled_write`、`human_confirmed`；高风险工具不能由模型直接执行。
- 旧 direct booking API 返回 `410 Gone`，购买只能在 Search Flights checkout 完成。
- MySQL session、Python service、Docker、trace 和 audit 使用 UTC。
- 航班输入按机场 local wall time 解析，拒绝 DST gap 与未消解的 ambiguous time。
- 浏览器检测并允许覆盖 IANA timezone；页面同时显示机场当地时间与旅客时间。
- `this month`、`this year` 和自定义报表范围锚定 `BUSINESS_TIMEZONE`。

### P4.5 Final Product Polish

- 航班查询接受完整 24-airport catalog 的 IATA、中英文城市名称和兼容 code variant。
- Tool 也可直接使用 `Airport` 表中的城市名，不再要求用户必须输入 IATA。
- 支持中文相对时间：`下个月`、`今年`、`明年`。
- Customer Agent 与 Staff Copilot 改为全宽单列 conversation panel，移除 Demo prompts。
- 宽结果表限制在 message/card 内滚动，避免破坏页面宽度。
- 移除 demo card number 指引；无效长度只返回 `Invalid card number` 类错误。

### P4 最终验收

| 验收项 | 结果 |
| --- | --- |
| 本地 deterministic 回归 | `110 passed, 24 skipped` |
| Docker MySQL 完整回归 | `134 passed` |
| Basic Agent eval | `23/23 passed`；tool accuracy、citation presence `1.0` |
| Deterministic QA smoke | `10 passed, 0 failed` |
| 真实 native tool calling | `search_flights` 调用通过，2 条返回航班逐条匹配数据库 |
| Embedding RAG / policy LLM | Embedding retrieval 与 grounded LLM answer 通过；citation 全部属于知识库 chunk |
| API failure fallback | Native/embedding API 不可用时降级到 deterministic、keyword、extractive，并保留 fallback reason 与 citation |
| 响应式 UI | Pending Actions、checkout、AgentOps 在 `1440x900` 和 `390x844` 无页面级横向溢出 |
| Time governance | UTC、IANA、DST-aware date/report boundaries 通过专项测试 |

### 主要提交

- `f2a6ad4` — Add P4 Agent evaluation metrics
- `82839d1` — Add P4 AgentOps trace dashboard
- `6af63f4` — Add persistent human confirmation queue and atomic checkout
- `f40b7f5` — Harden Agent governance and timezone handling
- `46f1031` — Support city flight search and polish Agent UI
- `6b651dc` — Remove demo payment guidance
- `e1daf4a`、`1d43244` — Record authenticated load, live-model and responsive smoke results
- `8b6c993` — Publish enterprise bilingual README

## 最终综合验收

| 类别 | 最终状态 |
| --- | --- |
| 功能范围 | P0–P4 全部完成 |
| 客户功能 | 查询、政策、memory、行程、购票 handoff、checkout、取消确认、Pending Actions |
| 员工功能 | Copilot analytics、reports、ratings、AgentOps、Action Queue |
| Agent runtime | Native/JSON/deterministic routing；single-step/bounded/auto runtime |
| 安全 | Signed identity、CSRF、role/airline isolation、tool risk、transaction guards、redaction |
| 数据与时间 | MySQL source of truth、UTC canonical storage、IANA display、DST-aware boundaries |
| 自动化测试 | 本地 `110 passed, 24 skipped`；Docker MySQL `134 passed` |
| Eval | `23/23 passed`，tool accuracy 与 citation presence `1.0` |
| 负载 | 20 users/1m，`2813` requests，`0` failures，P95 `33 ms` |
| 真实模型 | Native routing、embedding RAG、grounded answer、citation integrity 通过 |
| UI | 桌面与 390px viewport 核心 P4 页面通过 |

## 最终边界

- 系统不连接真实 GDS、NDC、航司库存或票务系统。
- 支付为 mock；不连接支付处理商，也不保存用户银行卡号。
- 默认库存、客户、机票和评价均为本地 seed 或 synthetic data。
- Embedding index 是本地 JSON cache，不是分布式 vector database。
- 已实现 eval、trace export 和 SFT-ready 数据格式，但没有执行真实 SFT 或 Agentic RL 训练。
- 当前 Docker Compose 是本地演示与验收环境，不是 production deployment specification。

## 相关文档

- [英文项目 README](../README.md)
- [中文项目 README](../README.zh-CN.md)
- [P0–P2 原始阶段记录](project_progress_report_p0.md)
- [P3/P4 设计与实施记录](<P3-P4(Chinese).md>)
- [航空政策知识库](policies/airline_policy.md)
