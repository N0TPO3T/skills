"""Local session collection and atomic publishing; summarization belongs to the host."""
from __future__ import annotations

import argparse
from collections import deque
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from omp_source import iter_messages as omp_messages
from codex_source import iter_messages as codex_messages

NOTE = "注：部分会话未读取，本日报可能不完整"
MARKER = "[daily-work-report]"
DEFAULT_CONFIG = Path.home() / ".daily-work-report" / "config.json"
# Defense in depth only: the host must also omit sensitive material semantically.
SECRET = re.compile(
    r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----"
    r"|\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{12,}"
    r"|\bBearer\s+[A-Za-z0-9._~+/=-]+"
    r"|(?:password|passwd|api[_-]?key|access[_-]?token|secret|密码|密钥)"
    r"[\"']?\s*[:=：]\s*[\"']?[^\s,;\"'，；]+",
    re.IGNORECASE,
)
REPORT_REQUEST = re.compile(r"^(?:请)?(?:生成今天(?:的)?日报|重新生成\d{4}-\d{2}-\d{2}(?:的)?日报)[。！!\s]*$")


def clean(text: str) -> str:
    return SECRET.sub("[已隐去敏感内容]", text)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("JSON 顶层必须是对象")
    return value


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix=".daily-report-", delete=False) as stream:
            name = stream.name
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if name is not None:
            Path(name).unlink(missing_ok=True)


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        raise ValueError("时区不可用：请使用 IANA 时区；Windows 可运行 python -m pip install tzdata") from None


def initialize(args) -> dict:
    name = args.timezone or os.environ.get("TZ")
    if not name:
        raise ValueError("宿主未提供时区；请传入 --timezone（IANA 名称），不能用当前固定 UTC 偏移替代")
    zone(name)
    sources = []
    if "omp" in args.sources:
        sources.append({"kind": "omp", "root": str(args.omp_root.expanduser().resolve())})
    if "codex" in args.sources:
        sources.append({"kind": "codex", "root": str(args.codex_root.expanduser().resolve())})
        archive = args.codex_archive_root
        if archive is not None:
            sources.append({"kind": "codex", "root": str(archive.expanduser().resolve())})
    config = {"output_dir": str(args.output_dir.expanduser().resolve()), "timezone": name, "sources": sources}
    atomic_write(args.config, json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    return {"status": "configured", "config": str(args.config.resolve())}


def configuration(path: Path) -> dict:
    cfg = load_json(path)
    if not isinstance(cfg.get("output_dir"), str) or not Path(cfg["output_dir"]).is_absolute():
        raise ValueError("配置 output_dir 必须为绝对路径")
    if not isinstance(cfg.get("timezone"), str):
        raise ValueError("配置缺少 timezone")
    zone(cfg["timezone"])
    sources = cfg.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("配置必须包含已授权的 sources")
    for source in sources:
        if (not isinstance(source, dict) or source.get("kind") not in {"omp", "codex"}
                or not isinstance(source.get("root"), str) or not Path(source["root"]).is_absolute()):
            raise ValueError("会话来源必须包含 kind 和绝对路径 root")
    return cfg


def date_window(cfg: dict, report_date: str | None, scheduled: bool,
                now: datetime | None = None) -> tuple[date, datetime, datetime]:
    tz = zone(cfg["timezone"])
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(tz)
    day = date.fromisoformat(report_date) if report_date else local.date() - timedelta(days=int(scheduled))
    if report_date and report_date != day.isoformat():
        raise ValueError("report_date 必须为 YYYY-MM-DD")
    if day > local.date():
        raise ValueError("不能生成未来日期的日报")
    start = datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)
    return day, start, min(end, now.astimezone(timezone.utc))


def session_files(root: Path, errors: list) -> list[Path]:
    if not root.is_dir():
        errors.append({"path": str(root), "reason": "授权会话目录不存在或不可读取"})
        return []
    files = []

    def onerror(error):
        errors.append({"path": str(error.filename), "reason": "会话目录读取失败"})

    def linked(path):
        info = path.lstat()
        return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)

    # No creation-date / mtime prefilter: old sessions may continue today.
    for folder, dirs, names in os.walk(root, followlinks=False, onerror=onerror):
        dirs[:] = sorted(d for d in dirs if not linked(Path(folder) / d))
        for name in sorted(names):
            file = Path(folder) / name
            if file.suffix == ".jsonl" and not linked(file):
                files.append(file)
    return files


def collect(cfg: dict, report_date: str | None = None, scheduled: bool = False,
            exclude: tuple[str, ...] = (), now: datetime | None = None) -> dict:
    day, start, end = date_window(cfg, report_date, scheduled, now)
    errors, sessions = [], []
    seen = set()
    readable = 0
    for source in cfg["sources"]:
        root = Path(source["root"])
        for file in session_files(root, errors):
            resolved = str(file.resolve())
            if resolved in seen or file.stem in exclude or resolved in exclude:
                continue
            seen.add(resolved)
            prefix = hashlib.sha256(resolved.encode()).hexdigest()[:16]
            history = deque(maxlen=2)
            messages, context = [], []
            reporting = False
            iterator = omp_messages if source["kind"] == "omp" else codex_messages
            try:
                for index, message in enumerate(iterator(file)):
                    text = message["text"]
                    # A dedicated marked report turn is excluded until the next user turn.
                    if message["role"] == "user":
                        reporting = bool(REPORT_REQUEST.fullmatch(text.strip()))
                    if message["role"] in {"user", "assistant"} and (
                            text.strip() == MARKER or text.startswith((MARKER + " ", MARKER + "\n"))):
                        reporting = True
                    if reporting:
                        continue
                    stamp = message["timestamp"].astimezone(timezone.utc)
                    record = {**message, "timestamp": stamp.isoformat(), "text": clean(text),
                              "id": f"{prefix}:{index}"}
                    if stamp < start and message["role"] in {"user", "assistant"}:
                        history.append({**record, "context_only": True})
                    elif start <= stamp < end:
                        if not messages:
                            context = list(history)
                        messages.append(record)
                readable += 1
            except (OSError, ValueError, TypeError, KeyError) as exc:
                # Never echo raw exception messages: malformed JSON can contain secrets.
                errors.append({"path": resolved, "reason": f"会话读取失败（{type(exc).__name__}）"})
            if messages:
                sessions.append({"source": source["kind"], "session": file.stem,
                                 "context": context, "messages": messages})
    status = "ready" if sessions else "failed" if errors and not readable else "skipped"
    reason = None
    if status == "failed":
        reason = "会话读取全部失败，不能判断当天工作"
    elif status == "skipped":
        reason = "已读取范围内无当日消息；部分会话读取失败，不能判断完整工作情况" if errors else "当天没有可读取的会话消息"
    return {"version": 1, "status": status, "reason": reason, "report_date": day.isoformat(),
            "timezone": cfg["timezone"], "start": start.isoformat(), "end": end.isoformat(),
            "partial": bool(errors), "errors": errors, "sessions": sessions}


def prose(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
        raise ValueError(f"{label} 必须是非空单行文本")
    if value.lstrip().startswith(("#", "- ", "* ", ">", "```")):
        raise ValueError(f"{label} 不得包含额外 Markdown 栏目")
    if clean(value) != value:
        raise ValueError("草稿疑似包含敏感内容，请删除后重新生成")
    return value.strip()


def render(packet: dict, draft: dict) -> str | None:
    if packet.get("status") != "ready":
        raise ValueError("只有 ready 状态的证据包可以发布")
    items = draft.get("items")
    if not isinstance(items, list) or len(items) > 5:
        raise ValueError("今日工作必须为 0—5 条")
    if not items:
        return None
    evidence = {m["id"]: m for session in packet["sessions"] for m in session["messages"]}

    def references(obj):
        refs = obj.get("evidence")
        if not isinstance(refs, list) or not refs or any(not isinstance(r, str) or r not in evidence for r in refs):
            raise ValueError("每条工作及复盘必须引用当日证据 ID；历史上下文不能用作成果依据")
        return [evidence[r] for r in refs]

    texts = []
    for item in items:
        if not isinstance(item, dict) or item.get("state") not in {"discussion", "attempt", "completed", "blocked"}:
            raise ValueError("工作状态必须为 discussion/attempt/completed/blocked")
        refs = references(item)
        if item["state"] == "completed" and not any(
                r["role"] == "user" or (r["role"] == "tool" and not r.get("is_error", False)) for r in refs):
            raise ValueError("完成状态不能仅引用助手自述或工具调用，须引用用户确认或成功结果")
        texts.append(prose(item.get("text"), "工作内容"))
    reflection = draft.get("reflection")
    if not isinstance(reflection, dict):
        raise ValueError("缺少简短复盘")
    references(reflection)
    review = prose(reflection.get("text"), "简短复盘")
    sentences = [s for s in re.split(r"[。！？!?]+|(?<=[a-zA-Z])\.(?:\s|$)", review) if s.strip()]
    if not 1 <= len(sentences) <= 2:
        raise ValueError("简短复盘只能为 1—2 句话")
    # Unicode non-whitespace characters; headings, bullets and exceptional note excluded.
    if sum(len(re.sub(r"\s", "", t)) for t in [*texts, review]) > 300:
        raise ValueError("正文超过 300 字，请压缩后重试")
    day = date.fromisoformat(packet["report_date"])
    if day.isoformat() != packet["report_date"]:
        raise ValueError("证据包日期必须为 YYYY-MM-DD")
    result = f"# 日报｜{day.isoformat()}\n\n## 今日工作\n" + "".join(f"- {t}\n" for t in texts)
    result += f"\n## 简短复盘\n{review}\n"
    if packet["partial"]:
        result += f"\n{NOTE}\n"
    return result


def publish(cfg: dict, packet: dict, draft: dict) -> dict:
    if packet.get("timezone") != cfg["timezone"]:
        raise ValueError("证据包时区与当前配置不一致，请重新采集")
    text = render(packet, draft)
    if text is None:
        reason = "已读取消息没有可记录的工作内容"
        if packet["partial"]:
            reason += "；部分会话未读取，不能判断完整工作情况"
        return {"status": "skipped", "reason": reason}
    # Neither the draft nor session text can supply an output path.
    path = Path(cfg["output_dir"]) / f"{packet['report_date']}.md"
    atomic_write(path, text)
    return {"status": "saved", "path": str(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="保存用户授权的配置，不安装调度任务")
    init.add_argument("--output-dir", type=Path, required=True)
    init.add_argument("--timezone", help="宿主用户时区（IANA），缺省读取 TZ")
    init.add_argument("--sources", nargs="+", choices=["omp", "codex"], default=["omp", "codex"])
    init.add_argument("--omp-root", type=Path, default=Path.home()/".omp/agent/sessions")
    init.add_argument("--codex-root", type=Path, default=Path.home()/".codex/sessions")
    init.add_argument("--codex-archive-root", type=Path, help="可选授权 Codex archived_sessions 目录")
    get = commands.add_parser("collect", help="读取全部授权会话并按消息日期生成证据包")
    get.add_argument("--report-date")
    get.add_argument("--scheduled", action="store_true", help="未指定日期时取配置时区的前一天")
    get.add_argument("--exclude-session", action="append", default=[], help="排除指定文件 stem 或绝对路径")
    get.add_argument("--packet", type=Path, required=True)
    save = commands.add_parser("save", help="校验宿主摘要草稿并原子保存日报")
    save.add_argument("--packet", type=Path, required=True)
    save.add_argument("--draft", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "init":
            result = initialize(args)
        else:
            cfg = configuration(args.config)
            if args.command == "collect":
                packet = collect(cfg, args.report_date, args.scheduled, tuple(args.exclude_session))
                atomic_write(args.packet, json.dumps(packet, ensure_ascii=False, indent=2) + "\n")
                result = {k: packet[k] for k in ("status", "reason", "partial")}
                result["packet"] = str(args.packet.resolve())
            else:
                result = publish(cfg, load_json(args.packet), load_json(args.draft))
        print(json.dumps(result, ensure_ascii=False))
        return int(result["status"] == "failed")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        # Our validation errors are safe; OS/JSON exceptions may contain arbitrary input.
        reason = str(exc) if type(exc) is ValueError else f"读取、配置或保存失败（{type(exc).__name__}）"
        print(json.dumps({"status": "failed", "reason": reason}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
