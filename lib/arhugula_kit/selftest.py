"""`arhugula doctor --self-test`: prove on this machine that refusals really refuse.

A deployment that only ever shows the success path proves nothing about its guard rails.
The self-test breaks one precondition at a time and expects the matching refusal:

- the runtime refuses a bad validator class, an unauthored prompt version, an exhausted
  fallback chain and a step deadline too short to meet (four real runs, on a scratch config);
- each preflight check fails, with its fix, when its precondition is broken;
- the dependency stage prints its guided message for a missing dependency and stops.

The deployment's configuration, ledgers, memory and traces are left as they were. Broken
inputs are values in memory or files under `<home>/run/selftest`; the four runs keep
their own ledger under `<home>/state/self-test`, write their spans to a scratch store and
send no trace to the collector. Both directories are removed afterwards.

[LAW:one-type-per-behavior] Every case is one `Case` value: what is broken, how, and the
text the refusal must carry. A new guard rail is a new row.
"""

from __future__ import annotations

import io
import re
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from arhugula_kit import dependencies, detect, overlay, preflight, providers, render, runtime, toml_out
from arhugula_kit.deploy import Deployment
from arhugula_kit.detect import Machine
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.layout import Home
from arhugula_kit.preflight import Level, Subject
from arhugula_kit.spec import Spec

__all__ = ["run"]

Say = Callable[[str], None]


@dataclass(frozen=True)
class Verdict:
    passed: bool
    seen: str  # what actually happened, for the report
    exercised: bool = True  # False: the case could not be run here, and `seen` says why


def _not_exercised(why: str) -> Verdict:
    return Verdict(True, f"not exercised: {why}", exercised=False)


@dataclass(frozen=True)
class Case:
    group: str
    name: str
    breaks: str  # the precondition that is broken, in words
    attempt: Callable[[], Verdict]


# --- runtime refusals: four real runs on a scratch config --------------------------------


SELF_TEST_STATE = "self-test"
NO_COLLECTOR = "http://127.0.0.1:9"  # the discard port: nothing listens there


def _scratch_config(deployment: Deployment, scratch: Path, name: str, spec: Spec) -> Path:
    """Render a config for one refused run, with its ledger, spans and traces kept apart."""
    home = deployment.home
    # Its own tenant as well as its own ledger: a pause journal is keyed by tenant and
    # workflow, so these runs cannot supersede a workflow the operator has on hold.
    target = replace(
        render.targets(spec, home)[0], state=home.state / SELF_TEST_STATE, tenant_id=SELF_TEST_STATE
    )
    apart = overlay.set_value(spec, "", ("runtime", "collector", "span_store_path"), str(scratch / "spans.sqlite"))
    apart = overlay.set_value(apart, "", ("runtime", "otel", "otlp_endpoint"), NO_COLLECTOR)
    document = render.render_config(apart, home, target, deployment.fragments)
    path = scratch / f"{name}.toml"
    path.write_text(toml_out.dumps(document, header="Self-test scratch config. Safe to delete."), encoding="utf-8")
    return path


def _refused_run(deployment: Deployment, config: Path, manifest: str, marker: str) -> Verdict:
    home = deployment.home
    outcome = runtime.run_tool(
        home.harness,
        ["run", home.upstream / "examples" / manifest, "--config", config],
        cwd=home.upstream,
        timeout=300,
    )
    text = outcome.stdout + outcome.stderr
    completed = re.search(r"^status:\s+completed\b", outcome.stdout, re.MULTILINE) is not None
    line = next((l.strip() for l in text.splitlines() if marker in l), "")
    if outcome.code != 0 and not completed and line:
        return Verdict(True, f"exit {outcome.code}: {line[:150]}")
    return Verdict(False, f"exit {outcome.code}, completed={completed}, no line carries {marker!r}:\n"
                   + "\n".join(text.splitlines()[-6:]))


def _runtime_cases(deployment: Deployment, scratch: Path) -> list[Case]:
    spec = deployment.spec
    if "ollama" not in spec.providers:
        skipped = _not_exercised("these four runs use the Ollama provider, which is not enabled")
        return [Case("runtime", name, "-", lambda: skipped) for name in
                ("bad validator class", "unauthored prompt version", "exhausted fallback chain", "step deadline")]
    # Every run goes to the local model: no account, no cost, and no fallback to hide a refusal.
    local = replace(spec, primary="ollama", fallback="")
    manifest = "ollama-first.toml"
    runtime_table = ("runtime",)

    def variant(name: str, changed: Spec) -> Path:
        return _scratch_config(deployment, scratch, name, changed)

    authored = "0" * 63 + "1"
    return [
        Case(
            "runtime", "bad validator class",
            "a validator binding names a class that cannot be imported",
            lambda: _refused_run(
                deployment,
                variant("validator", overlay.set_value(
                    local, "", (*runtime_table, "validator_framework_config", "bindings"),
                    [{"step_id": "ask-local-model",
                      "class_qualified_name": "arhugula_selftest:NoSuchValidator", "params": {}}])),
                manifest, "NoSuchValidator"),
        ),
        Case(
            "runtime", "unauthored prompt version",
            "the prompt selection names a version nobody authored",
            lambda: _refused_run(
                deployment,
                variant("prompt", overlay.set_value(
                    local, "", (*runtime_table, "prompt_selection_manifest"),
                    {"manifest_version": 1,
                     "per_workload_overrides": {"pipeline-automation": {"version_sha": "f" * 64}}})),
                manifest, "f" * 12),
        ),
        Case(
            "runtime", "exhausted fallback chain",
            "the only provider in the chain serves a model that does not exist",
            lambda: _refused_run(
                deployment,
                variant("exhausted", replace(local, models={**local.models, "ollama": "no-such-model:1b"})),
                manifest, "RT-FAIL-FALLBACK-EXHAUSTED"),
        ),
        Case(
            "runtime", "step deadline",
            # 10 ms, not the 300 ms a person would pick: no model call returns that fast, so
            # the refusal does not depend on how warm the model is.
            "a step may take 10 milliseconds and a model call takes longer",
            lambda: _refused_run(
                deployment,
                variant("deadline", overlay.set_value(
                    local, "", (*runtime_table, "step_dispatch_timeout_seconds"), 0.01)),
                manifest, "RT-FAIL-STEP-DISPATCH-TIMEOUT"),
        ),
    ]


# --- preflight: each check with its precondition broken ----------------------------------


def _scratch_home(real: Home, scratch: Path, name: str) -> Home:
    """A stand-in home that shares the real environment and upstream checkout."""
    root = scratch / name
    (root / "config" / "projects").mkdir(parents=True)
    (root / "env").symlink_to(real.env)
    (root / "upstream").symlink_to(real.upstream)
    return Home(root)


def _fails(check_id: str, subject: Subject, reason: str) -> Verdict:
    """The check must fail, and for the reason that was broken: `reason` is in its message."""
    check = next(c for c in preflight.CHECKS if c.id == check_id)
    finding = check.run(subject)
    if finding.level is Level.FAIL and reason in finding.detail:
        return Verdict(True, f"FAIL: {finding.detail[:110]}" + (f" | fix: {finding.fix[:70]}" if finding.fix else ""))
    return Verdict(False, f"{finding.level.value}: {finding.detail} (expected a failure naming {reason!r})")


def _preflight_cases(deployment: Deployment, machine: Machine, answers: Mapping[str, Any], scratch: Path) -> list[Case]:
    home = deployment.home
    base = Subject(machine, answers, home)

    def with_machine(**changes: Any) -> Subject:
        return Subject(replace(machine, **changes), answers, home)

    def with_answers(**changes: Any) -> Subject:
        return Subject(machine, {**answers, **changes}, home)

    def with_home(name: str, prepare: Callable[[Home], None]) -> Subject:
        stand_in = _scratch_home(home, scratch, name)
        prepare(stand_in)
        return Subject(machine, answers, stand_in)

    first_cli = next(
        (n for n in base.selected if providers.by_name(n).access is providers.Access.CLI), "claude_code"
    )
    signed_out = tuple(
        replace(state, status=providers.Status.NOT_SIGNED_IN, detail="signed out (simulated)")
        if state.provider.name == first_cli else state
        for state in machine.provider_states
    )
    kit_vm = {"enabled": True, "engine": "kit", "lima_home": "", "instance": ""}
    no_vm = {"enabled": False, "engine": "none", "lima_home": "", "instance": ""}

    def stray_files(stand_in: Home) -> None:
        stand_in.state.mkdir(mode=0o700)
        (stand_in.state / "someone-elses-file").write_text("x", encoding="utf-8")

    def loose_keys(stand_in: Home) -> None:
        stand_in.keys.mkdir(mode=0o755)
        stand_in.keys.chmod(0o755)

    def broken_config(stand_in: Home) -> None:
        stand_in.deployment_config.write_text('[runtime]\ndeployment_surface = "no-such-surface"\n', encoding="utf-8")

    def placeholder_left(stand_in: Home) -> None:
        stand_in.deployment_config.write_text('[runtime]\nrepository_root = "{{REPOSITORY}}"\n', encoding="utf-8")
        (stand_in.root / "env-etc").mkdir()

    def legacy_project(stand_in: Home) -> None:
        place = stand_in.root / "project" / ".harness" / "memory"
        place.mkdir(parents=True)
        (place / "record.json").write_text("{}", encoding="utf-8")

    def project_subject() -> Subject:
        subject = with_home("p10", legacy_project)
        return Subject(machine, {**answers, "project": str(subject.home.root / "project"), "projects": {}}, subject.home)

    def checkout_subject() -> Subject:
        subject = with_home("p5", lambda stand_in: (stand_in.root / ".git").mkdir())
        return subject

    rows: list[tuple[str, str, str, Callable[[], Subject]]] = [
        ("P1", "the machine is not a Mac", "macOS only",
         lambda: with_machine(system="Linux", macos_version="")),
        ("P2", "uv is not installed", "`uv` is not on PATH", lambda: with_machine(uv=None)),
        ("P3", "uv has no CPython 3.12", "no CPython 3.12", lambda: with_machine(python312="")),
        ("P5", "the home is inside a git checkout", "inside the git checkout", checkout_subject),
        ("P6", f"the default provider's CLI is signed out ({first_cli})", "signed out (simulated)",
         lambda: Subject(
             replace(machine, provider_states=signed_out),
             {**answers, "providers": list(dict.fromkeys([*base.selected, first_cli])), "primary": first_cli},
             home,
         )),
        ("P7", "Ollama does not answer", "no answer from Ollama",
         lambda: with_answers(providers=list(dict.fromkeys([*base.selected, "ollama"])), primary="ollama",
                              ollama_host=NO_COLLECTOR)),
        ("P8", "the state root holds files the runtime did not stamp", "marker-missing",
         lambda: with_home("p8", stray_files)),
        ("P10", "a project carries harness state from an earlier checkout-local setup",
         "legacy-state-present", project_subject),
        ("P11", "a generated config is one the runtime refuses", "the runtime refuses",
         lambda: with_home("p11", broken_config)),
        ("P14", "a virtual machine is chosen and Lima is not installed", "`limactl` is not on PATH",
         lambda: Subject(replace(machine, limactl=None, lima_version=None), {**answers, "observability": kit_vm}, home)),
        ("P15", "isolation tier 3 is on and no virtual machine is chosen", "needs a virtual machine",
         lambda: with_answers(isolation_tier3=True, observability=no_vm)),
        ("P16", "the signing-key directory is readable by others", "must be mode 0700",
         lambda: Subject(machine, {**answers, "features": [*base.features, "audit-signing"]},
                         with_home("p16", loose_keys).home)),
        ("P17", "embedding routing is on and the model is not in place", "embedding model is not in place",
         lambda: Subject(machine, {**answers, "features": [*base.features, "embedding-routing"]},
                         _scratch_home(home, scratch, "p17"))),
    ]
    cases = [
        Case("preflight", check_id, breaks,
             lambda check_id=check_id, build=build, reason=reason: _fails(check_id, build(), reason))
        for check_id, breaks, reason, build in rows
    ]

    def placeholder() -> Verdict:
        subject = with_home("p12", placeholder_left)
        # P12 also reads the installation-state document; give the stand-in an empty one.
        state_file = subject.home.root / "installation-state.json"
        state_file.write_text("{}", encoding="utf-8")
        finding = preflight.placeholder_finding([subject.home.deployment_config, state_file])
        return Verdict(finding.level is Level.FAIL, f"{finding.level.value}: {finding.detail[:120]}")

    cases.append(Case("preflight", "P12", "a generated file still holds a placeholder", placeholder))
    not_simulated = {
        "P4": "a full disk cannot be simulated safely; the check compares free space with the need",
        "P9": "a RAM disk would be needed; the check asks the runtime for the filesystem type",
        "P13": "this check only warns: it reports whether the trace endpoint is listening",
        "P18": "the installation-state document belongs to the real environment; breaking it "
        "would break the deployment. The runtime's refusal is covered by its own tests",
    }
    cases += [
        Case("preflight", check_id, "-", lambda why=why: _not_exercised(why))
        for check_id, why in not_simulated.items()
    ]
    return sorted(cases, key=lambda case: int(case.name[1:]))


# --- the dependency stage's guided message ------------------------------------------------


def _dependency_cases(deployment: Deployment, machine: Machine) -> list[Case]:
    home = deployment.home

    def guided(changes: dict[str, Any], must_stop: bool, title: str, command: str) -> Verdict:
        printed = io.StringIO()
        broken = replace(machine, **changes)
        stopped = False
        try:
            dependencies.run_stage(
                broken, home, offer=False, resurvey=lambda: broken,
                out=lambda line: print(line, file=printed),
            )
        except KitError:
            stopped = True
        text = printed.getvalue()
        shown = title in text and "what it is for:" in text and command in text
        if shown and stopped == must_stop:
            return Verdict(True, f"guide printed with `{command}`; init "
                           + ("stops" if stopped else "goes on, because it is optional"))
        return Verdict(False, f"guide shown={shown}, stopped={stopped} (expected {must_stop})")

    return [
        Case("dependencies", "missing required: uv", "uv is not installed",
             lambda: guided({"uv": None}, True, "uv", "brew install uv")),
        Case("dependencies", "missing required: developer tools", "the Xcode Command Line Tools are not installed",
             lambda: guided({"command_line_tools": ""}, True, "Xcode Command Line Tools", "xcode-select --install")),
        Case("dependencies", "missing optional: Lima", "Lima is not installed",
             lambda: guided({"limactl": None, "lima_version": None}, False, "Lima", "brew install lima")),
        Case("dependencies", "missing optional: Ollama", "Ollama is not installed",
             lambda: guided({"ollama_cli": None, "ollama_models": None}, False, "Ollama", "brew install ollama")),
    ]


def run(deployment: Deployment, *, say: Say = print) -> int:
    import json

    home = deployment.home
    scratch = home.run / "selftest"
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True)
    say("Surveying this machine (nothing is changed)...")
    machine = detect.survey(
        home, ollama_host=deployment.spec.ollama_host,
        lima_home=deployment.spec.observability.lima_home or None,
    )
    answers = json.loads(home.spec_file.read_text(encoding="utf-8"))
    failed = skipped = 0
    try:
        cases = (
            _dependency_cases(deployment, machine)
            + _preflight_cases(deployment, machine, answers, scratch)
            + _runtime_cases(deployment, scratch)
        )
        group = ""
        for case in cases:
            if case.group != group:
                group = case.group
                say(f"\n{group}:")
            verdict = case.attempt()
            failed += 0 if verdict.passed else 1
            skipped += 0 if verdict.exercised else 1
            word = "FAIL" if not verdict.passed else ("ok  " if verdict.exercised else "--  ")
            broke = f" [{case.breaks}]" if case.breaks != "-" else ""
            say(f"  {word}  {case.name}{broke}")
            say(f"        {verdict.seen}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        shutil.rmtree(home.state / SELF_TEST_STATE, ignore_errors=True)
    if failed:
        raise KitError(
            Exit.INTERNAL,
            f"{failed} self-test case(s) did not refuse as expected; the lines marked FAIL say what happened",
        )
    exercised = len(cases) - skipped
    say(f"\n{exercised} guard rail(s) refused as expected."
        + (f" {skipped} could not be exercised here; the lines marked -- say why." if skipped else ""))
    return Exit.OK
