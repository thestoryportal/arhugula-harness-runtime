"""`init`: ask, check, install, generate, prove.

The steps always run in this order, and each one either completes or stops init with the
failure and its fix:

    survey the machine -> dependencies (check, explain, offer, re-check) -> answers
    -> preflight (machine) -> install -> preflight (installed)
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
from collections.abc import Callable
from pathlib import Path
from typing import Any

from arhugula_kit import (
    audit_keys,
    dependencies,
    deploy,
    detect,
    preflight,
    proc,
    providers,
    questions,
    render,
    runtime,
    spec,
)
from arhugula_kit.detect import Machine
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.layout import KIT_ROOT, Home
from arhugula_kit.preflight import Level, Stage, Subject
from arhugula_kit.spec import Project, Spec

__all__ = ["first_run", "generate", "run_init", "smoke"]


def say(text: str = "") -> None:
    print(text, flush=True)


def _existing_raw(home: Home) -> dict[str, Any]:
    """The stored answers in the current shape, or nothing for a new deployment."""
    try:
        return spec.migrate(json.loads(home.spec_file.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return {}


def _preset(existing: dict[str, Any], say: Callable[[str], None] = say) -> dict[str, Any]:
    """The stored answers as defaults for asking again, without a provider the kit retired.

    The questions are asked anew, so a retired provider is left out here and said so; a
    default provider that was retired leaves question 3 to choose another.
    """
    retired = [name for name in existing.get("providers", ()) if name in providers.RETIRED]
    document = dict(existing)
    for name in retired:
        say(f"note: `{name}` is no longer a provider ({providers.RETIRED[name]}); it is left out of the answers below.")
        document = spec.without_provider(document, name)
        if document.get("primary") == name:
            document.pop("primary")
    return document


def _to_stderr(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def _interactive() -> bool:
    return sys.stdin.isatty()


def _agree(question: str) -> bool:
    """An offer to run a command: it runs only when the operator types yes."""
    return _confirm(question, default=False)


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
                if _agree(f"Run `{' '.join(finding.offer)}` now?"):
                    code = subprocess.call(list(finding.offer))
                    if code != 0:
                        raise KitError(
                            Exit.EXTERNAL_TOOL, f"`{' '.join(finding.offer)}` exited {code}"
                        )
                    results[index] = (check, check.run(subject))
    consequence = {
        Stage.MACHINE: "nothing was written",
        Stage.INSTALLED: "the environment is installed; no configuration was generated",
        Stage.GENERATED: "the configuration was generated but the deployment is not verified",
    }[stage]
    preflight.report(results, out=say, consequence=consequence)


def _answers(machine: Machine, args: argparse.Namespace, preset: dict[str, Any]) -> dict[str, Any]:
    if args.answers:
        try:
            given = json.loads(Path(args.answers).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise KitError(Exit.PRECONDITION, f"cannot read the answers file: {exc}") from exc
        placeholder = [key for key, value in given.items() if "/absolute/path/to" in json.dumps(value)]
        if placeholder:
            raise KitError(
                Exit.PRECONDITION,
                f"the answers file still holds the example's placeholder path in: {', '.join(placeholder)}",
                fix="replace every /absolute/path/to/... with a real path",
            )
        # The file answers the questions. Whatever else the deployment already carries
        # (attached projects, settings stored by verbs) stays, unless the file names it.
        given = spec.migrate(given)
        return {**preset, **given, **questions.complete(machine, given)}
    if args.yes or not _interactive():
        if not args.yes:
            raise KitError(
                Exit.PRECONDITION,
                "init needs a terminal to ask its questions",
                fix="run it in a terminal, or pass --answers <file> or --yes",
            )
        return _asked(preset, questions.ask_all(machine, preset=preset, accept_defaults=True, out=sys.stdout))
    return _asked(preset, questions.ask_all(machine, preset=preset))


def _asked(preset: dict[str, Any], asked: dict[str, Any]) -> dict[str, Any]:
    """Answers given at the prompts, over whatever the deployment already carried.

    Question 9 covers five features. One switched on with `arhugula feature enable` is
    not on its list, so asking again must not switch it off. (A provider added with
    `provider add` has no letter at question 2; that question keeps it selected itself, so
    questions 3 to 5 can choose it.)
    """
    offered = {name for _, name, _ in questions.FEATURE_LETTERS}
    kept = [name for name in preset.get("features", ()) if name not in offered]
    return {**preset, **asked, "features": [*asked["features"], *kept]}


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
    say("Init copies it there and runs once more from the copy, so the checks above print again.")
    say(f"When init has finished you can delete {KIT_ROOT}.")
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
    sys.stdout.flush()
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
    for directory in (home.config, home.logs, home.run):
        directory.mkdir(parents=True, exist_ok=True)
    # Backups hold copies of the private state root.
    home.backups.mkdir(mode=0o700, exist_ok=True)
    home.backups.chmod(0o700)
    if render.AUDIT_SIGNING in wanted.features and not audit_keys.present(home):
        # Signing was chosen: its keys must exist before the first run, which is a signed one.
        for line in audit_keys.generate(home):
            say(f"  {line}")
    deployment = deploy.apply(deploy.Deployment(home, wanted, render.fragments()), wanted)
    for target in render.targets(wanted, home):
        say(f"  wrote {target.config_file}")
    say(f"  wrote {render.write_installation_state(home)}")
    stamped = runtime.call(home, "bootstrap-state-root", config=str(home.deployment_config))
    say(f"  state root verified and stamped by the runtime: {stamped['state_root']}")
    home.pause_journal.mkdir(mode=0o700, exist_ok=True)
    say(f"  pause-journal root: {home.pause_journal}")
    # An agent CLI opened in the home itself finds the kit's instructions from here.
    (home.root / "AGENTS.md").write_text(
        "# Arhugula Harness deployment home\n\n"
        "This directory is a deployment of the Arhugula Harness. Before you act in it, read "
        "`kit/AGENTS.md`: it says how to operate the deployment and what never to do here.\n",
        encoding="utf-8",
    )
    # The kit's CLAUDE.md imports AGENTS.md and adds the few lines specific to Claude Code.
    (home.root / "CLAUDE.md").write_text("@kit/CLAUDE.md\n", encoding="utf-8")
    link = home.bin / "arhugula"
    home.bin.mkdir(exist_ok=True)
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(home.kit / "bin" / "arhugula")
    say(f"  command: {link}")
    return deployment


def first_run(wanted: Spec, project: str = "") -> str:
    """A run command that works on this deployment without spending anything it need not.

    Ollama's example when Ollama is enabled (a local model, no account); otherwise the
    one-step example on the default provider.
    """
    scope = f" --project {project}" if project else ""
    if "ollama" in wanted.providers:
        return f"run ollama-first.toml{scope} --provider ollama"
    return f"run minimal.toml{scope}"


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
            fix=f"{home.bin / 'arhugula'} doctor",
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

    if args.smoke:
        smoke(deploy.open_deployment(kit_home))
        return Exit.OK

    if args.reinstall and Path(sys.prefix).resolve() == kit_home.env.resolve():
        # `arhugula init --reinstall` runs inside the environment it is about to replace.
        # The kit's own `init` runs under uv instead, so hand over to it.
        program = str(kit_home.kit / "init")
        os.execv(program, [program, *sys.argv[sys.argv.index("init") + 1:]])

    def survey() -> Machine:
        return detect.survey(
            kit_home,
            ollama_host=existing.get("ollama_host", detect.OLLAMA_DEFAULT_HOST),
            lima_home=(existing.get("observability") or {}).get("lima_home") or None,
            added=spec.enabled_custom(existing),
        )

    # Standard error, so that `--questions-json` prints nothing but JSON on standard output.
    print("Surveying this machine (nothing is changed)...", file=sys.stderr, flush=True)
    machine = survey()
    if args.questions_json:
        print(
            json.dumps(
                {
                    "dependencies": dependencies.as_json(machine, kit_home),
                    "questions": questions.describe(machine, _preset(existing, say=_to_stderr)),
                },
                indent=2,
            )
        )
        return Exit.OK

    asking = _interactive() and not (args.answers or args.yes or args.reverify)
    machine = dependencies.run_stage(
        machine, kit_home, offer=asking, resurvey=survey, out=say, confirm=_agree
    )

    keep = bool(args.reverify)
    if keep and not existing:
        raise KitError(Exit.PRECONDITION, f"--reverify needs an answers file at {kit_home.spec_file}")
    if existing and not (keep or args.reconfigure or args.answers or args.yes) and _interactive():
        say(f"\nThis deployment is already configured ({kit_home.spec_file}).")
        keep = _confirm("Keep its answers and only re-verify?")
    # A relocated deployment finds itself by where its kit now sits; the stored home is stale.
    answers = {**existing, "home": str(kit_home.root)} if keep else _answers(machine, args, _preset(existing))
    # The one checkpoint for the answers, before anything is checked, installed or written.
    try:
        wanted = _spec_of(answers)
    except KitError as refused:
        raise KitError(refused.exit_code, f"the answers are not usable: {refused.message}", fix=refused.fix) from refused
    home = Home(Path(wanted.home))
    subject = Subject(machine, answers, home, initializing=True)

    _preflight(Stage.MACHINE, subject, offer=asking)
    _move_into_home(home, answers, args)
    _install(home, reinstall=args.reinstall)
    _preflight(Stage.INSTALLED, subject, offer=False)
    deployment = generate(home, wanted)
    _preflight(Stage.GENERATED, subject, offer=False)

    from arhugula_kit import isolation, observability

    if deployment.spec.observability.enabled:
        deployment = observability.up(deployment, out=say)
    if deployment.spec.isolation_tier3:
        deployment = isolation.enable_tier3(deployment, out=say)
    if deployment.spec.smoke:
        smoke(deployment)

    pending = home.config / "init-answers.pending.json"
    pending.unlink(missing_ok=True)
    say("\nThe deployment is ready.")
    say(f"  home:    {home.root}")
    say(f"  command: {home.bin / 'arhugula'}")
    say(f'  use it in this terminal:      export PATH="{home.bin}:$PATH"')
    say(f"""  keep it for new terminals:    echo 'export PATH="{home.bin}:$PATH"' >> ~/.zshrc""")
    say(f"  run a workflow:               arhugula {first_run(deployment.spec)}")
    say("  attach your own repository:   arhugula project add <path-to-a-repository>")
    return Exit.OK
