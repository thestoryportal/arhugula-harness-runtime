"""Run, resume and inspect workflows; list, create and validate manifests."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from arhugula_kit import audit_keys, deploy, providers, render, runtime, servedby, workflows
from arhugula_kit.common import PROJECT_ARG, exec_logged, harness_command, resolve_manifest, say, table, target_of
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.spec import Spec
from arhugula_kit.verbs import Arg, Verb
from arhugula_kit.verbs_config import offers

DECISIONS = ("approve", "edit", "reject", "respond")


def _run(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    manifest = resolve_manifest(deployment, target, args.manifest)
    words: list[str | Path] = ["run", manifest, "--config", target.config_file]
    spec = deployment.spec
    model = args.model
    if args.provider and args.provider in spec.providers:
        provider = spec.provider(args.provider)
        if model:
            model = _note_unavailable(spec, provider, model)
        else:
            # The runtime pairs `--provider` alone with the model named in the manifest, which
            # belongs to another provider as often as not; the request then fails and the
            # fallback chain quietly serves the run. "Use this provider" means with the model
            # this deployment configured for it.
            model = spec.model_of(args.provider)
    for flag, value in (("--provider", args.provider), ("--model", model)):
        if value:
            words += [flag, value]
    if args.json:
        words += ["--output", "json"]
    if args.daemon:
        from arhugula_kit import daemon

        words += ["--daemon", "--socket-path", daemon.socket_path(deployment.home, target)]
    started = time.time_ns()
    code = _exec_harness(deployment, target, words, label="run")
    if args.provider and not args.daemon:
        line = servedby.after_run(deployment.home.span_store, started, args.provider, model or "")
        if line:
            _aside(line)
    return code


def _aside(text: str) -> None:
    """A line about a run, on standard error: standard output is the runtime's (`--json`)."""
    print(text, file=sys.stderr, flush=True)


def _note_unavailable(spec: Spec, provider: providers.Provider, model: str) -> str:
    """The model as the runtime is to get it: the tool's id, with any level.

    Refuses a model the provider's own tool refuses; notes one this deployment did not make
    available. A manifest may name any model, so an unavailable one is the operator's call,
    not a refusal.
    """
    offered = offers(spec, provider)
    try:
        chosen = providers.resolve(provider, model, offered)
    except providers.ModelRefused as refused:
        raise KitError(Exit.USAGE, str(refused), fix=f"arhugula provider models {provider.name}") from None
    available = spec.available(provider.name)
    if providers.model_id(provider, chosen.ref, offered) not in providers.available_ids(provider, available, offered):
        _aside(f"note: `{chosen.ref}` is not one of the models available for {provider.name} "
               f"({', '.join(available)}); it is passed on as given"
               f"{f' ({chosen.note})' if chosen.note else ''}. To make it available: "
               f"{providers.enable_command(provider.name, [*available, chosen.ref])}")
    return chosen.ref


def _exec_harness(deployment: deploy.Deployment, target: render.Target, words: list[str | Path], *, label: str) -> int:
    """Run the runtime's CLI for a target, attached to this terminal and logged."""
    argv, env = harness_command(deployment, target, words)
    return exec_logged(
        argv, cwd=target.repository, log_dir=deployment.home.logs,
        label=f"{label}-{target.name or 'default'}", env=env,
    )


def _resume_words(args: argparse.Namespace, decision: str | None) -> list[str]:
    words: list[str] = []
    if decision:
        words += ["--hitl-response", decision]
    for flag, value in (
        ("--edited-proposal", getattr(args, "edited_proposal", None)),
        ("--response-text", getattr(args, "response_text", None)),
        ("--rejection-reason", getattr(args, "reason", None)),
    ):
        if value:
            words += [flag, value]
    if getattr(args, "json", False):
        words += ["--output", "json"]
    return words


def _resume_with(args: argparse.Namespace, decision: str | None) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    manifest = resolve_manifest(deployment, target, args.manifest)
    words = ["resume", manifest, "--config", target.config_file, *_resume_words(args, decision)]
    return _exec_harness(deployment, target, words, label="resume")


def _resume(args: argparse.Namespace) -> int:
    return _resume_with(args, args.decision)


def _gate_approve(args: argparse.Namespace) -> int:
    return _resume_with(args, "approve")


def _gate_deny(args: argparse.Namespace) -> int:
    return _resume_with(args, "reject")


def _gate_list(args: argparse.Namespace) -> int:
    from arhugula_kit.verbs_authoring import journals

    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    listing = journals(deployment, target)
    found = listing.get("pause_journals", [])
    if not found:
        say("no pause journal exists: no workflow is paused.")
        return Exit.OK
    say(f"{len(found)} pause journal(s). Each MAY hold an outstanding pause:")
    for journal in found:
        say(f"  {json.dumps(journal, sort_keys=True)}")
    say("\nupstream limit: the journal records no pause-resolved marker, so this list is an "
        "upper bound, not an inventory of outstanding pauses.")
    say("answer one with:  arhugula gate approve <manifest>   or   "
        "arhugula gate deny <manifest> --reason <text>")
    return Exit.OK


def _status(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    ledger = target.state / "state-ledger" / "state.jsonl"
    if not ledger.is_file():
        say(f"{target.label}: no run has been recorded yet ({ledger} does not exist).")
        return Exit.OK
    return runtime.exec_tool(
        deployment.home.harness_inspect,
        [
            "--ledger-path", ledger,
            "--runtime-config", target.config_file,
            "--pause-journal-dir", deployment.home.pause_journal,
            "--last-n", str(args.last),
            *audit_keys.signature_inputs(deployment.home, target),
            *(["--json"] if args.json else []),
        ],
        cwd=target.repository,
    )


def _workflow_list(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    places = [("upstream examples", deployment.home.upstream / "examples")]
    if target.name:
        places.insert(0, (f"project {target.name}", target.repository / "workflows"))
    rows: list[tuple[str, str, str, str, str]] = []
    for label, directory in places:
        for manifest in workflows.manifests_in(directory):
            match runtime.ask(deployment.home, "validate-workflow", manifest=str(manifest)):
                case runtime.Refusal(kind=kind):
                    rows.append((label, manifest.name, "-", "-", f"does not load: {kind}"))
                case facts:
                    rows.append(
                        (label, manifest.name, facts["workflow_id"], facts["topology_pattern"],
                         f"{len(facts['steps'])} steps, {facts['workload_class']}")
                    )
    table(rows, header=("where", "file", "workflow id", "topology", "notes"))
    return Exit.OK


def _workflow_new(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    if not target.name and not args.output:
        raise KitError(
            Exit.PRECONDITION,
            "a new workflow belongs to a project, and no project is current",
            fix="arhugula project add <path>, or pass --output <file>",
        )
    destination = (
        Path(args.output).expanduser().resolve()
        if args.output
        else target.repository / "workflows" / f"{args.name}.toml"
    )
    if destination.exists():
        raise KitError(Exit.PRECONDITION, f"{destination} already exists; choose another --name")
    text = workflows.derive(deployment.home, deployment.spec, args.topology, args.name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    facts = runtime.call(deployment.home, "validate-workflow", manifest=str(destination))
    say(f"wrote {destination}")
    say(f"  {facts['topology_pattern']}, {len(facts['steps'])} steps, workload class "
        f"{facts['workload_class']}; it loads in the runtime")
    say(f"next: edit the prompts, then  arhugula run {destination.name}")
    return Exit.OK


def _workflow_validate(args: argparse.Namespace) -> int:
    deployment = deploy.open_deployment()
    target = target_of(deployment, args.project)
    manifest = resolve_manifest(deployment, target, args.manifest)
    match runtime.ask(deployment.home, "validate-workflow", manifest=str(manifest)):
        case runtime.Refusal(kind=kind, message=message):
            raise KitError(Exit.RUNTIME_REFUSED, f"{manifest} does not load ({kind}): {message}")
        case facts:
            say(f"{manifest} loads.")
            say(f"  workflow id:   {facts['workflow_id']}")
            say(f"  topology:      {facts['topology_pattern']}")
            say(f"  workload:      {facts['workload_class']}")
            if facts["workload_class"] not in target.workloads:
                say(f"  warning: {target.label} does not bind the workload class "
                    f"{facts['workload_class']}; a run would fail at bootstrap")
            spec = deployment.spec
            named = {step["binding"]["provider"] for step in facts["steps"]} & set(spec.providers)
            lists = {name: offers(spec, spec.provider(name)) for name in named}
            for step in facts["steps"]:
                binding = step["binding"]
                say(f"  step:          {step['step_id']} ({step['step_kind']}), bound to "
                    f"{binding['provider']}/{binding['model']}")
                note = _binding_note(spec, binding["provider"], binding["model"], lists.get(binding["provider"], ()))
                if note:
                    say(f"    note: {note}")
            say("  (a run is routed by the deployment's chain unless --provider is given; "
                "`arhugula routing show`)")
    return Exit.OK


def _binding_note(spec: Spec, name: str, model: str, offered: Sequence[providers.Offer]) -> str:
    """What a manifest's binding names that this deployment does not have, in words."""
    if name not in spec.providers:
        return f"{name} is not an enabled provider here (enabled: {', '.join(spec.providers)})"
    provider = spec.provider(name)
    available = spec.available(name)
    if providers.model_id(provider, model, offered) not in providers.available_ids(provider, available, offered):
        return (f"`{model}` is not one of the models available for {name} ({', '.join(available)}); "
                f"to make it available: {providers.enable_command(name, [*available, model])}")
    return ""


MANIFEST = Arg(("manifest",), "a manifest file, or its name in the project's workflows/ or upstream's examples/")

VERBS: tuple[Verb, ...] = (
    Verb(
        path=("run",),
        summary="Run a workflow on the current project.",
        tier="runtime",
        handler=_run,
        args=(
            MANIFEST,
            PROJECT_ARG,
            Arg(("--provider",), "dispatch every step to this enabled provider, for this run only", {}),
            Arg(("--model",), "dispatch every step to this model, for this run only", {}),
            Arg(("--daemon",), "send the run to the running daemon instead of starting a process", {"action": "store_true"}),
            Arg(("--json",), "print the full run result as JSON, including each step's reply", {"action": "store_true"}),
        ),
        example="arhugula run ollama-first.toml --provider ollama",
        detail=(
            "The config's first fallback chain serves every step. --provider and --model "
            "override it for one run; a manifest's own binding does not select the provider. "
            "The run's stderr is also written to the home's logs/ directory."
        ),
    ),
    Verb(
        path=("resume",),
        summary="Resume the latest durable pause of a workflow.",
        tier="runtime",
        handler=_resume,
        args=(
            MANIFEST,
            PROJECT_ARG,
            Arg(("--decision",), "the answer for a held approval gate", {"choices": DECISIONS}),
            Arg(("--edited-proposal",), "with --decision edit: a JSON object that replaces the payload", {}),
            Arg(("--response-text",), "with --decision respond: the response text", {}),
            Arg(("--reason",), "with --decision reject: the reason", {}),
            Arg(("--json",), "print the result or the refusal as JSON", {"action": "store_true"}),
        ),
        example="arhugula resume my-workflow.toml --decision approve",
        detail="Needs the durable pause feature: arhugula pause enable.",
    ),
    Verb(
        ("gate", "list"),
        "List the pause journals that may hold a paused workflow.",
        "runtime",
        _gate_list,
        (PROJECT_ARG,),
        example="arhugula gate list",
    ),
    Verb(
        ("gate", "approve"),
        "Approve the held gate of a paused workflow and continue it.",
        "runtime",
        _gate_approve,
        (MANIFEST, PROJECT_ARG),
        example="arhugula gate approve my-workflow.toml",
    ),
    Verb(
        ("gate", "deny"),
        "Reject the held gate of a paused workflow.",
        "runtime",
        _gate_deny,
        (MANIFEST, PROJECT_ARG, Arg(("--reason",), "why the action is rejected", {})),
        example='arhugula gate deny my-workflow.toml --reason "wrong branch"',
    ),
    Verb(
        ("status",),
        "Show the most recent entries of a project's state ledger.",
        "runtime",
        _status,
        (
            PROJECT_ARG,
            Arg(("--last",), "how many entries to show (default: 10)", {"type": int, "default": 10}),
            Arg(("--json",), "print the summary as JSON", {"action": "store_true"}),
        ),
        example="arhugula status --last 5",
    ),
    Verb(
        ("workflow", "list"),
        "List the manifests of the current project and of upstream's examples.",
        "runtime",
        _workflow_list,
        (PROJECT_ARG,),
        example="arhugula workflow list",
    ),
    Verb(
        ("workflow", "new"),
        "Create a manifest for a topology, derived from upstream's example for it.",
        "kit",
        _workflow_new,
        (
            Arg(("topology",), "the topology pattern", {"choices": tuple(workflows.TOPOLOGY_EXAMPLES)}),
            Arg(("--name",), "the workflow id and file name", {"required": True}),
            PROJECT_ARG,
            Arg(("--output",), "write to this file instead of the project's workflows/ directory", {}),
        ),
        example="arhugula workflow new evaluator-optimizer --name tagline-review",
    ),
    Verb(
        ("workflow", "validate"),
        "Load a manifest through the runtime's loader. No provider is called.",
        "runtime",
        _workflow_validate,
        (MANIFEST, PROJECT_ARG),
        example="arhugula workflow validate tagline-review.toml",
    ),
    Verb(
        ("workflow", "run"),
        "Run a workflow (the same as `arhugula run`).",
        "runtime",
        _run,
        (
            MANIFEST,
            PROJECT_ARG,
            Arg(("--provider",), "dispatch every step to this enabled provider, for this run only", {}),
            Arg(("--model",), "dispatch every step to this model, for this run only", {}),
            Arg(("--daemon",), "send the run to the running daemon", {"action": "store_true"}),
            Arg(("--json",), "print the full run result as JSON", {"action": "store_true"}),
        ),
        example="arhugula workflow run tagline-review.toml",
    ),
)
