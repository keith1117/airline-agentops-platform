# Live Model Evaluation Record

[English](live-model-evaluation.md) | [简体中文](<live-model-evaluation(Chinese).md>)

## Scope

On September 21, 2026, the Agent was evaluated against Docker MySQL with `gpt-4o-mini`, `text-embedding-3-small`, forced native tool routing, forced embedding retrieval, and forced grounded LLM policy answers. Synthetic prompts, synthetic account and flight fields, and retrieved policy excerpts were sent to the configured OpenAI API with user authorization.

The evaluation separates live model behavior from deterministic governance. A trajectory counts as a live path only when its execution metadata records `router_used=native`, or both `retriever_used=embedding` and `answer_mode_used=llm`. Booking confirmation, cancellation gating, and some scope checks intentionally remain deterministic backend controls.

## Method

- The 23-case default suite ran three times, producing 69 main trajectories plus setup calls for memory cases.
- The six-case P4 governance suite ran three times, producing 18 trajectories.
- Each case checked expected and forbidden tools, tool arguments, required keywords, citations, request path, pending handoff state, and fallback behavior as applicable.
- P4 cases additionally checked multi-step success, tool order, unauthorized-call rejection, and confirmation gates.
- Latency is nearest-rank P50/P95 over serial main trajectories and includes local application, MySQL, network, and provider time.
- Token usage and estimated cost were not recorded because the current client does not persist provider usage fields.

Reproduce the default run:

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

## Diagnostic Run and Fixes

The first full live diagnostic passed `18/23` cases. It found one stale-data fixture and four live-path integration defects:

- The trips case used a fixed customer who no longer had a future ticket.
- The native preference-save response did not expose the saved fields expected by the product contract.
- A route-omitted native flight search skipped stored preferences.
- Native staff load-factor output used a generic heading.
- A staff booking request was misrouted to a staff analytics tool instead of being rejected at the role boundary.

The fixture now selects a customer with a future ticket. Native search applies stored preferences, native output uses the product formatters, staff booking requests are rejected before model routing, and no-tool live plans record `scope_fallback`. Focused regressions cover these paths.

## Final Results

| Suite | Result | Live-path coverage | Quality and governance | Serial latency |
| --- | --- | --- | --- | --- |
| Default, 3 × 23 | `69/69` | `51/69` live paths; `51/51` passed | Tool-call accuracy `1.0`; citation presence `1.0`; citation grounding `1.0`; fallback `0.0` | P50 `1.19 s`; P95 `2.16 s`; max `2.60 s` |
| P4 governance, 3 × 6 | `18/18` | `3/18` native-router denial paths; `3/3` passed | Multi-step success `1.0`; tool order `1.0`; unauthorized rejection `1.0`; confirmation gate `1.0`; fallback `0.0` | P50 `19 ms`; P95/max `1.69 s` |

The same revision passed the fast deterministic regression with `113 passed, 24 skipped` and the full Docker MySQL regression with `138 passed`. Live-model latency is provider-dependent and is not a throughput benchmark or production service-level objective. The separate deterministic Locust run remains the reproducible backend load result.
