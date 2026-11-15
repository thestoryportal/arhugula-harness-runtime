"""Preflight: the checks that must hold before the kit writes or runs anything.

[LAW:one-type-per-behavior] One `Check` type; P1 to P18 are eighteen values in one table.
`init`, `doctor` and docs/install.md all read the table. A check reports; it never fixes.
Where a fix is one safe command, the finding carries it as an offer that `init` may run
after the operator agrees.

[LAW:no-silent-failure] A failed check stops init before anything is written, with the
failure and its fix on the screen. A warning is printed and init goes on.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from arhugula_kit import dependencies, detect, lima, providers, runtime, vm
from arhugula_kit.detect import Machine
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.layout import KIT_ROOT, STACK_PORTS, Home

__all__ = [
    "CHECKS", "Check", "Finding", "Level", "Stage", "Subject",
    "placeholder_finding", "project_finding", "report", "run_stage",
]

LEGACY_STATE = (
    "onboarding/state-ledger",
    "memory",
    "memories",
    "memories.db",
    "memories-encrypted",
    "effect-fence",
    "engine-recovery-segments",
    "engine-recovery-reconciler",
    "protected-results",
)


class Level(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "FAIL"
    SKIP = "skip"


class Stage(StrEnum):
    MACHINE = "machine"  # before anything is installed or written
    INSTALLED = "installed"  # needs the runtime environment
    GENERATED = "generated"  # needs the generated configs and the stamped state root


@dataclass(frozen=True)
class Finding:
    level: Level
    detail: str
    fix: str = ""
    offer: tuple[str, ...] = ()  # one command init may run, with consent, to make the check pass


@dataclass(frozen=True)
class Subject:
    """What a check looks at: the machine, the answers, and the home they describe."""

    machine: Machine
    answers: Mapping[str, Any]
    home: Home
    initializing: bool = False  # init is running and will start what the answers ask for

    @property
    def selected(self) -> tuple[str, ...]:
        return tuple(self.answers["providers"])

    @property
    def required(self) -> tuple[str, ...]:
        return tuple(n for n in (self.answers["primary"], self.answers["fallback"]) if n)

    @property
    def features(self) -> tuple[str, ...]:
        return tuple(self.answers["features"])

    @property
    def engine(self) -> str:
        return str(self.answers["observability"]["engine"])

    def vm_ref(self) -> lima.VmRef | None:
        return vm.ref_of(self.answers["observability"], self.home)

    def instance(self) -> lima.Instance | None:
        ref = self.vm_ref()
        return lima.find(ref) if ref is not None else None


@dataclass(frozen=True)
class Check:
    id: str
    title: str
    stage: Stage
    run: Callable[[Subject], Finding]
    fails_when: str  # for docs/install.md: the condition, in words
    fix: str  # for docs/install.md: what the operator does about it
    applies_when: str = "always"


OK = Finding(Level.OK, "")


def _ok(detail: str) -> Finding:
    return Finding(Level.OK, detail)


def _skip(reason: str) -> Finding:
    return Finding(Level.SKIP, reason)


def _setup_of(dependency_id: str) -> str:
    """The first setup command the dependency table gives for one dependency."""
    row = next(d for d in dependencies.DEPENDENCIES if d.id == dependency_id)
    return row.setup[0].command if row.setup else ""


def _dependency(dependency_id: str) -> Callable[[Subject], Finding]:
    """A preflight check that is one row of the dependency table."""

    def check(s: Subject) -> Finding:
        row = next(d for d in dependencies.DEPENDENCIES if d.id == dependency_id)
        state = row.check(s.machine, s.home)
        if state.ready:
            return _ok(state.detail)
        return Finding(Level.FAIL, state.detail, fix=_setup_of(dependency_id))

    return check


def _p2(s: Subject) -> Finding:
    for dependency_id in ("developer-tools", "git", "uv"):
        finding = _dependency(dependency_id)(s)
        if finding.level is not Level.OK:
            return finding
    return _ok(f"git at {s.machine.git}, uv at {s.machine.uv}")


def _p3(s: Subject) -> Finding:
    if s.machine.python312:
        return _ok(f"CPython {s.machine.python312} through uv")
    command = _setup_of("python")
    return Finding(Level.FAIL, "uv has no CPython 3.12", fix=command, offer=tuple(command.split()))


def _p4(s: Subject) -> Finding:
    free = detect.free_gib(s.home.root)
    creates_vm = s.engine == "kit" and s.instance() is None
    needed = dependencies.VM_FREE_GIB if creates_vm else dependencies.MIN_FREE_GIB
    if free < needed:
        return Finding(
            Level.FAIL,
            f"{free:.1f} GiB free under {s.home.root}; "
            + ("the install and the new virtual machine need" if creates_vm else "the install needs")
            + f" {needed:.0f} GiB",
            fix="free space on that volume, or choose another home",
        )
    return _ok(f"{free:.0f} GiB free")


def _p5(s: Subject) -> Finding:
    above = detect.checkout_above(s.home.root)
    if above is not None:
        return Finding(
            Level.FAIL,
            f"the home {s.home.root} is inside the git checkout at {above}; the runtime "
            "refuses a state root with a checkout above it (inside-checkout)",
            fix="choose a home outside every git checkout",
        )
    # A kit clone made directly inside the home is not a stranger: init copies it to
    # `<home>/kit` and goes on from there.
    here = (KIT_ROOT.name,) if KIT_ROOT.parent == s.home.root else ()
    strangers = detect.checkouts_inside(s.home.root, allowed=("kit", "upstream", *here))
    if strangers:
        return Finding(
            Level.FAIL,
            f"the home holds other git checkouts: {', '.join(str(p) for p in strangers)}",
            fix="choose an empty directory as the home",
        )
    return _ok("a plain directory, outside every git checkout")


def _p6(s: Subject) -> Finding:
    problems: list[str] = []
    fixes: list[str] = []
    level = Level.OK
    for name in s.selected:
        provider = providers.by_name(name)
        if provider.access is not providers.Access.CLI:
            continue
        state = s.machine.state_of(name)
        if state.status is providers.Status.READY:
            continue
        severity = Level.FAIL if name in s.required and not state.usable else Level.WARN
        level = Level.FAIL if Level.FAIL in (level, severity) else Level.WARN
        problems.append(f"{provider.title}: {state.status.value} ({state.detail})")
        fixes.append(state.fix or provider.caveat)
    if level is Level.OK:
        return _ok("every selected CLI provider is installed and signed in")
    return Finding(level, "; ".join(problems), fix="; ".join(f for f in fixes if f))


def _p7(s: Subject) -> Finding:
    if "ollama" not in s.selected:
        return _skip("Ollama is not selected")
    host, model = s.answers["ollama_host"], s.answers["ollama_model"]
    models = providers.ollama_models(host)
    severity = Level.FAIL if "ollama" in s.required else Level.WARN
    if models is None:
        return Finding(severity, f"no answer from Ollama at {host}", fix="ollama serve")
    if model not in models:
        return Finding(
            severity,
            f"Ollama answers at {host} but the model {model} is not pulled",
            fix=f"ollama pull {model}",
            offer=("ollama", "pull", model),
        )
    return _ok(f"Ollama answers at {host}; {model} is pulled")


def _nearest_existing(path: Path) -> Path:
    here = path
    while not here.exists():
        here = here.parent
    return here


def _p8(s: Subject) -> Finding:
    root = s.home.state
    text = str(root)
    if not root.is_absolute() or "~" in text or "$" in text:
        return Finding(Level.FAIL, f"the state root {text} must be a literal absolute path")
    if root.exists():
        if not root.is_dir():
            return Finding(Level.FAIL, f"{root} exists and is not a directory")
        mode = stat.S_IMODE(root.stat().st_mode)
        stamped = (root / ".arhugula-state-root").is_file()
        if root.stat().st_uid != os.getuid() or mode & 0o077:
            return Finding(
                Level.FAIL,
                f"{root} must be yours with mode 0700 (it is {oct(mode)})",
                fix=f"chmod 700 {root}",
            )
        if any(root.iterdir()) and not stamped:
            return Finding(
                Level.FAIL,
                f"{root} holds files but no state-root marker; the runtime will not adopt "
                "someone else's data (marker-missing)",
                fix="move those files away, or choose another home",
            )
        return _ok("stamped by the runtime" if stamped else "empty, mode 0700, yours")
    parent = _nearest_existing(root)
    info = parent.stat()
    if info.st_uid not in (os.getuid(), 0) or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        return Finding(
            Level.FAIL,
            f"{parent} must be owned by you or root and not writable by group or others "
            "(parent-unsafe)",
            fix=f"chmod go-w {parent}",
        )
    return _ok(f"absent; it will be created under {parent}")


def _p9(s: Subject) -> Finding:
    probe = _nearest_existing(s.home.state)
    answer = runtime.call(s.home, "filesystem-type", path=str(probe))["filesystem_type"]
    if answer in ("tmpfs", "ramfs"):
        return Finding(
            Level.FAIL,
            f"{probe} is on {answer}, which does not survive a restart (non-durable-fs)",
            fix="choose a home on a real disk volume",
        )
    if answer is None:
        return Finding(
            Level.FAIL,
            f"the runtime cannot determine the filesystem of {probe} (fs-undetermined)",
            fix="choose a home on a local APFS volume",
        )
    return _ok(f"{answer}")


def _legacy_state(project: Path) -> list[str]:
    found: list[str] = []
    for relative in LEGACY_STATE:
        place = project / ".harness" / relative
        if place.is_file() or (place.is_dir() and any(place.iterdir())):
            found.append(str(place))
    return found


def project_finding(project: Path) -> Finding:
    """P10 for one project path; also what `project add` checks."""
    if not project.is_dir():
        return Finding(Level.FAIL, f"{project} is not a directory")
    legacy = _legacy_state(project)
    if legacy:
        return Finding(
            Level.FAIL,
            "the project holds harness state from a checkout-local config, which the "
            f"runtime refuses once state lives in the home (legacy-state-present): "
            f"{', '.join(legacy)}",
            fix=f"arhugula state archive-legacy {project}",
        )
    if not (project / ".git").exists():
        return Finding(Level.WARN, f"{project} is a plain directory, not a git checkout")
    return _ok("a git checkout with no leftover harness state")


def _p10(s: Subject) -> Finding:
    paths = [s.answers.get("project", "")] + [
        entry["path"] for entry in dict(s.answers.get("projects", {})).values()
    ]
    for path in dict.fromkeys(p for p in paths if p):
        finding = project_finding(Path(path))
        if finding.level is not Level.OK:
            return finding
    return _ok("no attached project holds leftover harness state") if any(paths) else _skip(
        "no project is attached"
    )


def _p11(s: Subject) -> Finding:
    configs = [s.home.deployment_config, *sorted((s.home.config / "projects").glob("*.toml"))]
    for config in configs:
        match runtime.ask(s.home, "load-config", config=str(config)):
            case runtime.Refusal(kind=kind, message=message):
                return Finding(Level.FAIL, f"the runtime refuses {config} ({kind}): {message}")
            case _:
                pass
    return _ok(f"{len(configs)} generated config(s) load through the runtime's own loader")


def placeholder_finding(files: list[Path]) -> Finding:
    """P12 for a list of generated files: none may still hold a placeholder or a `~`."""
    for path in files:
        body = "\n".join(
            line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("#")
        )
        if "{{" in body or '"~' in body or "/absolute/path/to" in body:
            return Finding(
                Level.FAIL,
                f"{path} still holds a placeholder or a `~`",
                fix="this is a kit defect; please file an issue with the file attached",
            )
    return _ok("no placeholder or `~` in any generated file")


def _p12(s: Subject) -> Finding:
    return placeholder_finding(
        [
            s.home.deployment_config,
            s.home.installation_state,
            *sorted((s.home.config / "projects").glob("*.toml")),
        ]
    )


def _p13(s: Subject) -> Finding:
    listening = detect.port_listening(STACK_PORTS["OTLP gRPC"])
    wanted = bool(s.answers["observability"]["enabled"])
    if listening and not wanted:
        return Finding(
            Level.WARN,
            "something listens on 127.0.0.1:4317 though the observability tier is off; "
            "the harness will send its traces there",
        )
    if not wanted:
        return _ok(
            "the observability tier is off: traces stay in the local span store, and each "
            "run prints a few trace-export retry lines, which are harmless"
        )
    if not listening and s.initializing:
        return _ok("the observability tier is on; init starts the trace stack after the install")
    if not listening:
        return Finding(
            Level.WARN,
            "the observability tier is on but nothing listens on 127.0.0.1:4317",
            fix="arhugula observability up",
        )
    return _ok("the trace endpoint is listening and the observability tier is on")


def _busy_ports() -> list[int]:
    return [port for port in STACK_PORTS.values() if detect.port_listening(port)]


def _p14(s: Subject) -> Finding:
    ref = s.vm_ref()
    if ref is None:
        return _skip("no virtual machine is chosen")
    lima_row = _dependency("lima")(s)
    if lima_row.level is not Level.OK:
        return lima_row
    if ref.kit_owned:
        budget = lima.socket_path_budget(ref.lima_home, ref.name)
        if budget < 0:
            return Finding(
                Level.FAIL,
                f"the home's path is {-budget} character(s) too long for the virtual machine: "
                "macOS limits a socket path to 104 bytes and Lima keeps its sockets under "
                f"{ref.lima_home / ref.name}",
                fix="choose a home with a shorter path",
            )
    instance = s.instance()
    if instance is None and not ref.kit_owned:
        return Finding(
            Level.FAIL,
            f"no Lima instance {ref.name!r} under {ref.lima_home}",
            fix="answer question 11 again; `kit` creates a VM for this machine",
        )
    if instance is not None and not instance.native:
        refusal = vm.emulation_refusal(instance)
        return Finding(Level.FAIL, refusal.message, fix=refusal.fix or "")
    if instance is None or not instance.running:
        busy = _busy_ports()
        if busy:
            return Finding(
                Level.FAIL,
                f"loopback port(s) {busy} are in use though the virtual machine is not "
                "running, so something else holds them",
                fix="find the owner with `lsof -nP -iTCP -sTCP:LISTEN` and stop it",
            )
        if instance is None:
            return _ok(
                f"the kit creates {ref.name} under {ref.lima_home} at the observability "
                "step, with Docker Engine, Compose and gVisor (5 to 10 minutes)"
            )
        return _ok(f"{instance.name} exists and is stopped; `observability up` starts it")
    engine = lima.probe_engine(instance)
    if engine is None:
        return Finding(
            Level.FAIL,
            f"no Docker engine answers inside {instance.name}",
            fix=f"LIMA_HOME={instance.lima_home} limactl shell {instance.name} docker info",
        )
    if not engine.compose_version:
        return Finding(
            Level.FAIL,
            f"`docker compose` is missing inside {instance.name}",
            fix="install the Docker Compose plugin inside the VM",
        )
    return _ok(f"Docker {engine.server_version}, Compose {engine.compose_version} inside {instance.name}")


def _p15(s: Subject) -> Finding:
    if not s.answers["isolation_tier3"]:
        return _skip("isolation tier 3 is off")
    if s.vm_ref() is None:
        return Finding(
            Level.FAIL,
            "isolation tier 3 needs a virtual machine",
            fix="answer question 11 with `kit`, or run `arhugula observability vm create`",
        )
    instance = s.instance()
    if instance is None or not instance.running:
        return _ok("gVisor is checked inside the virtual machine when the tier is enabled")
    engine = lima.probe_engine(instance)
    if engine is None or not engine.has_gvisor:
        return Finding(
            Level.FAIL,
            f"the Docker engine inside {instance.name} lists no `runsc` runtime",
            fix="install gVisor in the VM and register it with Docker under the name `runsc`",
        )
    return _ok("the VM's Docker engine lists the gVisor runtime `runsc`")


def _p16(s: Subject) -> Finding:
    if "audit-signing" not in s.features:
        return _skip("audit signing is off")
    keys = s.home.keys
    if keys.exists() and stat.S_IMODE(keys.stat().st_mode) & 0o077:
        return Finding(Level.FAIL, f"{keys} must be mode 0700", fix=f"chmod 700 {keys}")
    if not os.access(_nearest_existing(keys), os.W_OK):
        return Finding(Level.FAIL, f"cannot create {keys}")
    return _ok(f"{keys} is usable for the signing key")


def _p17(s: Subject) -> Finding:
    if "embedding-routing" not in s.features:
        return _skip("offline embedding routing is off")
    model = s.home.root / "models" / "bge-small-en-v1.5"
    if not (model / "SHA256SUMS").is_file():
        return Finding(
            Level.FAIL,
            f"the embedding model is not in place at {model} (with its SHA256SUMS)",
            fix="follow docs/configure.md, section `Offline embedding routing`, then run init again",
        )
    return _ok(f"embedding model and SHA256SUMS at {model}")


def _p18(s: Subject) -> Finding:
    match runtime.ask(s.home, "resolve-pause-journal", config=str(s.home.deployment_config)):
        case runtime.Refusal(kind=kind, message=message):
            return Finding(
                Level.FAIL,
                f"the pause-journal root does not resolve ({kind}): {message}",
                fix="arhugula init --reverify",
            )
        case value:
            return _ok(f"the pause-journal root resolves to {value['pause_journal_root']}")


CHECKS: tuple[Check, ...] = (
    Check("P1", "a supported macOS", Stage.MACHINE, _dependency("macos"),
          "the machine is not macOS 13 or later",
          "none: the kit runs on macOS only"),
    Check("P2", "the developer tools, git and uv are installed", Stage.MACHINE, _p2,
          "the Xcode Command Line Tools, `git` or `uv` is missing",
          "`xcode-select --install`; `brew install uv`"),
    Check("P3", "CPython 3.12 is available through uv", Stage.MACHINE, _p3,
          "uv has no CPython 3.12",
          "`uv python install 3.12` (init offers to run it)"),
    Check("P4", "enough free disk space under the home", Stage.MACHINE, _p4,
          "less than 3 GiB is free, or less than 12 GiB when init is about to create the virtual machine",
          "free space on that volume, or choose another home"),
    Check("P5", "the home is outside every git checkout", Stage.MACHINE, _p5,
          "the home is inside a git checkout, or holds a checkout other than `kit` and `upstream`",
          "choose a plain directory outside every git checkout"),
    Check("P6", "each selected CLI provider is installed and signed in", Stage.MACHINE, _p6,
          "the default or fallback provider's CLI is missing or signed out (any other selected one is a warning)",
          "install the CLI and sign in with its own command; `arhugula provider check` shows each"),
    Check("P7", "Ollama answers and has the model", Stage.MACHINE, _p7,
          "Ollama does not answer, or the chosen model is not pulled, and the routing depends on Ollama",
          "`ollama serve`; `ollama pull <model>` (init offers to run it)", "Ollama is selected"),
    Check("P8", "the state root can be created safely", Stage.MACHINE, _p8,
          "`<home>/state` holds files the runtime did not stamp, is not yours with mode 0700, or its parent is writable by others",
          "the `chmod` line the check prints, or choose another home"),
    Check("P9", "the state root's filesystem is durable", Stage.INSTALLED, _p9,
          "the home is on a RAM disk, or the runtime cannot tell what filesystem it is on",
          "choose a home on a local APFS volume"),
    Check("P10", "the project has no leftover harness state", Stage.MACHINE, _p10,
          "the project holds a ledger or memory from an earlier setup that kept state inside the checkout",
          "`arhugula state archive-legacy <project>`", "a project is attached"),
    Check("P11", "the generated configs load in the runtime", Stage.GENERATED, _p11,
          "the runtime's own loader refuses a generated config",
          "the loader's message names the field; this is a kit defect if no verb of yours caused it"),
    Check("P12", "no placeholder is left in a generated file", Stage.GENERATED, _p12,
          "a generated file still holds `{{...}}` or a `~`",
          "a kit defect: file an issue with the file attached"),
    Check("P13", "the trace endpoint matches the observability answer", Stage.MACHINE, _p13,
          "never fails; it warns when the tier is on and nothing listens on 127.0.0.1:4317 outside "
          "init, or when the tier is off and something does listen there",
          "`arhugula observability up`"),
    Check("P14", "the virtual machine and its Docker engine", Stage.MACHINE, _p14,
          "Lima is missing or older than 2.0; the home's path is too long for the VM's sockets; the chosen "
          "instance does not exist or was built for another CPU; the stack's ports are held by something "
          "else; or no Docker engine with Compose answers inside the running VM",
          "`brew install lima`; answer `kit` at question 11; free the port the check names", "a VM is chosen"),
    Check("P15", "gVisor for isolation tier 3", Stage.MACHINE, _p15,
          "tier 3 is on and no virtual machine is chosen, or the VM's Docker engine lists no `runsc` runtime",
          "answer `kit` at question 11, or `arhugula observability vm create`", "tier 3 is on"),
    Check("P16", "the signing-key directory is usable", Stage.MACHINE, _p16,
          "`<home>/keys` is readable by others or cannot be created",
          "`chmod 700 <home>/keys`", "audit signing is on"),
    Check("P17", "the offline embedding model is in place", Stage.MACHINE, _p17,
          "the model directory or its `SHA256SUMS` file is missing under `<home>/models`",
          "follow `Offline embedding routing` in docs/configure.md", "embedding routing is on"),
    Check("P18", "the pause-journal root resolves", Stage.GENERATED, _p18,
          "the installation-state document names no existing pause-journal directory",
          "`arhugula init --reverify`"),
)


def run_stage(stage: Stage, subject: Subject) -> list[tuple[Check, Finding]]:
    return [(check, check.run(subject)) for check in CHECKS if check.stage is stage]


def report(
    results: list[tuple[Check, Finding]],
    *,
    out: Callable[[str], None] = print,
    consequence: str = "nothing was written",
) -> None:
    """Print each result; raise when any check failed, naming every failure and fix.

    `consequence` says what the failure means at the point it is reported.
    """
    for check, finding in results:
        # An `ok` line states what was found; the title would only repeat it.
        shown = finding.detail if finding.level is Level.OK and finding.detail else (
            check.title + (f": {finding.detail}" if finding.detail else ""))
        out(f"  {finding.level.value:4}  {check.id:3} {shown}")
        if finding.fix and finding.level in (Level.FAIL, Level.WARN):
            out(f"          fix: {finding.fix}")
    failed = [(c, f) for c, f in results if f.level is Level.FAIL]
    if failed:
        lines = [f"{c.id} {c.title}: {f.detail}" for c, f in failed]
        fixes = [f"{c.id}: {f.fix}" for c, f in failed if f.fix]
        raise KitError(
            Exit.PRECONDITION,
            f"preflight failed; {consequence}:\n  " + "\n  ".join(lines),
            fix="\n       ".join(fixes) or None,
        )
