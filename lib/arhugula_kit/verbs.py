"""The verb registry: every `arhugula` command as one value.

[LAW:one-source-of-truth] The argument parser, `arhugula --help`, and the generated
reference docs/reference/cli.md are all built from `Verb` values, so the reference cannot
describe a command the program does not have.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = ["GROUPS", "Arg", "Verb"]

Handler = Callable[[argparse.Namespace], int]


@dataclass(frozen=True)
class Arg:
    names: tuple[str, ...]
    help: str
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Verb:
    path: tuple[str, ...]  # ("project", "add")
    summary: str
    tier: str  # "runtime": drives a runtime capability; "kit": added by the kit
    handler: Handler
    args: tuple[Arg, ...] = ()
    example: str = ""
    detail: str = ""
    passthrough: bool = False  # unrecognized arguments go to the runtime tool unchanged


GROUPS: Mapping[str, str] = {
    "init": "Create or reconfigure the deployment.",
    "doctor": "Re-run the preflight checks; `--self-test` proves the runtime's refusals.",
    "upgrade": "Move the deployment to another upstream pin.",
    "relocate": "Move the deployment home to another directory.",
    "uninstall": "Remove the deployment.",
    "project": "Attach project repositories and choose the current one.",
    "run": "Run a workflow.",
    "resume": "Resume a paused workflow.",
    "gate": "Answer a workflow that paused at an approval gate.",
    "status": "Show the most recent ledger entries.",
    "daemon": "Run the harness as a long-lived service.",
    "provider": "See, enable and check providers.",
    "routing": "Choose which provider and model serve which work.",
    "workflow": "List, create, validate and run workflow manifests.",
    "prompt": "Author and select versioned prompts.",
    "skill": "Manage the skills agents can load.",
    "validator": "Bind validators to workflow steps.",
    "mcp": "Connect Model Context Protocol (MCP) tool servers.",
    "policy": "Set what an approval gate may approve on its own.",
    "memory": "Review and manage what the harness remembers.",
    "pause": "Durable pause and resume, and its journals.",
    "webhook": "Deliver pause notifications to a URL.",
    "audit": "Sign and verify the audit ledger.",
    "observability": "The trace stack: collector, Tempo and Grafana.",
    "trace": "Browse and export traces from the local span store.",
    "collector": "The local span store the runtime writes.",
    "logs": "Read the deployment's run logs.",
    "eval": "The holdout evaluation loop and drift checks.",
    "state": "Inspect, back up and restore the state root.",
    "isolation": "Sandboxed tool execution.",
    "feature": "Switch named configuration features on and off.",
    "config": "Show the generated config and set any runtime key.",
    "agent": "Context files for agent CLIs that operate this deployment.",
}
