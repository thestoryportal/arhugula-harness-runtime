"""`init`: ask, check, install, generate, prove.

The steps always run in this order, and each one either completes or stops init with the
failure and its fix:

    survey the machine -> answers -> preflight (machine) -> install -> preflight (installed)
    -> generate and have the runtime accept every config -> stamp the state root
    -> preflight (generated) -> observability stack -> isolation tier 3 -> smoke runs

[LAW:no-ambient-temporal-coupling] The order is this module's, stated once here. The
state root is stamped by the runtime before the pause-journal directory is created inside
it, because the runtime refuses a root that holds files it did not stamp.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from arhugula_kit import deploy, detect, preflight, proc, questions, render, runtime, spec
from arhugula_kit.detect import Machine
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.layout import KIT_ROOT, Home
from arhugula_kit.preflight import Level, Stage, Subject
from arhugula_kit.spec import Project, Spec

__all__ = ["generate", "run_init", "smoke"]


def say(text: str = "") -> None:
    print(text, flush=True)


def _existing_raw(home: Home) -> dict[str, Any]:
    try:
        return json.loads(home.spec_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _interactive() -> bool:
    return sys.stdin.isatty()


def _confirm(question: str, *, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    answer = input(f"    {question} [{hint}]: ").strip().lower()
    return default if not answer else answer in ("y", "yes")


def _preflight(stage: Stage, subject: Subject, *, offer: bool) -> None:
    say(f"\nPreflight ({stage.value}):")
    results = preflight.run_stage(stage, subject)
    if offer:
        for index, (check, finding) in enumerate(results):
            if finding.level is Level.FAIL and finding.offer:
                say(f"  {check.id} {check.title}: {finding.detail}")
                if _confirm(f"Run `{' '.join(finding.offer)}` now?"):
                    code = subprocess.call(list(finding.offer))
                    if code != 0:
                        raise KitError(
                            Exit.EXTERNAL_TOOL, f"`{' '.join(finding.offer)}` exited {code}"
                        )
                    results[index] = (check, check.run(subject))
    preflight.report(results, out=say)


def _answers(machine: Machine, args: argparse.Namespace, preset: dict[str, Any]) -> dict[str, Any]:
    if args.answers:
        try:
            given = json.loads(Path(args.answers).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise KitError(Exit.PRECONDITION, f"cannot read the answers file: {exc}") from exc
        return {**given, **questions.complete(machine, given)}
    if args.yes or not _interactive():
        if not args.yes:
            raise KitError(
                Exit.PRECONDITION,
                "init needs a terminal to ask its questions",
                fix="run it in a terminal, or pass --answers <file> or --yes",
            )
        return {**preset, **questions.ask_all(machine, preset=preset, accept_defaults=True, out=sys.stdout)}
    return {**preset, **questions.ask_all(machine, preset=preset)}


def _spec_of(raw: dict[str, Any]) -> Spec:
    """The answers (with whatever an earlier spec carried) as a `Spec`."""
    document = {**raw, "format": spec.FORMAT}
    projects = dict(document.get("projects", {}))
    project_path = document.pop("project", "")
    if project_path:
        name = spec.project_name_for(Path(project_path))
        projects.setdefault(name, {"path": project_path, "workloads": list(document["workloads"])})
        document.setdefault("current_project", name)
    document["projects"] = projects
    return spec.parse(document, known_features=tuple(render.fragments()))


def _move_into_home(home: Home, answers: dict[str, Any], args: argparse.Namespace) -> None:
    """Continue from `<home>/kit` when this clone is somewhere else.

    The kit locates its home as the directory that contains it, so a deployment's kit
    must sit at `<home>/kit`.
    """
    if KIT_ROOT == home.kit:
        return
    if home.kit.exists():
        raise KitError(
            Exit.PRECONDITION,
            f"{home.kit} already exists and is not this kit clone",
            fix=f"run {home.kit / 'init'} instead, or choose another home",
        )
    say(f"\nThis kit clone is at {KIT_ROOT}. A deployment's kit lives at {home.kit}.")
    home.root.mkdir(parents=True, exist_ok=True)
    proc.require(
        proc.run(["git", "clone", "--quiet", str(KIT_ROOT), str(home.kit)], timeout=300),
        "cloning the kit into the home",
    )
    origin = proc.run(["git", "-C", str(KIT_ROOT), "remote", "get-url", "origin"])
    if origin.ok:
        proc.require(
            proc.run(["git", "-C", str(home.kit), "remote", "set-url", "origin", origin.stdout.strip()]),
            "pointing the home's kit at its origin",
        )
    pending = home.config / "init-answers.pending.json"
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text(json.dumps(answers, indent=2) + "\n", encoding="utf-8")
    flags = ["--answers", str(pending)] + (["--reinstall"] if args.reinstall else [])
    say(f"Continuing from {home.kit / 'init'}.")
    os.execv(str(home.kit / "init"), [str(home.kit / "init"), *flags])


def _install(home: Home, *, reinstall: bool) -> None:
    say("\nInstall:")
    words = [str(KIT_ROOT / "bin" / "install.sh"), str(home.root)] + (["--reinstall"] if reinstall else [])
    code = subprocess.call(words)
    if code != 0:
        raise KitError(
            Exit.EXTERNAL_TOOL,
            f"the install stopped (exit {code}); its message is above",
            fix=f"logs are under {home.logs}",
        )


def generate(home: Home, wanted: Spec) -> deploy.Deployment:
    """Write every generated file and prepare the state root, through the runtime."""
    say("\nGenerate:")
    for directory in (home.config, home.logs, home.run, home.backups):
        directory.mkdir(parents=True, exist_ok=True)
    deployment = deploy.apply(deploy.Deployment(home, wanted, render.fragments()), wanted)
    for target in render.targets(wanted, home):
        say(f"  wrote {target.config_file}")
    say(f"  wrote {render.write_installation_state(home)}")
    stamped = runtime.call(home, "bootstrap-state-root", config=str(home.deployment_config))
    say(f"  state root verified and stamped by the runtime: {stamped['state_root']}")
    home.pause_journal.mkdir(mode=0o700, exist_ok=True)
    say(f"  pause-journal root: {home.pause_journal}")
    link = home.bin / "arhugula"
    home.bin.mkdir(exist_ok=True)
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(home.kit / "bin" / "arhugula")
    say(f"  command: {link}")
    return deployment


def _smoke_run(home: Home, label: str, manifest: Path, config: Path, cwd: Path, extra: list[str]) -> None:
    outcome = runtime.run_tool(
        home.harness, ["run", manifest, "--config", config, *extra], cwd=cwd, timeout=600
    )
    status = next(
        (line.split(":", 1)[1].strip() for line in outcome.stdout.splitlines() if line.startswith("status:")),
        "no status",
    )
    say(f"  {label}: exit {outcome.code}, status: {status}")
    if outcome.code != 0 or status != "completed":
        raise KitError(
            Exit.WORKFLOW,
            f"the smoke run `{label}` did not complete:\n{outcome.last_lines(8)}",
            fix="arhugula doctor",
        )


def smoke(deployment: deploy.Deployment) -> None:
    """One short run per route: the primary, Ollama when selected, and the current project."""
    home, wanted = deployment.home, deployment.spec
    examples = home.upstream / "examples"
    say("\nSmoke runs:")
    primary_manifest = examples / ("ollama-first.toml" if wanted.primary == "ollama" else "minimal.toml")
    _smoke_run(
        home, f"primary route ({wanted.primary})", primary_manifest,
        home.deployment_config, home.upstream, [],
    )
    if "ollama" in wanted.providers and wanted.primary != "ollama":
        _smoke_run(
            home, "Ollama route", examples / "ollama-first.toml",
            home.deployment_config, home.upstream, ["--provider", "ollama"],
        )
    if wanted.current_project:
        target = deployment.target()
        route = ["--provider", "ollama"] if "ollama" in wanted.providers else []
        manifest = examples / ("ollama-first.toml" if route or wanted.primary == "ollama" else "minimal.toml")
        _smoke_run(
            home, f"project {target.name}", manifest, target.config_file, target.repository, route
        )


def run_init(args: argparse.Namespace) -> int:
    kit_home = Home.of_kit()
    existing = _existing_raw(kit_home)
    lima_home = (existing.get("observability") or {}).get("lima_home") or None

    if args.smoke:
        smoke(deploy.open_deployment(kit_home))
        return Exit.OK

    say("Surveying this machine (nothing is changed)...")
    machine = detect.survey(
        ollama_host=existing.get("ollama_host", detect.OLLAMA_DEFAULT_HOST), lima_home=lima_home
    )
    if args.questions_json:
        print(json.dumps(questions.describe(machine, existing), indent=2))
        return Exit.OK

    keep = bool(args.reverify)
    if keep and not existing:
        raise KitError(Exit.PRECONDITION, f"--reverify needs an answers file at {kit_home.spec_file}")
    if existing and not (keep or args.reconfigure or args.answers or args.yes) and _interactive():
        say(f"\nThis deployment is already configured ({kit_home.spec_file}).")
        keep = _confirm("Keep its answers and only re-verify?")
    # A relocated deployment finds itself by where its kit now sits; the stored home is stale.
    answers = {**existing, "home": str(kit_home.root)} if keep else _answers(machine, args, existing)
    home = Home(Path(answers["home"]))
    subject = Subject(machine, answers, home)

    _preflight(Stage.MACHINE, subject, offer=_interactive() and not args.answers)
    _move_into_home(home, answers, args)
    _install(home, reinstall=args.reinstall)
    _preflight(Stage.INSTALLED, subject, offer=False)
    deployment = generate(home, _spec_of(answers))
    _preflight(Stage.GENERATED, subject, offer=False)

    from arhugula_kit import isolation, observability

    if deployment.spec.observability.enabled:
        observability.up(deployment, out=say)
    if deployment.spec.isolation_tier3:
        deployment = isolation.enable_tier3(deployment, out=say)
    if deployment.spec.smoke:
        smoke(deployment)

    say("\nThe deployment is ready.")
    say(f"  home:    {home.root}")
    say(f"  command: {home.bin / 'arhugula'}")
    say(f'  add it to your shell:  export PATH="{home.bin}:$PATH"')
    say("  next:    arhugula project add <path-to-a-repository>")
    return Exit.OK
