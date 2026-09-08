"""Behavioral regressions using synthetic logs, never the user's sessions."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import daily_report as report

NOW = datetime(2026, 9, 8, 4, tzinfo=timezone.utc)


def omp_header():
    return {"type": "session", "version": 3, "id": "session-1", "cwd": "/project",
            "timestamp": "2026-09-07T00:00:00Z"}


def omp(stamp, text, role="user"):
    return {"type": "message", "timestamp": stamp,
            "message": {"role": role, "content": [{"type": "text", "text": text}]}}


def codex_header():
    return {"type": "session_meta", "payload": {"id": "codex-1", "cwd": "/project"}}


def codex(stamp, text):
    return {"type": "response_item", "timestamp": stamp,
            "payload": {"type": "message", "role": "user",
                        "content": [{"type": "input_text", "text": text}]}}


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.logs = self.root / "logs"
        self.logs.mkdir()
        self.cfg = {"output_dir": str(self.root / "output"), "timezone": "Asia/Shanghai",
                    "sources": [{"kind": "omp", "root": str(self.logs)}]}

    def log(self, name, rows):
        path = self.logs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        return path

    def packet(self):
        return report.collect(self.cfg, now=NOW)

    def draft(self, packet, text="梳理检索方案，尚未实现。"):
        ref = packet["sessions"][0]["messages"][0]["id"]
        return {"items": [{"project": "检索项目", "text": text, "state": "discussion", "evidence": [ref]}],
                "reflection": {"text": "当前仅完成方案讨论，仍待验证。", "evidence": [ref]}}

    def test_old_session_today_window_and_historical_evidence(self):
        self.log("2026/09/07/old.jsonl", [omp_header(),
            omp("2026-09-07T15:59:59Z", "昨天已修复清洗脚本"),
            omp("2026-09-07T16:00:00Z", "今天比较检索方案"),
            omp("2026-09-08T03:59:59Z", "仍未执行"),
            omp("2026-09-08T04:00:01Z", "采集后发生，不得记录"),
            omp("2026-09-08T16:00:00Z", "次日，不得记录")])
        packet = self.packet()
        session = packet["sessions"][0]
        self.assertEqual([m["text"] for m in session["messages"]], ["今天比较检索方案", "仍未执行"])
        self.assertEqual(session["context"][0]["text"], "昨天已修复清洗脚本")
        draft = self.draft(packet)
        draft["items"][0]["evidence"] = [session["context"][0]["id"]]
        with self.assertRaises(ValueError):
            report.publish(self.cfg, packet, draft)
        self.assertFalse(Path(self.cfg["output_dir"]).exists())

    def test_scheduled_local_midnight_and_dst_calendar_days(self):
        cfg = {**self.cfg, "timezone": "America/New_York"}
        for now, day, hours in [(datetime(2026, 3, 9, 4, 5, tzinfo=timezone.utc), "2026-03-08", 23),
                                (datetime(2026, 11, 2, 5, 5, tzinfo=timezone.utc), "2026-11-01", 25)]:
            selected, start, end = report.date_window(cfg, None, True, now)
            self.assertEqual(selected.isoformat(), day)
            self.assertEqual((end-start).total_seconds(), hours*3600)
        selected, _, _ = report.date_window(self.cfg, None, True,
                                            datetime(2025, 12, 31, 16, 5, tzinfo=timezone.utc))
        self.assertEqual(selected.isoformat(), "2025-12-31")

    def test_report_turn_excluded_without_excluding_skill_development(self):
        self.log("mixed.jsonl", [omp_header(),
            omp("2026-09-08T01:00:00Z", "为日报实现 [daily-work-report] 过滤逻辑"),
            omp("2026-09-08T01:01:00Z", "生成今天的日报"),
            omp("2026-09-08T01:01:01Z", report.MARKER, "assistant"),
            omp("2026-09-08T01:01:02Z", "已生成日报", "assistant"),
            omp("2026-09-08T01:02:00Z", "继续修复边界问题")])
        texts = [m["text"] for m in self.packet()["sessions"][0]["messages"]]
        self.assertEqual(texts, ["为日报实现 [daily-work-report] 过滤逻辑", "继续修复边界问题"])

    def test_partial_all_failed_empty_and_no_work_preserve_existing(self):
        bad = self.logs / "bad.jsonl"
        bad.write_text("{broken", encoding="utf-8")
        self.assertEqual(self.packet()["status"], "failed")
        good = self.log("good.jsonl", [omp_header(), omp("2026-09-08T01:00:00Z", "讨论方案")])
        packet = self.packet()
        result = report.publish(self.cfg, packet, self.draft(packet))
        target = Path(result["path"])
        original = target.read_bytes()
        self.assertIn(report.NOTE, original.decode())
        self.assertEqual(report.publish(self.cfg, packet, {"items": []})["status"], "skipped")
        self.assertEqual(target.read_bytes(), original)
        bad.unlink()
        good.unlink()
        self.assertEqual(self.packet()["status"], "skipped")
        self.assertEqual(target.read_bytes(), original)

    def test_corrupt_tail_retains_available_evidence_with_warning(self):
        path = self.log("truncated.jsonl", [omp_header(), omp("2026-09-08T01:00:00Z", "讨论方案")])
        with path.open("a", encoding="utf-8") as stream:
            stream.write('{"incomplete":')
        packet = self.packet()
        self.assertEqual(packet["status"], "ready")
        self.assertTrue(packet["partial"])
        self.assertIn("讨论方案", packet["sessions"][0]["messages"][0]["text"])

    def test_overwrite_validation_failure_and_atomic_replace_failure(self):
        self.log("work.jsonl", [omp_header(), omp("2026-09-08T01:00:00Z", "讨论方案")])
        packet = self.packet()
        target = Path(report.publish(self.cfg, packet, self.draft(packet))["path"])
        report.publish(self.cfg, packet, self.draft(packet, "比较检索方案，尚未测试。"))
        original = target.read_bytes()
        self.assertIn("比较检索方案", original.decode())
        self.assertEqual(list(target.parent.glob("*.md")), [target])
        with self.assertRaises(ValueError):
            report.publish(self.cfg, packet, self.draft(packet, "字"*801))
        self.assertEqual(target.read_bytes(), original)
        with patch.object(report.os, "replace", side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError):
                report.publish(self.cfg, packet, self.draft(packet))
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(list(target.parent.glob(".daily-report-*")), [])

    def test_assistant_claim_alone_cannot_prove_completion(self):
        self.log("claim.jsonl", [omp_header(), omp("2026-09-08T01:00:00Z", "开发完成", "assistant")])
        packet = self.packet()
        draft = self.draft(packet, "完成开发。")
        draft["items"][0]["state"] = "completed"
        with self.assertRaises(ValueError):
            report.publish(self.cfg, packet, draft)

    def test_codex_mirrors_metadata_and_tool_failure(self):
        self.cfg["sources"][0]["kind"] = "codex"
        stamp = "2026-09-08T01:00:00Z"
        self.log("codex.jsonl", [codex_header(),
            {"type": "world_state", "payload": {"full": True, "state": {}}},
            codex(stamp, "比较方案"),
            {"type": "event_msg", "timestamp": stamp, "payload": {"type": "user_message", "message": "比较方案"}},
            {"type": "response_item", "timestamp": stamp, "payload": {"type": "function_call", "name": "bash", "call_id": "1", "arguments": "test"}},
            {"type": "response_item", "timestamp": stamp, "payload": {"type": "function_call_output", "call_id": "1", "output": "exit code 1: failed", "is_error": True}}])
        messages = self.packet()["sessions"][0]["messages"]
        self.assertEqual([m["text"] for m in messages if m["role"] == "user"], ["比较方案"])
        self.assertEqual(messages[-1]["text"], "exit code 1: failed")
        self.assertTrue(messages[-1]["is_error"])

    def test_secrets_are_redacted_and_rejected_at_publication(self):
        self.log("sensitive.jsonl", [omp_header(), omp("2026-09-08T01:00:00Z", "配置 password=never-publish-this")])
        packet = self.packet()
        self.assertNotIn("never-publish-this", json.dumps(packet))
        with self.assertRaises(ValueError):
            report.publish(self.cfg, packet, self.draft(packet, "配置 api_key=never-publish-this"))

    def test_quoted_secret_values_do_not_leak_suffixes_into_evidence(self):
        self.log("quoted.jsonl", [omp_header(), omp("2026-09-08T01:00:00Z",
            'password="prefix,private-suffix with spaces"；继续比较检索方案')])
        packet = self.packet()
        text = packet["sessions"][0]["messages"][0]["text"]
        self.assertNotIn("private-suffix", text)
        self.assertNotIn("with spaces", text)
        self.assertIn("继续比较检索方案", text)
        with self.assertRaises(ValueError):
            report.publish(self.cfg, packet, self.draft(packet, '配置 password="prefix,private-suffix"'))

    def test_interleaved_projects_are_grouped_with_their_problem_and_resolution(self):
        self.log("work.jsonl", [omp_header(), omp("2026-09-08T01:00:00Z",
            "讨论检索超时与参数；运维重启后仍待验证")])
        packet = self.packet()
        draft = self.draft(packet)
        template = draft["items"][0]
        draft["items"] = [
            {**template, "text": "排查检索超时。", "problem": "批量请求超时。",
             "resolution": "尝试缩小批次，仍待复测。"},
            {**template, "project": "本机运维", "text": "重启服务，待验证。"},
            {**template, "text": "比较检索参数，尚未测试。"},
        ]
        target = Path(report.publish(self.cfg, packet, draft)["path"])
        content = target.read_text(encoding="utf-8")
        self.assertEqual(content.count("### 检索项目"), 1)
        retrieval, operations = content.split("### 本机运维")
        self.assertIn("比较检索参数", retrieval)
        self.assertIn("批量请求超时", retrieval)
        self.assertIn("仍待复测", retrieval)
        self.assertNotIn("批量请求超时", operations)
        self.assertIn("重启服务", operations)

    def test_problem_details_count_toward_limit_and_incomplete_pairs_preserve_report(self):
        self.log("work.jsonl", [omp_header(), omp("2026-09-08T01:00:00Z", "讨论方案")])
        packet = self.packet()
        draft = self.draft(packet)
        target = Path(report.publish(self.cfg, packet, draft)["path"])
        original = target.read_bytes()
        draft["items"][0]["problem"] = "描述请求超时。"
        with self.assertRaises(ValueError):
            report.publish(self.cfg, packet, draft)
        self.assertEqual(target.read_bytes(), original)
        draft["items"][0]["resolution"] = "字" * 801
        with self.assertRaises(ValueError):
            report.publish(self.cfg, packet, draft)
        self.assertEqual(target.read_bytes(), original)

    def test_unreadable_directory_entry_does_not_discard_readable_work(self):
        self.log("good.jsonl", [omp_header(), omp("2026-09-08T01:00:00Z", "讨论方案")])
        inaccessible = self.logs / "inaccessible.jsonl"
        inaccessible.touch()
        original = Path.lstat

        def restricted(path, *args, **kwargs):
            if path == inaccessible:
                raise PermissionError("denied")
            return original(path, *args, **kwargs)

        with patch.object(Path, "lstat", restricted):
            packet = self.packet()
        self.assertEqual(packet["status"], "ready")
        self.assertTrue(packet["partial"])
        self.assertEqual(packet["sessions"][0]["messages"][0]["text"], "讨论方案")

    def test_image_only_user_ends_report_exclusion_for_both_sources(self):
        for kind in ("omp", "codex"):
            with self.subTest(source=kind):
                self.cfg["sources"][0]["kind"] = kind
                if kind == "omp":
                    rows = [omp_header(), omp("2026-09-08T01:00:00Z", "生成今天的日报"),
                            omp("2026-09-08T01:01:00Z", "", "user"),
                            omp("2026-09-08T01:02:00Z", "分析截图中的接口问题", "assistant")]
                    rows[2]["message"]["content"] = [{"type": "image", "data": "synthetic"}]
                else:
                    rows = [codex_header(), codex("2026-09-08T01:00:00Z", "生成今天的日报"),
                            codex("2026-09-08T01:01:00Z", ""),
                            codex("2026-09-08T01:02:00Z", "分析截图中的接口问题")]
                    rows[2]["payload"]["content"] = [{"type": "input_image", "image_url": "synthetic"}]
                    rows[3]["payload"]["role"] = "assistant"
                self.log("session.jsonl", rows)
                packet = self.packet()
                self.assertEqual(packet["status"], "ready")
                self.assertEqual([m["text"] for m in packet["sessions"][0]["messages"]],
                                 ["分析截图中的接口问题"])

    def test_invalid_utf8_tail_preserves_complete_prefix_for_both_sources(self):
        for kind, header, message in (("omp", omp_header, omp), ("codex", codex_header, codex)):
            with self.subTest(source=kind):
                self.cfg["sources"][0]["kind"] = kind
                path = self.log("session.jsonl", [header(), message("2026-09-08T01:00:00Z", "讨论方案")])
                with path.open("ab") as stream:
                    stream.write(b"\xff\n")
                packet = self.packet()
                self.assertEqual(packet["status"], "ready")
                self.assertTrue(packet["partial"])
                self.assertEqual(packet["sessions"][0]["messages"][0]["text"], "讨论方案")

    def test_codex_compaction_control_items_do_not_hide_later_work(self):
        self.cfg["sources"][0]["kind"] = "codex"
        rows = [codex_header()]
        rows.extend({"type": "response_item", "timestamp": "2026-09-07T00:00:00Z",
                     "payload": {"type": kind, "encrypted_content": "opaque"}}
                    for kind in ("compaction", "compaction_summary", "context_compaction"))
        rows.append(codex("2026-09-08T01:00:00Z", "继续讨论方案"))
        self.log("session.jsonl", rows)
        packet = self.packet()
        self.assertEqual(packet["status"], "ready")
        self.assertFalse(packet["partial"])
        self.assertEqual(packet["sessions"][0]["messages"][0]["text"], "继续讨论方案")


if __name__ == "__main__":
    unittest.main()
