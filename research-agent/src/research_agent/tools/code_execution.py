from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CodeExecutionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str


class CodeExecutionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: bool
    message: str


class CodeExecutionTool:
    name = "code_execution"

    async def run(self, input: CodeExecutionInput) -> CodeExecutionOutput:
        return CodeExecutionOutput(
            accepted=False,
            message="Direct code execution is disabled; use the authorized ExperimentRunner.",
        )

