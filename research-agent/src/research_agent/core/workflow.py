from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from time import perf_counter

from research_agent.core.ids import new_id
from research_agent.core.orchestrator import validate_action
from research_agent.core.transitions import ResearchPhase, require_valid_transition
from research_agent.schemas.decision import DecisionRecord, ResearchAction
from research_agent.schemas.project import ResourceConstraints
from research_agent.schemas.state import ResearchState
from research_agent.storage.artifact_store import ArtifactStore


StepHandler = Callable[[ResearchState, ResearchAction], Awaitable[ResearchPhase]]


class WorkflowPaused(RuntimeError):
    pass


class WorkflowEngine:
    def __init__(
        self,
        handlers: dict[str, StepHandler] | None = None,
        *,
        artifacts: ArtifactStore | None = None,
    ) -> None:
        self.handlers = handlers or {}
        self.artifacts = artifacts

    def register(self, action: str, handler: StepHandler) -> None:
        self.handlers[action] = handler

    async def execute(
        self, state: ResearchState, action: ResearchAction
    ) -> ResearchState:
        if state.human_checkpoint and state.human_checkpoint.required:
            raise WorkflowPaused(state.human_checkpoint.prompt)
        validate_action(state.phase.value, action)
        handler = self.handlers.get(action.action.value)
        if handler is None:
            raise KeyError(f"No workflow handler for action: {action.action.value}")
        old_phase = state.phase
        artifacts_before = self._artifact_paths(state)
        writes_before = len(self.artifacts.written_paths) if self.artifacts else 0
        started = perf_counter()
        try:
            proposed_phase = await handler(state, action)
            require_valid_transition(old_phase, proposed_phase)
        except Exception:
            self._log_step(
                state,
                action,
                old_phase,
                duration=perf_counter() - started,
                status="failed",
                artifact_ids=(
                    self.artifacts.written_paths[writes_before:]
                    if self.artifacts
                    else []
                ),
            )
            raise
        state.phase = proposed_phase
        state.iteration += 1
        state.updated_at = datetime.now(timezone.utc)
        state.decisions.append(
            DecisionRecord(
                id=new_id("DEC"),
                phase=old_phase,
                action=action,
                outcome=f"transitioned_to:{proposed_phase.value}",
            )
        )
        self._log_step(
            state,
            action,
            old_phase,
            duration=perf_counter() - started,
            status="completed",
            artifact_ids=sorted(
                set(self._artifact_paths(state) - artifacts_before)
                | set(
                    self.artifacts.written_paths[writes_before:]
                    if self.artifacts
                    else []
                )
            ),
        )
        return state

    @staticmethod
    def _log_step(
        state: ResearchState,
        action: ResearchAction,
        phase: ResearchPhase,
        *,
        duration: float,
        status: str,
        artifact_ids: list[str],
    ) -> None:
        logging.getLogger("research_agent.workflow").info(
            "workflow_step",
            extra={
                "workflow": {
                    "project_id": state.project.id,
                    "phase": phase.value,
                    "iteration": state.iteration,
                    "agent_role": "orchestrator",
                    "prompt_profile": action.action.value,
                    "action": action.action.value,
                    "duration": round(duration, 6),
                    "status": status,
                    "artifact_ids": artifact_ids,
                }
            },
        )

    @staticmethod
    def _artifact_paths(state: ResearchState) -> set[str]:
        found: set[str] = set()

        def visit(value: object) -> None:
            if isinstance(value, str) and value.startswith("artifacts/"):
                found.add(value)
            elif isinstance(value, dict):
                for nested in value.values():
                    visit(nested)
            elif isinstance(value, list):
                for nested in value:
                    visit(nested)

        visit(state.model_dump(mode="json"))
        return found

    def resume_checkpoint(self, state: ResearchState, response: str) -> ResearchState:
        checkpoint = state.human_checkpoint
        if checkpoint is None or not checkpoint.required:
            raise ValueError("No human checkpoint is awaiting input")
        if checkpoint.type == "topic_selection":
            if response not in checkpoint.options:
                raise ValueError(f"Choose one of: {', '.join(checkpoint.options)}")
            selected = next(
                (gap for gap in state.gaps.candidates if gap.id == response), None
            )
            if selected is None:
                raise ValueError("Selected gap does not exist in state")
            for gap in state.gaps.candidates:
                if gap.status == "selected":
                    gap.status = "shortlisted"
            selected.status = "selected"
            state.gaps.selected_gap_id = response
        elif checkpoint.type == "resource_input":
            if response.strip().lower() != "default":
                try:
                    values = json.loads(response)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "Resource input must be 'default' or a JSON object"
                    ) from exc
                state.constraints = ResourceConstraints.model_validate(
                    {**state.constraints.model_dump(), **values}
                )
        elif checkpoint.type == "major_pivot":
            if response not in checkpoint.options:
                raise ValueError(f"Choose one of: {', '.join(checkpoint.options)}")
        state.phase = checkpoint.resume_phase
        state.human_checkpoint = None
        state.iteration += 1
        state.updated_at = datetime.now(timezone.utc)
        return state
