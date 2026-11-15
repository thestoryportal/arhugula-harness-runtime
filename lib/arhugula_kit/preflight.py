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

from arhugula_kit import detect, lima, providers, runtime
from arhugula_kit.detect import Machine
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.layout import Home

__all__ = ["CHECKS", "Check", "Finding", "Level", "Stage", "Subject", "report", "run_stage"]

MIN_FREE_GIB = 3.0
STACK_PORTS = (3000, 3200, 4317, 4318)
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

    @property
    def selected(self) -> tuple[str, ...]:
        return tuple(self.answers["providers"])

    @property
    def required(self) -> tuple[str, ...]:
        return tuple(n for n in (self.answers["primary"], self.answers["fallback"]) if n)

    @property
    def features(self) -> tuple[str, ...]:
        return tuple(self.answers["features"])

    def instance(self) -> lima.Instance | None:
        chosen = self.answers["observability"]
        for candidate in self.machine.lima_instances:
            if candidate.name == chosen["instance"] and str(candidate.lima_home) == chosen["lima_home"]:
                return candidate
        return None


@dataclass(frozen=True)
class Check:
    id: str
    title: str
    stage: Stage
    run: Callable[[Subject], Finding]
    applies_when: str = "always"


OK = Finding(Level.OK, "")


def _ok(detail: str) -> Finding:
    return Finding(Level.OK, detail)


def _skip(reason: str) -> Finding:
    return Finding(Level.SKIP, reason)


def _p1(s: Subject) -> Finding:
    if (s.machine.system, s.machine.arch) == ("Darwin", "arm64"):
        return _ok("macOS on Apple silicon")
    return Finding(
        Level.WARN,
        f"{s.machine.system} {s.machine.arch}: this kit is witnessed on macOS arm64 only",
    )


def _p2(s: Subject) -> Finding:
    missing = [name for name, path in (("git", s.machine.git), ("uv", s.machine.uv)) if path is None]
    if missing:
        return Finding(
            Level.FAIL, f"not on PATH: {', '.join(missing)}", fix=f"brew install {' '.join(missing)}"
        )
    return _ok(f"git at {s.machine.git}, uv at {s.machine.uv}")


def _p3(s: Subject) -> Finding:
    if s.machine.python312:
        return _ok(f"CPython {s.machine.python312} through uv")
    return Finding(
        Level.FAIL,
        "uv has no CPython 3.12",
        fix="uv python install 3.12",
        offer=("uv", "python", "install", "3.12"),
    )


def _p4(s: Subject) -> Finding:
    free = detect.free_gib(s.home.root)
    if free < MIN_FREE_GIB:
        return Finding(
            Level.FAIL,
            f"{free:.1f} GiB free under {s.home.root}; the install needs {MIN_FREE_GIB:.0f} GiB",
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
    strangers = detect.checkouts_inside(s.home.root, allowed=("kit", "upstream"))
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


def _p12(s: Subject) -> Finding:
    files = [
        s.home.deployment_config,
        s.home.installation_state,
        *sorted((s.home.config / "projects").glob("*.toml")),
    ]
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


def _p13(s: Subject) -> Finding:
    listening = detect.port_listening(4317)
    wanted = bool(s.answers["observability"]["enabled"])
    if listening and not wanted:
        return Finding(
            Level.WARN,
            "something listens on 127.0.0.1:4317 though the observability tier is off; "
            "the harness will send its traces there",
        )
    if not listening and not wanted:
        return Finding(
            Level.WARN,
            "nothing listens on 127.0.0.1:4317: each run prints a few OTLP retry lines on "
            "stderr and keeps its traces in the local span store only",
        )
    return _ok("the trace endpoint matches the observability answer")


def _p14(s: Subject) -> Finding:
    chosen = s.answers["observability"]
    if not chosen["enabled"]:
        return _skip("the observability tier is off")
    if s.machine.limactl is None:
        return Finding(Level.FAIL, "limactl is not on PATH", fix="brew install lima")
    instance = s.instance()
    if instance is None:
        return Finding(
            Level.FAIL,
            f"no Lima instance {chosen['instance']!r} under {chosen['lima_home']}",
            fix="answer question 11 again with `<lima-home>::<instance>`",
        )
    busy = [port for port in STACK_PORTS if detect.port_listening(port)]
    if not instance.running:
        if busy:
            return Finding(
                Level.FAIL,
                f"loopback port(s) {busy} are in use while {instance.name} is stopped, so "
                "something else holds them",
                fix="find the owner with `lsof -nP -iTCP -sTCP:LISTEN` and stop it",
            )
        return Finding(
            Level.WARN,
            f"{instance.name} is stopped; `observability up` starts it and then checks its "
            "Docker engine",
        )
    engine = lima.probe_engine(instance)
    if engine is None:
        return Finding(
            Level.FAIL,
            f"no Docker engine answers inside {instance.name}",
            fix=f"LIMA_HOME={instance.lima_home} limactl shell {instance.name} docker info",
        )
    compose = engine.docker("compose", "version", timeout=60)
    if not compose.ok:
        return Finding(
            Level.FAIL,
            f"`docker compose` is missing inside {instance.name}",
            fix="install the Docker Compose plugin inside the VM",
        )
    return _ok(f"Docker {engine.server_version} with Compose inside {instance.name}")


def _p15(s: Subject) -> Finding:
    if not s.answers["isolation_tier3"]:
        return _skip("isolation tier 3 is off")
    instance = s.instance()
    if instance is None:
        return Finding(Level.FAIL, "isolation tier 3 needs the Lima instance from question 11")
    if not instance.running:
        return Finding(
            Level.WARN,
            f"{instance.name} is stopped; gVisor is checked when the tier is enabled",
        )
    engine = lima.probe_engine(instance)
    if engine is None or not engine.has_gvisor:
        return Finding(
            Level.FAIL,
            f"the Docker engine inside {instance.name} lists no `runsc` runtime",
            fix="install gVisor in the VM (upstream docs: deploy/images/README.md)",
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
                fix="run `arhugula init --reconfigure`",
            )
        case value:
            return _ok(f"the pause-journal root resolves to {value['pause_journal_root']}")


CHECKS: tuple[Check, ...] = (
    Check("P1", "macOS on Apple silicon", Stage.MACHINE, _p1),
    Check("P2", "git and uv are installed", Stage.MACHINE, _p2),
    Check("P3", "CPython 3.12 is available through uv", Stage.MACHINE, _p3),
    Check("P4", "at least 3 GiB free under the home", Stage.MACHINE, _p4),
    Check("P5", "the home is outside every git checkout", Stage.MACHINE, _p5),
    Check("P6", "each selected CLI provider is installed and signed in", Stage.MACHINE, _p6),
    Check("P7", "Ollama answers and has the model", Stage.MACHINE, _p7, "Ollama is selected"),
    Check("P8", "the state root can be created safely", Stage.MACHINE, _p8),
    Check("P9", "the state root's filesystem is durable", Stage.INSTALLED, _p9),
    Check("P10", "the project has no leftover harness state", Stage.MACHINE, _p10, "a project is attached"),
    Check("P11", "the generated configs load in the runtime", Stage.GENERATED, _p11),
    Check("P12", "no placeholder is left in a generated file", Stage.GENERATED, _p12),
    Check("P13", "the trace endpoint matches the observability answer", Stage.MACHINE, _p13),
    Check("P14", "the Lima engine for the observability tier", Stage.MACHINE, _p14, "the tier is on"),
    Check("P15", "gVisor for isolation tier 3", Stage.MACHINE, _p15, "tier 3 is on"),
    Check("P16", "the signing-key directory is usable", Stage.MACHINE, _p16, "audit signing is on"),
    Check("P17", "the offline embedding model is in place", Stage.MACHINE, _p17, "embedding routing is on"),
    Check("P18", "the pause-journal root resolves", Stage.GENERATED, _p18),
)


def run_stage(stage: Stage, subject: Subject) -> list[tuple[Check, Finding]]:
    return [(check, check.run(subject)) for check in CHECKS if check.stage is stage]


def report(results: list[tuple[Check, Finding]], *, out: Callable[[str], None] = print) -> None:
    """Print each result; raise when any check failed, naming every failure and fix."""
    for check, finding in results:
        out(f"  {finding.level.value:4}  {check.id:3} {check.title}"
            + (f": {finding.detail}" if finding.detail else ""))
        if finding.fix and finding.level in (Level.FAIL, Level.WARN):
            out(f"          fix: {finding.fix}")
    failed = [(c, f) for c, f in results if f.level is Level.FAIL]
    if failed:
        lines = [f"{c.id} {c.title}: {f.detail}" for c, f in failed]
        fixes = [f"{c.id}: {f.fix}" for c, f in failed if f.fix]
        raise KitError(
            Exit.PRECONDITION,
            "preflight failed; nothing was written:\n  " + "\n  ".join(lines),
            fix="\n       ".join(fixes) or None,
        )
