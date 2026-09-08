"""Read persisted OMP messages without interpreting tool calls as successes."""

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path


def _error(line: int, detail: str) -> ValueError:
    return ValueError(f"OMP line {line}: {detail}")


def _timestamp(record: dict, line: int) -> datetime:
    value = record.get("timestamp")
    if not isinstance(value, str):
        raise _error(line, "missing or invalid record timestamp")
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        raise _error(line, "invalid record timestamp") from None
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise _error(line, "record timestamp has no timezone")
    return stamp


def _reject_constant(value: str) -> None:
    raise ValueError("invalid JSON constant")


def _content(message: dict, line: int) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        raise _error(line, "message content must be text or a block list")
    parts = []
    for block in content:
        if not isinstance(block, dict) or not isinstance(block.get("type"), str):
            raise _error(line, "invalid content block")
        kind = block["type"]
        if kind == "text":
            if not isinstance(block.get("text"), str):
                raise _error(line, "invalid text block")
            parts.append(block["text"])
        elif kind == "toolCall":
            if message["role"] != "assistant":
                raise _error(line, "tool call outside assistant message")
            name = block.get("name")
            arguments = block.get("arguments")
            if not isinstance(name, str) or not name or not isinstance(arguments, dict):
                raise _error(line, "invalid tool call name or arguments")
            parts.append(
                "工具调用（不代表成功）: " + name + "\n参数: "
                + json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
            )
        elif kind not in {"thinking", "image"}:
            raise _error(line, "unsupported content block type")
    return "\n".join(parts)


def iter_messages(path: Path) -> Iterator[dict]:
    """Yield user, assistant and tool messages in physical JSONL order.

    A leading ``title`` record is allowed before the required ``session``
    header. Non-message records after that header are metadata and are not
    emitted; in particular, compaction and branch summaries are never replayed.
    Only top-level, timezone-bearing persistence timestamps are accepted.
    """
    header_seen = False
    line_number = 0
    try:
        with path.open("r", encoding="utf-8-sig") as stream:
            for line_number, raw in enumerate(stream, 1):
                if not raw.strip():
                    continue
                try:
                    record = json.loads(raw, parse_constant=_reject_constant)
                except (ValueError, RecursionError):
                    raise _error(line_number, "invalid JSON") from None
                if not isinstance(record, dict) or not isinstance(record.get("type"), str):
                    raise _error(line_number, "invalid record envelope")
                kind = record["type"]
                if kind == "session":
                    if header_seen:
                        raise _error(line_number, "duplicate session header")
                    if (
                        type(record.get("version")) is not int
                        or not isinstance(record.get("id"), str)
                        or not record["id"]
                        or not isinstance(record.get("cwd"), str)
                    ):
                        raise _error(line_number, "invalid session header")
                    _timestamp(record, line_number)
                    header_seen = True
                    continue
                if not header_seen:
                    if kind == "title" and isinstance(record.get("title"), str):
                        continue
                    raise _error(line_number, "record encountered before session header")
                if kind != "message":
                    continue
                message = record.get("message")
                if not isinstance(message, dict) or not isinstance(message.get("role"), str):
                    raise _error(line_number, "invalid message envelope")
                role = message["role"]
                if role in {"system", "developer", "compactionSummary", "branchSummary"}:
                    continue
                if role not in {"user", "assistant", "toolResult"}:
                    raise _error(line_number, "unsupported message role")
                stamp = _timestamp(record, line_number)
                text = _content(message, line_number)
                result = {
                    "timestamp": stamp,
                    "role": "tool" if role == "toolResult" else role,
                    "text": text,
                }
                if role == "toolResult":
                    name = message.get("toolName")
                    is_error = message.get("isError")
                    if not isinstance(name, str) or not name or not isinstance(is_error, bool):
                        raise _error(line_number, "invalid tool result metadata")
                    result["tool_name"] = name
                    result["is_error"] = is_error
                if text or role == "toolResult":
                    yield result
    except UnicodeError:
        raise _error(line_number + 1, "invalid UTF-8 input") from None
    if not header_seen:
        raise _error(max(line_number, 1), "missing session header")
