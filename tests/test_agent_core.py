from agent_service.rag import PolicyRAG
from agent_service.tool_registry import Tool, ToolAccessError, ToolRegistry


def test_tool_registry_blocks_wrong_role():
    registry = ToolRegistry()
    registry.register(Tool("staff_only", "demo", ["staff"], lambda: {"ok": True}))

    try:
        registry.call("customer", "staff_only")
    except ToolAccessError:
        return

    raise AssertionError("customer role should not call staff-only tools")


def test_policy_rag_returns_citation_for_refund_question(tmp_path):
    policy = tmp_path / "policy.md"
    policy.write_text(
        "# Policy\n\n## Refund Policy\nCancelled flights are refundable in the demo system.\n",
        encoding="utf-8",
    )
    rag = PolicyRAG(str(policy))
    result = rag.query("Can I get a refund for a cancelled flight?")

    assert result["citations"]
    assert "refundable" in result["answer"].lower()

