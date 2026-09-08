from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol, TypeVar

from pydantic import BaseModel

from research_agent.core.ids import new_id
from research_agent.schemas.live import HostAgentResult
from research_agent.storage.artifact_store import ArtifactStore

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class HostAgentBackendError(RuntimeError):
    pass


class AgentBackend(Protocol):
    async def run(
        self,
        instructions: str,
        context: dict[str, object],
        tools: dict[str, str],
    ) -> HostAgentResult: ...


class CodexExecBackend:
    """Use the installed Codex CLI as the host's native tool-using agent."""

    def __init__(
        self,
        *,
        cwd: Path,
        artifacts: ArtifactStore,
        command: str = "codex",
        model: str | None = None,
        timeout_seconds: float = 900,
    ) -> None:
        executable = shutil.which(command)
        if executable is None:
            raise FileNotFoundError(f"Host agent command not found: {command}")
        self.command = executable
        self.cwd = cwd.resolve()
        self.artifacts = artifacts
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.continuation_id: str | None = None

    async def run(
        self,
        instructions: str,
        context: dict[str, object],
        tools: dict[str, str],
    ) -> HostAgentResult:
        return await self.run_structured(
            instructions,
            context,
            tools,
            response_model=HostAgentResult,
            workflow_contract=True,
        )

    async def run_structured(
        self,
        instructions: str,
        context: dict[str, object],
        tools: dict[str, str],
        *,
        response_model: type[SchemaT],
        workflow_contract: bool = False,
    ) -> SchemaT:
        turn_id = new_id("HOST-TURN")
        prompt = self._prompt(
            instructions, context, tools, workflow_contract=workflow_contract
        )
        with TemporaryDirectory(prefix="research-agent-host-") as temporary:
            temporary_path = Path(temporary)
            schema_path = temporary_path / "response.schema.json"
            output_path = temporary_path / "last-message.json"
            schema_path.write_text(
                json.dumps(self.output_schema(response_model)), encoding="utf-8"
            )
            command = self._command(
                schema_path=schema_path,
                output_path=output_path,
                tools=tools,
            )
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=self.cwd,
                    env=dict(os.environ),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(prompt.encode("utf-8")),
                    timeout=self.timeout_seconds,
                )
            except TimeoutError as exc:
                process.terminate()
                await process.communicate()
                raise HostAgentBackendError("Host agent timed out") from exc
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")
            root = f"artifacts/live/host/{turn_id}"
            self.artifacts.write_text(f"{root}/events.jsonl", stdout_text)
            self.artifacts.write_text(f"{root}/stderr.log", stderr_text)
            if process.returncode != 0:
                raise HostAgentBackendError(
                    f"Host agent exited with code {process.returncode}: "
                    f"{stderr_text[-1000:] or stdout_text[-1000:]}"
                )
            if not output_path.is_file():
                raise HostAgentBackendError(
                    "Host agent produced no structured response"
                )
            try:
                result = response_model.model_validate_json(
                    output_path.read_text(encoding="utf-8")
                )
            except Exception as exc:
                raise HostAgentBackendError(
                    f"Host agent response did not match {response_model.__name__}"
                ) from exc
            self.continuation_id = self._session_id(stdout_text) or self.continuation_id
            if isinstance(result, HostAgentResult):
                result = result.model_copy(
                    update={"continuation_id": self.continuation_id}
                )
            self.artifacts.write_json(
                f"{root}/response.json", result.model_dump(mode="json")
            )
            return result

    def safe_configuration(self) -> dict[str, object]:
        return {
            "backend": "codex_exec",
            "command": self.command,
            "model_configured": bool(self.model),
            "cwd": str(self.cwd),
            "timeout_seconds": self.timeout_seconds,
        }

    @staticmethod
    def output_schema(
        response_model: type[BaseModel] = HostAgentResult,
    ) -> dict[str, object]:
        schema = response_model.model_json_schema()

        def make_strict(node: object) -> None:
            if isinstance(node, dict):
                node.pop("default", None)
                properties = node.get("properties")
                if isinstance(properties, dict):
                    node["additionalProperties"] = False
                    node["required"] = list(properties)
                for value in node.values():
                    make_strict(value)
            elif isinstance(node, list):
                for value in node:
                    make_strict(value)

        make_strict(schema)
        return schema

    def _command(
        self,
        *,
        schema_path: Path,
        output_path: Path,
        tools: dict[str, str],
    ) -> list[str]:
        sandbox = "workspace-write" if "shell" in tools else "read-only"
        base = [self.command]
        if "search" in tools:
            base.append("--search")
        base.extend(
            [
                "--sandbox",
                sandbox,
                "--ask-for-approval",
                "never",
                "--cd",
                str(self.cwd),
            ]
        )
        if self.model:
            base.extend(("--model", self.model))
        if self.continuation_id:
            base.extend(
                (
                    "exec",
                    "resume",
                    "--skip-git-repo-check",
                    self.continuation_id,
                )
            )
        else:
            base.extend(("exec", "--skip-git-repo-check"))
        base.extend(
            (
                "--json",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "-",
            )
        )
        return base

    @staticmethod
    def _prompt(
        instructions: str,
        context: dict[str, object],
        tools: dict[str, str],
        *,
        workflow_contract: bool = True,
    ) -> str:
        rules = [
            "Use only capabilities listed as available.",
            "Return every structured field; use null or an empty list when unused.",
        ]
        if workflow_contract:
            rules.extend(
                [
                    "Classify read-only local inspection as read or filesystem, not shell.",
                    "Do not edit state.json directly; return typed state_update fields.",
                    "Populate only fields listed in context.allowed_state_update_fields.",
                    "Set repository_path only when context.repository_attachment_allowed is true.",
                    "Persist only decision-relevant sources, not exploratory search noise.",
                    "Do not claim execution or metrics; request execution and wait for runner output.",
                    "Use proposed_action for one action listed in context.allowed_actions.",
                ]
            )
        runtime_contract = {
            "available_tool_capabilities": tools,
            "rules": list(dict.fromkeys(rules)),
        }
        return (
            instructions
            + "\n\n# Host runtime contract\n"
            + json.dumps(runtime_contract, indent=2, ensure_ascii=False)
            + "\n\n# Current bounded project context\n"
            + json.dumps(context, indent=2, ensure_ascii=False, default=str)
        )

    @staticmethod
    def _session_id(events: str) -> str | None:
        for line in events.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") in {"thread.started", "session.started"}:
                value = event.get("thread_id") or event.get("session_id")
                if value:
                    return str(value)
        return None
