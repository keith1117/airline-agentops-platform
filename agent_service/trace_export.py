import json
from pathlib import Path
from typing import Dict, Optional

from .db import get_conn
from .timezones import utc_iso


def export_traces(
    output_path: str = "eval/sft_ready_traces.jsonl",
    session_prefix: Optional[str] = None,
) -> Dict[str, object]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            sql = """
            SELECT session_id, role, principal, user_message, reasoning,
                   tool_calls, final_answer, created_at
            FROM agent_traces
            """
            args = []
            if session_prefix:
                sql += " WHERE session_id LIKE %s"
                args.append(f"{session_prefix}%")
            sql += " ORDER BY id"
            cur.execute(sql, tuple(args))
            rows = cur.fetchall()
    finally:
        conn.close()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    exported = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            tool_calls = json.loads(row["tool_calls"] or "[]")
            execution = _parse_execution(row["reasoning"] or "")
            fh.write(
                json.dumps(
                    {
                        "messages": [
                            {"role": "user", "content": row["user_message"]},
                            {"role": "assistant", "content": row["reasoning"] or ""},
                            {"role": "tool", "content": json.dumps(tool_calls, ensure_ascii=False)},
                            {"role": "assistant", "content": row["final_answer"] or ""},
                        ],
                        "metadata": {
                            "session_id": row["session_id"],
                            "role": row["role"],
                            "principal": row["principal"],
                            "tool_names": [call.get("name") for call in tool_calls],
                            "execution": execution,
                            "trajectory": execution.get("trajectory", []),
                            "created_at": utc_iso(row["created_at"]),
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            exported += 1
    return {"output_path": str(path), "exported": exported, "session_prefix": session_prefix}


def _parse_execution(reasoning: str) -> Dict[str, object]:
    marker = "\nexecution: "
    if marker not in reasoning:
        return {}
    try:
        return json.loads(reasoning.split(marker, 1)[1])
    except json.JSONDecodeError:
        return {}
