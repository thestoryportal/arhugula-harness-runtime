"""Memory verbs: the runtime's operator tool, plus a status view, a guided review and an export.

`status`, `review` and `export` are kit extensions. Every change to memory still goes
through the runtime's own operator tool, so its review-bound rules apply unchanged.
"""

from __future__ import annotations

import argparse
import getpass
import json
import time
from pathlib import Path
from typing import Any

from arhugula_kit import deploy, render, runtime
from arhugula_kit.common import PROJECT_ARG, say, table, target_of, write_private_archive
from arhugula_kit.deploy import Deployment
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.verbs import Arg, Verb
from arhugula_kit.verbs_config import rendered

KINDS = ("convention", "decision", "fact", "failure_learning", "procedural_update", "research")
INJECTION = ("never", "retrieval_only", "prompt_packet_allowed", "tool_allowed", "native_allowed")
OPERATOR_ARG = Arg(
    ("--operator",),
    "the name recorded on the operation (default: your login name)",
    {"default": getpass.getuser()},
)
RUN_ARG = Arg(("--run-id",), "the run that owns run-keyed records", {})


def _memory_root(deployment: Deployment, target: render.Target) -> Path:
    memory = rendered(deployment, target.name).get("memory", {})
    if not memory.get("enabled"):
        raise KitError(
            Exit.PRECONDITION,
            f"memory is off for {target.label}",
            fix="arhugula feature enable memory",
        )
    return Path(memory["root_path"])


def _operator(
    deployment: Deployment, target: render.Target, args: argparse.Namespace, words: list[str]
) -> list[str]:
    _memory_root(deployment, target)
    base = [
        "-m", "harness_runtime.admin.memory_operator",
        "--config", str(target.config_file),
        "--operator", args.operator,
    ]
    if getattr(args, "run_id", None):
        base += ["--run-id", args.run_id]
    return [*base, *words]


def _capture(deployment: Deployment, target: render.Target, args: argparse.Namespace, words: list[str]) -> Any:
    """Run the operator tool and parse its one JSON document; a refusal is the tool's own text."""
    outcome = runtime.run_tool(
        deployment.home.python, _operator(deployment, target, args, words), cwd=target.repository
    )
    if not outcome.ok:
        raise KitError(
            Exit.RUNTIME_REFUSED,
            f"the memory operator refused: {(outcome.stderr or outcome.stdout).strip()}",
        )
    return json.loads(outcome.stdout)


def _passthrough(command: str) -> Any:
    def handler(args: argparse.Namespace) -> int:
        deployment = deploy.open_deployment()
        target = target_of(deployment, args.project)
        words = [command, *args.passthrough]
        return runtime.exec_tool(
            deployment.home.python, _operator(deployment, target, args, words), cwd=target.repository
        )

    return handler


def _count(path: Path, pattern: str) -> int:
    return sum(1 for _ in path.glob(pattern)) if path.is_dir() else 0


def _status(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    root = _memory_root(deployment, target)
    memory = rendered(deployment, target.name)["memory"]
    say(f"project:        {target.label}")
    say(f"memory root:    {root}")
    say(f"prompt packet:  {'on' if memory.get('prompt_packet_enabled', True) else 'off'}"
        f" (budget {memory.get('token_budget', 1200)} tokens)")
    say(f"memory tools:   {'on' if memory.get('standard_tools_enabled', True) else 'off'}")
    say(f"native memory:  {'on' if memory.get('native_provider_enabled', False) else 'off'}")
    if not root.is_dir():
        say("\nno run has written memory yet.")
        return Exit.OK
    say("")
    table(
        [
            ("episodic runs", str(_count(root / "episodic" / "runs", "*"))),
            *[
                (f"semantic {kind}", str(_count(root / "semantic" / kind, "*")))
                for kind in ("facts", "preferences", "decisions", "conventions", "failures", "research")
            ],
            ("procedural snapshots", str(_count(root / "procedural" / "snapshots", "*"))),
            ("procedural promoted", str(_count(root / "procedural" / "promoted", "*"))),
        ],
        header=("kind", "records"),
    )
    operations = _capture(deployment, target, args, ["operations"])
    by_kind: dict[str, int] = {}
    for operation in operations:
        by_kind[operation["operation_kind"]] = by_kind.get(operation["operation_kind"], 0) + 1
    say(f"\noperation ledger: {len(operations)} entries "
        f"({', '.join(f'{k} {v}' for k, v in sorted(by_kind.items()))})")
    return Exit.OK


def _ask(prompt: str, allowed: tuple[str, ...], default: str) -> str:
    while True:
        answer = input(f"{prompt} [{default}]: ").strip() or default
        if answer in allowed:
            return answer
        say(f"  choose one of: {', '.join(allowed)}")


def _review(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    operations = _capture(deployment, target, args, ["operations"])
    captured = [
        (operation["run_id"], ref)
        for operation in reversed(operations)
        if operation["operation_kind"] == "capture"
        for ref in operation["memory_refs"]
        if ":episodic_turn:" in ref
    ]
    if not captured:
        say("nothing captured to review yet. Run a workflow with memory on first.")
        return Exit.OK
    say(f"{len(captured)} captured turn(s), newest first. For each one you may propose a memory.")
    say("Nothing becomes long-term memory until you approve it here.\n")
    proposed = approved = 0
    for run_id, source in captured[: args.limit]:
        args.run_id = run_id
        record = _capture(deployment, target, args, ["inspect", source])
        say(f"--- captured turn {source}")
        say(json.dumps(record, indent=2, sort_keys=True)[:1500])
        choice = _ask("\n[p]ropose a memory from this turn, [s]kip, [q]uit", ("p", "s", "q"), "s")
        if choice == "q":
            break
        if choice == "s":
            continue
        kind = _ask("kind: " + ", ".join(KINDS), KINDS, "fact")
        statement = input("statement (one sentence the harness should remember): ").strip()
        if not statement:
            say("  no statement; skipped")
            continue
        proposal = _capture(
            deployment, target, args,
            ["propose", source, "--kind", kind, "--statement", statement],
        )
        proposed += 1
        say(f"  proposed {proposal['memory_id']}")
        decision = _ask("[a]pprove now, [d]eny, [l]eave it proposed", ("a", "d", "l"), "a")
        if decision == "a":
            policy = _ask("how it may be used: " + ", ".join(INJECTION), INJECTION, "prompt_packet_allowed")
            _capture(
                deployment, target, args,
                ["approve", proposal["memory_id"], "--source", source, "--injection-policy", policy],
            )
            approved += 1
            say("  approved")
        elif decision == "d":
            reason = input("reason: ").strip() or "declined at review"
            _capture(
                deployment, target, args,
                ["deny", proposal["memory_id"], "--source", source, "--reason", reason],
            )
            say("  denied")
    say(f"\nreview done: {proposed} proposed, {approved} approved.")
    return Exit.OK


def _export(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    root = _memory_root(deployment, target)
    if not root.is_dir():
        raise KitError(Exit.PRECONDITION, f"{target.label} has no memory yet")
    archive = (
        Path(args.output).expanduser().resolve()
        if args.output
        else deployment.home.private_backups()
        / f"memory-{target.name or 'default'}-{time.strftime('%Y%m%dT%H%M%S')}.tar.gz"
    )
    write_private_archive(archive, lambda tar: tar.add(root, arcname="memory"))
    say(f"wrote {archive}")
    return Exit.OK


def _tool_verb(command: str, summary: str, example: str) -> Verb:
    return Verb(
        ("memory", command),
        summary,
        "runtime",
        _passthrough(command),
        (PROJECT_ARG, OPERATOR_ARG, RUN_ARG),
        example=example,
        passthrough=True,
        detail=(
            "Arguments the kit does not name go to the runtime's memory operator unchanged. "
            "docs/memory.md lists each one."
        ),
    )


VERBS: tuple[Verb, ...] = (
    Verb(
        ("memory", "status"),
        "Show where a project's memory lives and how much it holds.",
        "kit",
        _status,
        (PROJECT_ARG, OPERATOR_ARG),
        example="arhugula memory status",
    ),
    Verb(
        ("memory", "review"),
        "Walk through captured turns and propose, approve or deny memories.",
        "kit",
        _review,
        (
            PROJECT_ARG,
            OPERATOR_ARG,
            Arg(("--limit",), "how many captured turns to walk through (default: 10)", {"type": int, "default": 10}),
        ),
        example="arhugula memory review",
        detail="Every decision is made through the runtime's operator tool and is decided at most once.",
    ),
    Verb(
        ("memory", "export"),
        "Write a project's memory to an archive.",
        "kit",
        _export,
        (PROJECT_ARG, Arg(("--output",), "the archive to write (default: backups/memory-<project>-<time>.tar.gz)")),
        example="arhugula memory export",
    ),
    _tool_verb("operations", "Print the memory-operation ledger.", "arhugula memory operations"),
    _tool_verb("inspect", "Print one memory record.", "arhugula memory inspect <memory-id> --run-id <run-id>"),
    _tool_verb(
        "propose",
        "Propose a memory from captured evidence.",
        'arhugula memory propose <source-id> --kind fact --statement "The team deploys on Fridays." --run-id <run-id>',
    ),
    _tool_verb(
        "approve",
        "Activate a proposal.",
        "arhugula memory approve <proposal-id> --source <source-id> --injection-policy prompt_packet_allowed --run-id <run-id>",
    ),
    _tool_verb("deny", "Deny a proposal.", 'arhugula memory deny <proposal-id> --source <source-id> --reason "not true" --run-id <run-id>'),
    _tool_verb("redact", "Redact a record (a dry run unless --apply).", 'arhugula memory redact <memory-id> --reason "contains a secret" --apply'),
    _tool_verb("tombstone", "Tombstone a record (a dry run unless --apply).", 'arhugula memory tombstone <memory-id> --reason "obsolete" --apply'),
    _tool_verb("expire", "Expire a record (a dry run unless --apply).", 'arhugula memory expire <memory-id> --reason "out of date" --apply'),
    _tool_verb("migrate", "Migrate legacy filesystem callback memory (a dry run unless --apply).", "arhugula memory migrate --run-id <run-id> <legacy-root> /memories/notes.md --migration-id m1"),
    _tool_verb("compact", "Record compaction candidate dispositions (a dry run unless --apply).", 'arhugula memory compact --run-id <run-id> c1 --source <ids> --summary "merged duplicates"'),
)
