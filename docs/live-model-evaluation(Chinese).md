# 真实模型评测记录

[English](live-model-evaluation.md) | [简体中文](<live-model-evaluation(Chinese).md>)

## 范围

2026 年 9 月 21 日，Agent 在 Docker MySQL 环境中使用 `gpt-4o-mini`、`text-embedding-3-small`、强制 native tool routing、强制 embedding retrieval 和强制 grounded LLM policy answer 完成评测。经用户授权，合成提示、合成账号与航班字段以及检索到的政策片段被发送至已配置的 OpenAI API。

评测将真实模型行为与确定性治理分开统计。只有 execution metadata 记录 `router_used=native`，或者同时记录 `retriever_used=embedding` 与 `answer_mode_used=llm` 的 trajectory 才计入 live path。购票确认、取消门禁和部分 scope 检查按设计继续由确定性后端控制。

## 方法

- 23-case default suite 运行三轮，生成 69 个主 trajectory，另有 memory cases 的 setup calls。
- 6-case P4 governance suite 运行三轮，生成 18 个 trajectory。
- 每个 case 按适用范围检查 expected/forbidden tools、tool arguments、required keywords、citation、request path、pending handoff state 和 fallback behavior。
- P4 cases 额外检查 multi-step success、tool order、unauthorized-call rejection 和 confirmation gate。
- 延迟使用串行主 trajectory 的 nearest-rank P50/P95，包含本地应用、MySQL、网络和供应商处理时间。
- 当前 client 不持久化供应商 usage 字段，因此没有记录 token usage 和估算成本。

复现 default run：

```bash
mkdir -p logs/live_model_eval
docker compose run --rm -T \
  -v "$PWD/logs/live_model_eval:/app/logs/live_model_eval" \
  -e TOOL_ROUTER_MODE=native \
  -e RAG_RETRIEVER_MODE=embedding \
  -e POLICY_ANSWER_MODE=llm \
  agent python -m scripts.run_live_model_eval \
  --suite default --repeats 3
```

## 诊断与修复

首次完整 live diagnostic 通过 `18/23` cases，发现一个数据 fixture 漂移和四个 live-path integration defects：

- Trips case 使用的固定 customer 已经没有未来机票。
- Native preference-save response 没有展示产品契约所要求的已保存字段。
- 未提供 route 的 native flight search 没有读取已保存偏好。
- Native staff load-factor 输出使用了泛化标题。
- Staff booking request 被错误路由到 staff analytics tool，没有在角色边界直接拒绝。

现在 fixture 会动态选择拥有未来机票的 customer；native search 会应用保存的偏好；native output 使用产品 formatter；staff booking request 在模型路由前被拒绝；无工具 live plan 会记录 `scope_fallback`。这些路径均已增加专项回归。

## 最终结果

| Suite | 结果 | Live-path 覆盖 | 质量与治理 | 串行延迟 |
| --- | --- | --- | --- | --- |
| Default，3 × 23 | `69/69` | `51/69` live paths；`51/51` 通过 | Tool-call accuracy `1.0`；citation presence `1.0`；citation grounding `1.0`；fallback `0.0` | P50 `1.19 s`；P95 `2.16 s`；max `2.60 s` |
| P4 governance，3 × 6 | `18/18` | `3/18` native-router denial paths；`3/3` 通过 | Multi-step success `1.0`；tool order `1.0`；unauthorized rejection `1.0`；confirmation gate `1.0`；fallback `0.0` | P50 `19 ms`；P95/max `1.69 s` |

同一 revision 的快速 deterministic regression 为 `113 passed, 24 skipped`，Docker MySQL 完整回归为 `138 passed`。真实模型延迟受供应商影响，不属于吞吐 benchmark，也不代表生产服务等级目标。可复现的后端负载结果仍来自单独的 deterministic Locust run。
