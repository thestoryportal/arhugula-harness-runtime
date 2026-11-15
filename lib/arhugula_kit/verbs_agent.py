"""Agent verbs: the context section an agent CLI reads when it is opened in a project."""

from __future__ import annotations

import argparse
from pathlib import Path

from arhugula_kit import agentctx, deploy
from arhugula_kit.common import say
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.verbs import Arg, Verb

PROJECT_ARG = Arg(
    ("--project",),
    "the attached project whose files get the section (default: the current project)",
    {"metavar": "NAME"},
)


def _project(deployment: deploy.Deployment, given: str | None) -> str:
    name = given or deployment.spec.current_project
    if name not in deployment.spec.projects:
        raise KitError(
            Exit.PRECONDITION,
            "the context section belongs in an attached project; "
            + (f"no project is named {name!r}" if name else "no project is attached"),
            fix="arhugula project add <path>",
        )
    return name


def _install(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    for line in agentctx.install(deployment, _project(deployment, args.project)):
        say(line)
    say("An agent CLI opened in that project now knows how to drive the harness.")
    say("Agents that run inside a workflow do not read these files: see docs/authoring.md.")
    return Exit.OK


def _show(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    print(agentctx.section(deployment, _project(deployment, args.project)), end="")
    return Exit.OK


def _remove(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    name = _project(deployment, args.project)
    for line in agentctx.remove(Path(deployment.spec.projects[name].path)):
        say(line)
    return Exit.OK


VERBS: tuple[Verb, ...] = (
    Verb(
        ("agent", "context", "install"),
        "Write the harness section into a project's CLAUDE.md and AGENTS.md.",
        "kit",
        _install,
        (PROJECT_ARG,),
        example="arhugula agent context install --project my-project",
        detail=(
            "The section sits between two marker comments, so running the verb again "
            "replaces it and leaves the rest of each file alone."
        ),
    ),
    Verb(
        ("agent", "context", "show"),
        "Print the section that `agent context install` would write.",
        "kit",
        _show,
        (PROJECT_ARG,),
        example="arhugula agent context show",
    ),
    Verb(
        ("agent", "context", "remove"),
        "Remove the harness section from a project's CLAUDE.md and AGENTS.md.",
        "kit",
        _remove,
        (PROJECT_ARG,),
        example="arhugula agent context remove",
    ),
)
