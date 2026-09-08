from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
from collections.abc import Sequence
from pathlib import Path

import yaml

from research_agent.core.ids import stable_id
from research_agent.host_agent import CodexExecBackend
from research_agent.literature.providers import (
    ArxivLikeProvider,
    CrossrefMetadataProvider,
    GenericWebPaperProvider,
    MockLiteratureProvider,
    OpenAlexMetadataProvider,
)
from research_agent.logging import configure_logging
from research_agent.schemas.literature import LiteratureSearchQuery, NoveltySearchInput
from research_agent.schemas.literature_quality import LiteratureQualityGateConfig
from research_agent.services.extraction_evaluation_service import (
    ExtractionEvaluationService,
)
from research_agent.services.focused_verification_service import (
    FocusedEvidenceVerificationService,
)
from research_agent.services.literature_quality_gate_service import (
    LiteratureQualityGateService,
)
from research_agent.services.literature_quality_report_service import (
    LiteratureQualityReportService,
)
from research_agent.services.literature_service import (
    LiteratureService,
    LiteratureSettings,
)
from research_agent.services.live_runtime import LiveResearchRuntime
from research_agent.services.metadata_corroboration_service import (
    MetadataCorroborationService,
)
from research_agent.services.repository_attachment_service import (
    RepositoryAttachmentService,
)
from research_agent.skill_context import SkillContextLoader
from research_agent.storage.artifact_store import ArtifactStore
from research_agent.storage.project_store import ProjectStore
from research_agent.storage.state_store import StateStore
from research_agent.workflows.runtime import ResearchRuntime, WorkflowRunResult


def _projects_root(value: str | None) -> Path:
    configured = value or os.environ.get("RESEARCH_AGENT_PROJECTS_ROOT") or "projects"
    return Path(configured)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-agent",
        description="Deterministic, evidence-aware autonomous ML research workflow",
    )
    parser.add_argument(
        "--projects-root",
        help="Project storage root (default: ./projects or RESEARCH_AGENT_PROJECTS_ROOT)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize a research project")
    init_parser.add_argument("project_id")
    init_parser.add_argument("--direction", default="")
    init_parser.add_argument(
        "--mock", action="store_true", help="Mark the project as synthetic test data"
    )

    status_parser = subparsers.add_parser("status", help="Show project status")
    status_parser.add_argument("project_id")

    run_parser = subparsers.add_parser("run", help="Run until a checkpoint or plan")
    run_parser.add_argument("project_id")
    run_mode = run_parser.add_mutually_exclusive_group()
    run_mode.add_argument("--mock", action="store_true")
    run_mode.add_argument("--live", action="store_true")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect a live turn without executing it",
    )

    resume_parser = subparsers.add_parser("resume", help="Resolve a human checkpoint")
    resume_parser.add_argument("project_id")
    resume_parser.add_argument(
        "response", nargs="?", help="Checkpoint response; prompted when omitted"
    )
    resume_mode = resume_parser.add_mutually_exclusive_group()
    resume_mode.add_argument("--mock", action="store_true")
    resume_mode.add_argument("--live", action="store_true")

    attach_parser = subparsers.add_parser(
        "attach-repo", help="Attach an existing repository to a research project"
    )
    attach_parser.add_argument("project_id")
    attach_parser.add_argument("repository_path", type=Path)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Check live host, skill, project, repository, and execution readiness",
    )
    doctor_parser.add_argument("project_id")

    install_skill_parser = subparsers.add_parser(
        "install-skill", help="Install the packaged Research Agent skill for the host"
    )
    install_skill_parser.add_argument(
        "--target",
        type=Path,
        help="Exact destination directory (default: CODEX_HOME/skills/research-agent)",
    )

    inspect_parser = subparsers.add_parser(
        "inspect", help="Inspect typed project state"
    )
    inspect_parser.add_argument("project_id")
    inspect_parser.add_argument(
        "view", choices=("state", "literature", "gaps", "experiments")
    )

    skill_context_parser = subparsers.add_parser(
        "skill-context", help="Show progressively loaded Research Agent skill files"
    )
    skill_context_parser.add_argument("project_id")

    literature_parser = subparsers.add_parser(
        "literature", help="Search, verify, and inspect literature intelligence"
    )
    literature_commands = literature_parser.add_subparsers(
        dest="literature_command", required=True
    )
    literature_search = literature_commands.add_parser("search")
    literature_search.add_argument("project_id")
    literature_search.add_argument(
        "--provider",
        action="append",
        choices=("arxiv", "crossref", "openalex", "web", "mock"),
    )
    literature_search.add_argument(
        "--mode", choices=("standard", "novelty_check"), default="standard"
    )
    literature_search.add_argument("--method")
    literature_search.add_argument("--mechanism")
    literature_search.add_argument("--task")
    literature_search.add_argument("--setting")
    literature_search.add_argument(
        "--query",
        action="append",
        help="Use an explicit query; required for direct-URL web acquisition",
    )

    literature_status = literature_commands.add_parser("status")
    literature_status.add_argument("project_id")

    literature_inspect = literature_commands.add_parser("inspect")
    literature_inspect.add_argument("project_id")
    literature_inspect.add_argument("paper_id")

    literature_verify = literature_commands.add_parser("verify")
    literature_verify.add_argument("project_id")
    literature_verify.add_argument("paper_id")
    literature_verify.add_argument(
        "--provider",
        action="append",
        choices=("arxiv", "crossref", "openalex", "web", "mock"),
    )

    literature_coverage = literature_commands.add_parser("coverage")
    literature_coverage.add_argument("project_id")

    literature_corroborate = literature_commands.add_parser(
        "corroborate", help="Corroborate canonical metadata without silent overwrite"
    )
    literature_corroborate.add_argument("project_id")
    literature_corroborate.add_argument("paper_id")
    literature_corroborate.add_argument(
        "--provider",
        action="append",
        choices=("crossref", "openalex"),
    )

    literature_quality = literature_commands.add_parser(
        "quality", help="Write the multi-dimensional literature quality report"
    )
    literature_quality.add_argument("project_id")

    literature_focused_verify = literature_commands.add_parser(
        "focused-verify",
        help="Verify one GAP's central statements against parsed source passages",
    )
    literature_focused_verify.add_argument("project_id")
    literature_focused_verify.add_argument("gap_id")

    eval_parser = subparsers.add_parser(
        "eval", help="Manage human-labelled extraction evaluation"
    )
    eval_commands = eval_parser.add_subparsers(dest="eval_scope", required=True)
    literature_eval = eval_commands.add_parser("literature")
    literature_eval_commands = literature_eval.add_subparsers(
        dest="eval_command", required=True
    )
    eval_create_set = literature_eval_commands.add_parser("create-set")
    eval_create_set.add_argument("project_id")
    eval_create_set.add_argument("--size", type=int, default=30)
    eval_export = literature_eval_commands.add_parser("export-annotation")
    eval_export.add_argument("project_id")
    eval_export.add_argument("paper_id")
    eval_export.add_argument("--format", choices=("yaml", "json"), default="yaml")
    eval_import = literature_eval_commands.add_parser("import-annotation")
    eval_import.add_argument("project_id")
    eval_import.add_argument("path", type=Path)
    eval_run = literature_eval_commands.add_parser("run")
    eval_run.add_argument("project_id")
    eval_report = literature_eval_commands.add_parser("report")
    eval_report.add_argument("project_id")
    return parser


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _run_summary(result: WorkflowRunResult) -> dict[str, object]:
    state = result.state
    summary: dict[str, object] = {
        "project_id": state.project.id,
        "phase": state.phase.value,
        "iteration": state.iteration,
        "stopped_reason": result.stopped_reason,
        "synthetic_test_data": state.project.synthetic_test_data,
    }
    if state.human_checkpoint:
        summary["checkpoint"] = state.human_checkpoint.model_dump(mode="json")
    if result.stopped_reason == "experiment_plan_ready":
        summary["experiment_id"] = state.experiments.experiments[-1].id
    return summary


def _load_literature_settings(project_dir: Path) -> LiteratureSettings:
    config_path = project_dir / "project.yaml"
    if not config_path.is_file():
        return LiteratureSettings()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return LiteratureSettings.model_validate(raw.get("literature", {}))


def _load_quality_gate_config(project_dir: Path) -> LiteratureQualityGateConfig:
    config_path = project_dir / "project.yaml"
    if not config_path.is_file():
        return LiteratureQualityGateConfig()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return LiteratureQualityGateConfig.model_validate(
        raw.get("literature_quality_gate", {})
    )


def _provider_factories(settings: LiteratureSettings):
    return {
        "arxiv": lambda: ArxivLikeProvider(
            max_results=settings.max_candidates_per_query
        ),
        "crossref": lambda: CrossrefMetadataProvider(
            mailto=os.environ.get("CROSSREF_MAILTO"),
            timeout_seconds=settings.provider_timeout_seconds,
            max_results=settings.max_candidates_per_query,
        ),
        "openalex": lambda: OpenAlexMetadataProvider(
            api_key=os.environ.get("OPENALEX_API_KEY"),
            timeout_seconds=settings.provider_timeout_seconds,
            max_results=settings.max_candidates_per_query,
        ),
        "web": GenericWebPaperProvider,
        "mock": MockLiteratureProvider,
    }


def _literature_service(
    root: Path,
    project_id: str,
    *,
    provider_names: list[str] | None,
    synthetic_project: bool,
) -> LiteratureService:
    selected = provider_names or ["arxiv"]
    contains_mock = "mock" in selected
    if contains_mock and len(selected) != 1:
        raise ValueError("Mock and real literature providers cannot be mixed")
    if contains_mock and not synthetic_project:
        raise ValueError("Mock provider requires a project initialized with --mock")
    if not contains_mock and synthetic_project:
        raise ValueError("Real providers cannot write into a synthetic mock project")
    project_dir = root / project_id
    settings = _load_literature_settings(project_dir)
    factories = _provider_factories(settings)
    providers = [factories[name]() for name in selected]
    return LiteratureService(
        providers=providers,
        artifacts=ArtifactStore(project_dir),
        settings=settings,
    )


def _literature_status(state) -> dict[str, object]:
    literature = state.literature
    return {
        "project_id": state.project.id,
        "query_count": len(literature.search_queries),
        "candidate_count": len(literature.candidates),
        "metadata_verified_count": sum(
            paper.metadata_verified and not paper.synthetic_test_data
            for paper in literature.paper_metadata
        ),
        "content_verified_count": sum(
            content.content_verified and not content.synthetic_test_data
            for content in literature.contents
        ),
        "extraction_count": len(literature.extractions),
        "statement_count": len(literature.statements),
        "failure_count": len(literature.failures),
        "latest_coverage_sufficient": (
            literature.coverage_reports[-1].sufficient_for_gap_synthesis
            if literature.coverage_reports
            else False
        ),
    }


def _inspect_literature_paper(state, paper_id: str) -> dict[str, object]:
    literature = state.literature
    metadata = next(
        (item for item in literature.paper_metadata if item.paper_id == paper_id), None
    )
    if metadata is None:
        raise ValueError(f"Unknown paper: {paper_id}")
    content = next(
        (item for item in literature.contents if item.paper_id == paper_id), None
    )
    extraction = next(
        (item for item in literature.extractions if item.paper_id == paper_id), None
    )
    return {
        "metadata": metadata.model_dump(mode="json"),
        "content": content.model_dump(mode="json") if content else None,
        "extraction": extraction.model_dump(mode="json") if extraction else None,
        "statements": [
            item.model_dump(mode="json")
            for item in literature.statements
            if item.paper_id == paper_id
        ],
        "provenance": [
            item.model_dump(mode="json")
            for item in literature.provenance_records
            if item.source_id == paper_id or item.entity_id == paper_id
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    root = _projects_root(args.projects_root)
    project_store = ProjectStore(root)
    state_store = StateStore(root)

    try:
        if args.command == "init":
            direction = args.direction or args.project_id.replace("_", " ")
            state = project_store.initialize(
                args.project_id, direction=direction, synthetic=args.mock
            )
            _print_json(
                {
                    "project_id": state.project.id,
                    "phase": state.phase.value,
                    "state_path": str(state_store.state_path(state.project.id)),
                    "synthetic_test_data": state.project.synthetic_test_data,
                }
            )
            return 0

        if args.command == "status":
            state = state_store.load(args.project_id)
            _print_json(
                {
                    "project_id": state.project.id,
                    "phase": state.phase.value,
                    "iteration": state.iteration,
                    "checkpoint": (
                        state.human_checkpoint.model_dump(mode="json")
                        if state.human_checkpoint
                        else None
                    ),
                    "papers": len(state.literature.papers),
                    "gaps": len(state.gaps.candidates),
                    "experiments": len(state.experiments.experiments),
                }
            )
            return 0

        if args.command == "run":
            if args.live:
                runtime = LiveResearchRuntime(root)
                if args.dry_run:
                    _print_json(runtime.dry_run(args.project_id))
                    return 0
                result = asyncio.run(runtime.run_until_pause(args.project_id))
                summary = _run_summary(
                    WorkflowRunResult(result.state, result.stopped_reason)
                )
                summary["mode"] = "live"
                summary["host_turn_artifacts"] = result.host_turn_artifacts
                _print_json(summary)
                return 0
            if args.dry_run:
                raise ValueError("--dry-run requires --live")
            if not args.mock:
                raise ValueError("Choose exactly one runtime mode: --mock or --live")
            result = asyncio.run(
                ResearchRuntime(root, mock=args.mock).run_until_pause(args.project_id)
            )
            _print_json(_run_summary(result))
            return 0

        if args.command == "resume":
            runtime = ResearchRuntime(root, mock=args.mock)
            state = state_store.load(args.project_id)
            if state.human_checkpoint is None:
                raise ValueError("No human checkpoint is awaiting input")
            response = args.response
            if response is None:
                print(state.human_checkpoint.prompt)
                if state.human_checkpoint.options:
                    print("Options: " + ", ".join(state.human_checkpoint.options))
                response = input("> ").strip()
            runtime.resume(args.project_id, response)
            if args.mock:
                result = asyncio.run(runtime.run_until_pause(args.project_id))
                _print_json(_run_summary(result))
            elif args.live:
                result = asyncio.run(
                    LiveResearchRuntime(root).run_until_pause(args.project_id)
                )
                summary = _run_summary(
                    WorkflowRunResult(result.state, result.stopped_reason)
                )
                summary["mode"] = "live"
                summary["host_turn_artifacts"] = result.host_turn_artifacts
                _print_json(summary)
            else:
                _print_json(
                    {
                        "project_id": args.project_id,
                        "checkpoint_resolved": True,
                        "next": f"research-agent run {args.project_id}",
                    }
                )
            return 0

        if args.command == "attach-repo":
            state = state_store.load(args.project_id)
            if state.project.synthetic_test_data:
                raise ValueError("Cannot attach a real repository to a mock project")
            repository = RepositoryAttachmentService(root / args.project_id).attach(
                args.repository_path
            )
            _print_json({"project_id": state.project.id, "repository": repository})
            return 0

        if args.command == "doctor":
            _print_json(LiveResearchRuntime(root).doctor(args.project_id))
            return 0

        if args.command == "install-skill":
            source = SkillContextLoader().root
            codex_root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
            target = (args.target or codex_root / "skills" / "research-agent").resolve()
            if target.exists():
                raise FileExistsError(f"Skill destination already exists: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)
            SkillContextLoader(target)
            _print_json(
                {
                    "installed": True,
                    "source": str(source),
                    "target": str(target),
                    "skill": "research-agent",
                }
            )
            return 0

        if args.command == "inspect":
            state = state_store.load(args.project_id)
            views = {
                "state": state,
                "literature": state.literature,
                "gaps": state.gaps,
                "experiments": state.experiments,
            }
            _print_json(views[args.view].model_dump(mode="json"))
            return 0
        if args.command == "skill-context":
            state = state_store.load(args.project_id)
            loaded = SkillContextLoader().load_for_state(state)
            summary = loaded.summary()
            summary["project_id"] = state.project.id
            summary["full_sop_character_count"] = (
                SkillContextLoader().full_sop_character_count()
            )
            _print_json(summary)
            return 0
        if args.command == "eval":
            state = state_store.load(args.project_id)
            project_dir = root / args.project_id
            evaluation = ExtractionEvaluationService(ArtifactStore(project_dir))
            if args.eval_command == "create-set":
                path = evaluation.create_set(state, size=args.size)
                _print_json({"project_id": state.project.id, "artifact": path})
                return 0
            if args.eval_command == "export-annotation":
                path = evaluation.export_annotation(
                    state, args.paper_id, output_format=args.format
                )
                _print_json({"project_id": state.project.id, "artifact": path})
                return 0
            if args.eval_command == "import-annotation":
                path = evaluation.import_annotation(state, args.path)
                state_store.save(state)
                _print_json({"project_id": state.project.id, "artifact": path})
                return 0
            if args.eval_command == "run":
                result = evaluation.evaluate(state)
                statuses = LiteratureQualityGateService(
                    _load_quality_gate_config(project_dir)
                ).apply(state, result)
                state_store.save(state)
                _print_json(
                    {
                        "evaluation": result.model_dump(mode="json"),
                        "capabilities": [
                            item.model_dump(mode="json") for item in statuses
                        ],
                    }
                )
                return 0
            if args.eval_command == "report":
                latest = (
                    state.literature_quality.extraction_evaluations[-1]
                    if state.literature_quality.extraction_evaluations
                    else None
                )
                _print_json(
                    {
                        "project_id": state.project.id,
                        "available": latest is not None,
                        "evaluation": (
                            latest.model_dump(mode="json") if latest else None
                        ),
                        "capabilities": [
                            item.model_dump(mode="json")
                            for item in state.literature_quality.capability_statuses
                        ],
                    }
                )
                return 0
        if args.command == "literature":
            state = state_store.load(args.project_id)
            literature_command = args.literature_command
            if literature_command == "status":
                _print_json(_literature_status(state))
                return 0
            if literature_command == "coverage":
                if not state.literature.coverage_reports:
                    _print_json(
                        {
                            "project_id": state.project.id,
                            "available": False,
                            "message": "No literature coverage report has been generated.",
                        }
                    )
                else:
                    _print_json(
                        state.literature.coverage_reports[-1].model_dump(mode="json")
                    )
                return 0
            if literature_command == "inspect":
                _print_json(_inspect_literature_paper(state, args.paper_id))
                return 0
            if literature_command == "quality":
                report = LiteratureQualityReportService(
                    ArtifactStore(root / args.project_id)
                ).build(state)
                state_store.save(state)
                _print_json(report.model_dump(mode="json"))
                return 0
            if literature_command == "focused-verify":
                artifacts = ArtifactStore(root / args.project_id)
                service = FocusedEvidenceVerificationService(
                    backend_factory=lambda: CodexExecBackend(
                        cwd=root / args.project_id,
                        artifacts=artifacts,
                        command=os.environ.get("RESEARCH_AGENT_HOST_COMMAND", "codex"),
                        model=os.environ.get("RESEARCH_AGENT_HOST_MODEL"),
                    ),
                    artifacts=artifacts,
                )
                tasks = asyncio.run(service.verify_gap(state, args.gap_id))
                state_store.save(state)
                gap = next(
                    item for item in state.gaps.candidates if item.id == args.gap_id
                )
                _print_json(
                    {
                        "project_id": state.project.id,
                        "gap_id": gap.id,
                        "verification_tasks": [
                            item.model_dump(mode="json") for item in tasks
                        ],
                        "supporting_statement_ids": gap.supporting_statement_ids,
                        "contradictory_statement_ids": gap.contradictory_statement_ids,
                    }
                )
                return 0
            if literature_command == "corroborate":
                settings = _load_literature_settings(root / args.project_id)
                selected = args.provider or ["crossref", "openalex"]
                factories = _provider_factories(settings)
                corroboration = asyncio.run(
                    MetadataCorroborationService(
                        providers=[factories[name]() for name in selected],
                        artifacts=ArtifactStore(root / args.project_id),
                    ).corroborate(state, args.paper_id)
                )
                state_store.save(state)
                _print_json(corroboration.model_dump(mode="json"))
                return 0
            service = _literature_service(
                root,
                args.project_id,
                provider_names=args.provider,
                synthetic_project=state.project.synthetic_test_data,
            )
            if literature_command == "search":
                novelty = None
                if args.mode == "novelty_check":
                    values = (args.method, args.mechanism, args.task, args.setting)
                    if not all(values):
                        raise ValueError(
                            "novelty_check requires --method, --mechanism, --task, and --setting"
                        )
                    novelty = NoveltySearchInput(
                        proposed_method=args.method,
                        mechanism=args.mechanism,
                        task=args.task,
                        setting=args.setting,
                    )
                result = asyncio.run(
                    service.search_round(
                        state,
                        search_mode=args.mode,
                        novelty=novelty,
                        queries_override=(
                            [
                                LiteratureSearchQuery(
                                    id=stable_id("QUERY", "explicit", query),
                                    query=query,
                                    purpose=(
                                        "novelty_check"
                                        if args.mode == "novelty_check"
                                        else "canonical"
                                    ),
                                    priority=1.0,
                                )
                                for query in args.query
                            ]
                            if args.query
                            else None
                        ),
                    )
                )
                state_store.save(state)
                _print_json(result.model_dump(mode="json"))
                return 0
            if literature_command == "verify":
                metadata = asyncio.run(
                    service.verify_paper(state.literature, args.paper_id)
                )
                state_store.save(state)
                _print_json(
                    {
                        "project_id": state.project.id,
                        "requested_id": args.paper_id,
                        "metadata": (
                            metadata.model_dump(mode="json") if metadata else None
                        ),
                        "status": _literature_status(state),
                    }
                )
                return 0
    except (
        FileNotFoundError,
        FileExistsError,
        KeyError,
        PermissionError,
        RuntimeError,
        ValueError,
    ) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
