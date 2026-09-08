"""Read persisted Codex rollout messages without replaying mirrored events."""

from collections.abc import Iterator
from datetime import datetime
import json
from pathlib import Path


def _error(line: int, reason: str) -> ValueError:
    return ValueError(f"Codex JSONL line {line}: {reason}")


def _timestamp(record: dict, line: int) -> datetime:
    value = record.get("timestamp")
    if not isinstance(value, str):
        raise _error(line, "message timestamp is missing or invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise _error(line, "invalid message timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error(line, "message timestamp must include a timezone")
    return parsed


def _text(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _required_string(payload: dict, key: str, line: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise _error(line, f"missing or invalid {key}")
    return value


def _reject_constant(value: str) -> None:
    raise ValueError("non-JSON numeric constant")


def iter_messages(path: Path) -> Iterator[dict]:
    """Yield user, assistant and tool records, raising sanitized line errors.

    Requires a session_meta header and response_item message format. Event-only
    message rollouts are rejected at EOF; messages yielded before an error remain
    usable. Reasoning, internal roles and compacted replacement history are never
    emitted. Tool-call text describes an attempt, not evidence of success.
    """
    header_seen = False
    response_message_seen = False
    mirror_line = None
    calls: dict[str, str] = {}
    completed_calls: set[str] = set()
    line_number = 0
    with path.open("rb") as stream:
        while True:
            line_number += 1
            try:
                raw = stream.readline().decode("utf-8-sig" if line_number == 1 else "utf-8")
            except UnicodeError:
                raise _error(line_number, "invalid UTF-8 input") from None
            if not raw:
                break
            if not raw.strip():
                continue
            try:
                record = json.loads(raw, parse_constant=_reject_constant)
            except (ValueError, RecursionError):
                raise _error(line_number, "invalid JSON") from None
            if not isinstance(record, dict):
                raise _error(line_number, "record must be an object")
            kind = _required_string(record, "type", line_number)
            payload = record.get("payload")
            if not isinstance(payload, dict):
                raise _error(line_number, "payload must be an object")
            if not header_seen:
                if kind != "session_meta":
                    raise _error(line_number, "expected session_meta header")
                identifier = payload.get("id", payload.get("session_id"))
                if not isinstance(identifier, str) or not identifier:
                    raise _error(line_number, "invalid session identifier")
                _required_string(payload, "cwd", line_number)
                header_seen = True
                continue
            if kind == "session_meta":
                raise _error(line_number, "unexpected duplicate session_meta header")
            if kind in {"turn_context", "compacted", "world_state", "token_usage_record",
                        "inter_agent_communication_metadata"}:
                continue
            if kind == "event_msg":
                event = _required_string(payload, "type", line_number)
                if event in {"user_message", "agent_message"}:
                    if mirror_line is None:
                        mirror_line = line_number
                    continue
                if event != "patch_apply_end":
                    continue
                call_id = _required_string(payload, "call_id", line_number)
                if not isinstance(payload.get("success"), bool):
                    raise _error(line_number, "patch_apply_end requires boolean success")
                timestamp = _timestamp(record, line_number)
                if call_id in completed_calls:
                    continue
                yield {
                    "timestamp": timestamp,
                    "role": "tool",
                    "tool_name": calls.get(call_id, "apply_patch"),
                    "text": "patch_apply_end: " + _text(payload),
                    "is_error": not payload["success"],
                }
                continue
            if kind != "response_item":
                raise _error(line_number, "unsupported record type")
            item = _required_string(payload, "type", line_number)
            if item == "message":
                role = _required_string(payload, "role", line_number)
                if role in {"system", "developer"}:
                    continue
                if role not in {"user", "assistant"}:
                    raise _error(line_number, "unsupported message role")
                response_message_seen = True
                if role == "assistant" and payload.get("channel") == "analysis":
                    continue
                content = payload.get("content")
                if not isinstance(content, list):
                    raise _error(line_number, "message content must be a list")
                parts = []
                for part in content:
                    if not isinstance(part, dict):
                        raise _error(line_number, "message content part must be an object")
                    part_type = _required_string(part, "type", line_number)
                    if part_type in {"input_text", "output_text"}:
                        if not isinstance(part.get("text"), str):
                            raise _error(line_number, "message text must be a string")
                        parts.append(part["text"])
                    elif part_type not in {"input_image", "output_image", "image"}:
                        raise _error(line_number, "unsupported message content type")
                timestamp = _timestamp(record, line_number)
                if parts or role == "user":
                    yield {"timestamp": timestamp, "role": role, "text": "\n".join(parts)}
                continue
            if item in {"function_call", "custom_tool_call"}:
                name = _required_string(payload, "name", line_number)
                call_id = _required_string(payload, "call_id", line_number)
                argument_key = "arguments" if item == "function_call" else "input"
                if argument_key not in payload:
                    raise _error(line_number, "tool call arguments are missing")
                calls[call_id] = name
                yield {
                    "timestamp": _timestamp(record, line_number),
                    "role": "assistant",
                    "tool_name": name,
                    "text": f"Tool call (attempt only; success not established): {name}\n"
                    + _text(payload[argument_key]),
                }
                continue
            if item in {"function_call_output", "custom_tool_call_output"}:
                # Named standalone outputs have an item id, not a paired call_id.
                call_id = None
                standalone_name = None
                if "call_id" in payload:
                    call_id = _required_string(payload, "call_id", line_number)
                else:
                    _required_string(payload, "id", line_number)
                    standalone_name = _required_string(payload, "name", line_number)
                if "output" not in payload:
                    raise _error(line_number, "tool output is missing")
                message = {
                    "timestamp": _timestamp(record, line_number),
                    "role": "tool",
                    "text": _text(payload["output"]),
                }
                if call_id in calls:
                    message["tool_name"] = calls[call_id]
                elif standalone_name is not None:
                    message["tool_name"] = standalone_name
                if "is_error" in payload:
                    if not isinstance(payload["is_error"], bool):
                        raise _error(line_number, "is_error must be a boolean")
                    message["is_error"] = payload["is_error"]
                if call_id is not None:
                    completed_calls.add(call_id)
                yield message
                continue
            if item not in {"reasoning", "compaction", "compaction_summary", "context_compaction"}:
                raise _error(line_number, "unsupported response item type")
    if not header_seen:
        raise _error(max(1, line_number - 1), "session_meta header is missing")
    if mirror_line is not None and not response_message_seen:
        raise _error(mirror_line, "event-only messages are unsupported; response_item messages required")
