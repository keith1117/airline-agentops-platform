import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Set

from .config import settings as default_settings
from .db import ensure_agent_schema
from .qa_harness import generate_agent_qa_cases, run_agent_qa
from .rag import PolicyRAG
from .react_agent import ReActAgent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run randomized Agent QA checks for customer and staff agents.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=24)
    parser.add_argument("--report-dir", default="logs/agent_qa_runs")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--tool-router-mode", choices=["auto", "native", "json", "deterministic"], default=None)
    parser.add_argument("--agent-router-mode", choices=["auto", "deterministic", "llm"], default=None)
    parser.add_argument("--runtime-mode", choices=["single_step", "bounded_react"], default=None)
    parser.add_argument("--rag-retriever-mode", choices=["auto", "keyword", "embedding"], default=None)
    parser.add_argument("--policy-answer-mode", choices=["auto", "extractive", "llm"], default=None)
    parser.add_argument("--avoid-recent", action="store_true")
    parser.add_argument("--fail-on-failures", action="store_true")
    args = parser.parse_args()

    settings = default_settings
    overrides = {}
    if args.tool_router_mode:
        overrides["tool_router_mode"] = args.tool_router_mode
    if args.agent_router_mode:
        overrides["agent_router_mode"] = args.agent_router_mode
    if args.runtime_mode:
        overrides["agent_runtime_mode"] = args.runtime_mode
    if args.rag_retriever_mode:
        overrides["rag_retriever_mode"] = args.rag_retriever_mode
    if args.policy_answer_mode:
        overrides["policy_answer_mode"] = args.policy_answer_mode
    if overrides:
        settings = replace(settings, **overrides)

    report_dir = Path(args.report_dir)
    recent_prompts = _load_recent_prompts(report_dir) if args.avoid_recent else set()
    cases = generate_agent_qa_cases(seed=args.seed, count=args.count, recent_prompts=recent_prompts)

    ensure_agent_schema()
    rag = PolicyRAG(settings.rag_policy_path, settings=settings)
    agent = ReActAgent(rag, settings=settings)
    summary = run_agent_qa(agent, cases, report_dir=report_dir, run_id=args.run_id)
    printable = {key: value for key, value in summary.items() if key not in {"results", "failed_cases"}}
    print(json.dumps(printable, indent=2, ensure_ascii=False))
    if summary["failed_cases"]:
        print(f"Failed cases written to {summary['report_path']}")
    if args.fail_on_failures and summary["failed"]:
        raise SystemExit(1)


def _load_recent_prompts(report_dir: Path, max_files: int = 10) -> Set[str]:
    prompts: Set[str] = set()
    if not report_dir.exists():
        return prompts
    case_files = sorted(report_dir.glob("agent_qa_*_cases.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in case_files[:max_files]:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("message"):
                prompts.add(row["message"])
    return prompts


if __name__ == "__main__":
    main()
