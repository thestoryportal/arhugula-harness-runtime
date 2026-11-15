"""Projects: one harness install, many repositories."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from arhugula_kit import initflow, deploy, preflight, spec
from arhugula_kit.common import say, table
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.preflight import Level
from arhugula_kit.spec import Project
from arhugula_kit.verbs import Arg, Verb

GITIGNORE_LINE = ".harness/"


def _ignore_harness_dir(project: Path) -> str:
    """Add `.harness/` to the project's .gitignore unless it is already ignored."""
    ignore = project / ".gitignore"
    lines = ignore.read_text(encoding="utf-8").splitlines() if ignore.is_file() else []
    if any(line.strip() in (GITIGNORE_LINE, ".harness", "/.harness/", "/.harness") for line in lines):
        return f"{ignore} already ignores .harness/"
    with ignore.open("a", encoding="utf-8") as handle:
        prefix = "" if not lines or lines[-1] == "" else "\n"
        handle.write(f"{prefix}# Arhugula Harness working files (prompts, routing manifest, index)\n{GITIGNORE_LINE}\n")
    return f"added `{GITIGNORE_LINE}` to {ignore}"


def _add(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    path = Path(args.path).expanduser().resolve()
    finding = preflight.project_finding(path)
    if finding.level is Level.FAIL:
        raise KitError(Exit.PRECONDITION, finding.detail, fix=finding.fix or None)
    if finding.level is Level.WARN:
        say(f"note: {finding.detail}")
    name = args.name or spec.project_name_for(path)
    if name in deployment.spec.projects:
        raise KitError(
            Exit.PRECONDITION,
            f"a project named {name!r} is already attached "
            f"({deployment.spec.projects[name].path})",
            fix="pass --name to attach this one under another name",
        )
    workloads = tuple(args.workload) if args.workload else deployment.spec.workloads
    projects = {**deployment.spec.projects, name: Project(str(path), workloads)}
    changed = replace(
        deployment.spec,
        projects=projects,
        current_project=deployment.spec.current_project or name,
    )
    deployment = deploy.apply(deployment, changed)
    target = deployment.target(name)
    say(f"attached {name}: {path}")
    say(f"  config:  {target.config_file}")
    say(f"  state:   {target.state} (ledger and memory; tenant id `{name}`)")
    if args.gitignore:
        say(f"  {_ignore_harness_dir(path)}")
    else:
        say(f"  the harness writes working files under {path / '.harness'}; "
            "pass --gitignore to ignore them in git")
    if args.agent_context:
        from arhugula_kit import agentctx

        for line in agentctx.install(deployment, name):
            say(f"  {line}")
    say(f"  current project: {deployment.spec.current_project}")
    say(f"next: arhugula {initflow.first_run(deployment.spec, name)}")
    return Exit.OK


def _list(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    if not deployment.spec.projects:
        say("no project is attached. Attach one with: arhugula project add <path>")
        return Exit.OK
    table(
        [
            (
                "*" if name == deployment.spec.current_project else "",
                name,
                project.path,
                ",".join(project.workloads),
            )
            for name, project in sorted(deployment.spec.projects.items())
        ],
        header=("", "name", "path", "workload classes"),
    )
    return Exit.OK


def _use(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    name = "" if args.name == "default" else args.name
    if name:
        deployment.target(name)
    deploy.apply(deployment, replace(deployment.spec, current_project=name))
    say(f"current project: {name or 'the deployment default'}")
    return Exit.OK


def _show(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = deployment.target("" if args.name == "default" else args.name)
    say(f"name:        {target.label}")
    say(f"repository:  {target.repository}")
    say(f"config:      {target.config_file}")
    say(f"state:       {target.state}")
    say(f"ledger:      {target.state / 'state-ledger' / 'state.jsonl'}")
    say(f"tenant id:   {target.tenant_id or '(none)'}")
    say(f"workloads:   {', '.join(target.workloads)}")
    return Exit.OK


def _remove(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = deployment.target(args.name)
    projects = {n: p for n, p in deployment.spec.projects.items() if n != args.name}
    overlays = {n: o for n, o in deployment.spec.project_overlays.items() if n != args.name}
    current = "" if deployment.spec.current_project == args.name else deployment.spec.current_project
    deploy.apply(
        deployment,
        replace(deployment.spec, projects=projects, project_overlays=overlays, current_project=current),
    )
    say(f"detached {args.name}. Its config is removed.")
    say(f"Its ledger and memory are kept at {target.state}; delete that directory yourself "
        "when you no longer need them.")
    return Exit.OK


VERBS: tuple[Verb, ...] = (
    Verb(
        path=("project", "add"),
        summary="Attach a project repository to this deployment.",
        tier="runtime",
        handler=_add,
        args=(
            Arg(("path",), "the project repository"),
            Arg(("--name",), "the project's name and tenant id (default: from the directory name)", {}),
            Arg(("--workload",), "a workload class to bind; repeat for several (default: the deployment's)", {"action": "append", "choices": spec.WORKLOADS}),
            Arg(("--gitignore",), "add `.harness/` to the project's .gitignore", {"action": "store_true"}),
            Arg(("--agent-context",), "append the harness section to the project's CLAUDE.md and AGENTS.md", {"action": "store_true"}),
        ),
        example="arhugula project add ~/code/my-service --gitignore --agent-context",
        detail="The project gets its own config, ledger, memory and tenant id. The harness itself is not copied into it.",
    ),
    Verb(("project", "list"), "List attached projects; `*` marks the current one.", "kit", _list, example="arhugula project list"),
    Verb(
        ("project", "use"),
        "Choose the project that verbs act on by default.",
        "kit",
        _use,
        (Arg(("name",), "an attached project, or `default` for the deployment default"),),
        example="arhugula project use my-service",
    ),
    Verb(
        ("project", "show"),
        "Show where a project's config, ledger and memory live.",
        "kit",
        _show,
        (Arg(("name",), "an attached project, or `default`"),),
        example="arhugula project show my-service",
    ),
    Verb(
        ("project", "remove"),
        "Detach a project. Its state is kept.",
        "kit",
        _remove,
        (Arg(("name",), "the project to detach"),),
        example="arhugula project remove my-service",
    ),
)
