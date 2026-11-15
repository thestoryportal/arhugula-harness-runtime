"""The dependencies: everything a deployment needs on the machine, as one table.

[LAW:one-source-of-truth] `DEPENDENCIES` is the only statement of what must be installed,
what each thing is for, how to check it and how to set it up. Init's dependency stage,
`arhugula doctor`, `init --questions-json` and the dependency section of docs/install.md
are renderings of it, so the guide on the screen and the guide on the page cannot disagree.

[LAW:one-type-per-behavior] One `Dependency` type. The provider rows are derived from the
provider catalogue, which already states each tool's install and sign-in commands.

The stage never installs anything on its own. It checks, explains, and where a setup step
is one safe command it offers to run that command; the operator answers each offer.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from arhugula_kit import detect, lima, proc, providers
from arhugula_kit.detect import Machine
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.layout import Home

__all__ = [
    "DEPENDENCIES",
    "MIN_FREE_GIB",
    "MIN_MACOS",
    "VM_FREE_GIB",
    "Dependency",
    "Need",
    "Setup",
    "State",
    "as_json",
    "markdown",
    "report",
    "run_stage",
]

MIN_MACOS = 13
MIN_FREE_GIB = 3.0
VM_FREE_GIB = 12.0
"""Free space for the install plus the kit's virtual machine and its container images."""


class Need(StrEnum):
    REQUIRED = "required"  # init cannot continue without it
    CHOICE = "optional"  # needed only by something the operator may choose
    ADVISORY = "checked again later"  # shown here; preflight repeats it once the home is known


@dataclass(frozen=True)
class Setup:
    command: str  # exactly what the operator types in a terminal
    offered: bool = False  # init may run it, after the operator agrees to this command


@dataclass(frozen=True)
class State:
    ready: bool
    detail: str


@dataclass(frozen=True)
class Dependency:
    id: str
    title: str
    purpose: str
    need: Need
    needed_for: str  # in words; "every deployment" for a required one
    check_by_hand: str  # the terminal command that shows whether it is in place
    check: Callable[[Machine, Home], State]
    setup: tuple[Setup, ...] = ()
    in_order: bool = False  # the setup commands are steps to run in order, not alternatives
    then: str = ""  # what to do after the setup command, in words (sign in, start it)


def _macos(machine: Machine, home: Home) -> State:
    if machine.system != "Darwin":
        return State(
            False,
            f"this is {machine.system}. The kit runs on macOS only: it uses zsh, the macOS "
            "keychain and Lima's macOS virtual machines",
        )
    major = int(machine.macos_version.split(".")[0] or 0)
    chip = {"arm64": "Apple silicon", "x86_64": "Intel"}.get(machine.arch, machine.arch)
    if major < MIN_MACOS:
        return State(False, f"macOS {machine.macos_version}; version {MIN_MACOS} or later is needed")
    untested = "" if machine.arch == "arm64" else " (the kit is witnessed on Apple silicon; Intel is untested)"
    return State(True, f"macOS {machine.macos_version} on {chip}{untested}")


def _developer_tools(machine: Machine, home: Home) -> State:
    if machine.command_line_tools:
        return State(True, machine.command_line_tools)
    return State(False, "no developer directory is selected")


def _git(machine: Machine, home: Home) -> State:
    return State(True, str(machine.git)) if machine.git else State(False, "`git` is not on PATH")


def _homebrew(machine: Machine, home: Home) -> State:
    return State(True, str(machine.brew)) if machine.brew else State(False, "`brew` is not on PATH")


def _uv(machine: Machine, home: Home) -> State:
    return State(True, str(machine.uv)) if machine.uv else State(False, "`uv` is not on PATH")


def _python(machine: Machine, home: Home) -> State:
    if machine.python312:
        return State(True, f"CPython {machine.python312}")
    return State(False, "uv has no CPython 3.12")


def _disk(machine: Machine, home: Home) -> State:
    free = detect.free_gib(home.root)
    return State(free >= MIN_FREE_GIB, f"{free:.0f} GiB free on the volume that holds {home.root}")


def _ollama(machine: Machine, home: Home) -> State:
    if machine.ollama_models is not None:
        return State(True, f"answers at {machine.ollama_host}; {len(machine.ollama_models)} model(s) pulled")
    if machine.ollama_cli is not None:
        return State(False, f"installed at {machine.ollama_cli}, but no server answers at {machine.ollama_host}")
    return State(False, "`ollama` is not on PATH")


_OLLAMA_MODEL = providers.by_name("ollama").default_model


def _ollama_model(machine: Machine, home: Home) -> State:
    if machine.ollama_models is None:
        return State(False, "the Ollama server does not answer, so its models cannot be listed")
    if _OLLAMA_MODEL in machine.ollama_models:
        return State(True, f"{_OLLAMA_MODEL} is pulled")
    return State(False, f"{_OLLAMA_MODEL} is not pulled (any other pulled model can be chosen at question 5)")


def _cli_provider(name: str) -> Callable[[Machine, Home], State]:
    def check(machine: Machine, home: Home) -> State:
        state = machine.state_of(name)
        return State(state.usable, f"{state.status.value}: {state.detail}")

    return check


def _any_provider(machine: Machine, home: Home) -> State:
    usable = machine.usable_providers
    if usable:
        return State(True, ", ".join(usable))
    return State(False, "no provider is installed and signed in, so no workflow step could run")


def _lima(machine: Machine, home: Home) -> State:
    if machine.limactl is None or machine.lima_version is None:
        return State(False, "`limactl` is not on PATH")
    shown = ".".join(str(part) for part in machine.lima_version)
    if machine.lima_version < lima.MINIMUM_VERSION:
        wanted = ".".join(str(part) for part in lima.MINIMUM_VERSION)
        return State(False, f"Lima {shown}; version {wanted} or later is needed")
    return State(True, f"Lima {shown}")


def _vm(machine: Machine, home: Home) -> State:
    vm, engine = machine.kit_vm, machine.kit_engine
    if vm is None:
        return State(False, "not created yet; answering `kit` at question 11 creates it")
    if not vm.running:
        return State(True, f"created at {vm.lima_home}; stopped (its engine is checked when it starts)")
    if engine is None:
        return State(False, f"{vm.name} is running but no Docker engine answers inside it")
    missing = [
        what
        for what, present in (("Docker Compose", engine.compose_version), ("gVisor `runsc`", engine.has_gvisor))
        if not present
    ]
    if missing:
        return State(False, f"Docker {engine.server_version} answers, but {' and '.join(missing)} is missing")
    return State(True, f"Docker {engine.server_version}, Compose {engine.compose_version}, gVisor runsc")


def _provider_rows() -> tuple[Dependency, ...]:
    rows = []
    for provider in providers.CATALOGUE:
        if provider.access is not providers.Access.CLI:
            continue
        rows.append(
            Dependency(
                id=provider.name,
                title=provider.title,
                purpose=f"Runs workflow steps through your own signed-in `{provider.command}`.",
                need=Need.CHOICE,
                needed_for=f"the provider `{provider.name}`",
                check_by_hand=f"{provider.command} --version",
                check=_cli_provider(provider.name),
                setup=tuple(Setup(command) for command in provider.install),
                then=f"Sign in by running `{provider.sign_in}`."
                + (f" {provider.caveat}" if provider.caveat else ""),
            )
        )
    return tuple(rows)


DEPENDENCIES: tuple[Dependency, ...] = (
    Dependency(
        id="macos",
        title=f"macOS {MIN_MACOS} or later",
        purpose="The kit is written for macOS, on Apple silicon or Intel.",
        need=Need.REQUIRED,
        needed_for="every deployment",
        check_by_hand="sw_vers -productVersion; uname -m",
        check=_macos,
    ),
    Dependency(
        id="developer-tools",
        title="Xcode Command Line Tools",
        purpose="Apple's developer tools. They provide git and the libraries other tools build on.",
        need=Need.REQUIRED,
        needed_for="every deployment",
        check_by_hand="xcode-select -p",
        check=_developer_tools,
        setup=(Setup("xcode-select --install", offered=True),),
        then="A system window opens. Finish the installation there, then run init again.",
    ),
    Dependency(
        id="git",
        title="git",
        purpose="Fetches the harness source at the pinned commit.",
        need=Need.REQUIRED,
        needed_for="every deployment",
        check_by_hand="git --version",
        check=_git,
        setup=(Setup("xcode-select --install", offered=True), Setup("brew install git", offered=True)),
    ),
    Dependency(
        id="homebrew",
        title="Homebrew",
        purpose="A package installer. It is only the suggested way to install the tools "
        "below; each one also has its own installer.",
        need=Need.CHOICE,
        needed_for="the `brew install` commands in this list",
        check_by_hand="brew --version",
        check=_homebrew,
        setup=(
            Setup(
                '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
            ),
        ),
        then="The installer asks for your password and prints two lines to add to your shell profile.",
    ),
    Dependency(
        id="uv",
        title="uv",
        purpose="Builds the harness and creates its private Python environment.",
        need=Need.REQUIRED,
        needed_for="every deployment",
        check_by_hand="uv --version",
        check=_uv,
        setup=(Setup("brew install uv", offered=True), Setup("curl -LsSf https://astral.sh/uv/install.sh | sh", offered=True)),
    ),
    Dependency(
        id="python",
        title="CPython 3.12, managed by uv",
        purpose="The Python the harness runs on. uv keeps it apart from the system Python.",
        need=Need.REQUIRED,
        needed_for="every deployment",
        check_by_hand="uv python find 3.12",
        check=_python,
        setup=(Setup("uv python install 3.12", offered=True),),
    ),
    Dependency(
        id="disk",
        title=f"{MIN_FREE_GIB:.0f} GiB of free disk space",
        purpose=f"Init wants {MIN_FREE_GIB:.0f} GiB free before it installs, and "
        f"{VM_FREE_GIB:.0f} GiB when it also creates the virtual machine. The install itself "
        "takes about half a gigabyte; the virtual machine with its container images takes about 5.",
        # Not blocking here: the home is chosen at question 1, and preflight P4 checks the
        # volume that will really hold it.
        need=Need.ADVISORY,
        needed_for="every deployment; preflight check P4 checks the home you choose",
        check_by_hand="df -h ~",
        check=_disk,
    ),
    Dependency(
        id="ollama",
        title="Ollama",
        purpose="Runs open-weight models on this machine. It needs no account and no network "
        "once a model is pulled.",
        need=Need.CHOICE,
        needed_for="the provider `ollama`",
        check_by_hand="curl -s http://127.0.0.1:11434/api/tags",
        check=_ollama,
        setup=(Setup("brew install ollama", offered=True), Setup("brew services start ollama", offered=True)),
        in_order=True,
        then="Without Homebrew, install the app from https://ollama.com/download and open it; "
        "`ollama serve` starts the server in a terminal.",
    ),
    Dependency(
        id="ollama-model",
        title=f"The Ollama model {_OLLAMA_MODEL}",
        purpose="The default local model (about 2 GB). Question 5 lets you choose another.",
        need=Need.CHOICE,
        needed_for="the provider `ollama` with its default model",
        check_by_hand="ollama list",
        check=_ollama_model,
        setup=(Setup(f"ollama pull {_OLLAMA_MODEL}", offered=True),),
    ),
    *_provider_rows(),
    Dependency(
        id="provider",
        title="At least one usable provider",
        purpose="A workflow step is a call to a model. One provider above must be installed "
        "and signed in. Ollama is the one that needs no account: set up the Ollama row and "
        "its model row, and this one is met.",
        need=Need.REQUIRED,
        needed_for="every deployment",
        check_by_hand="",
        check=_any_provider,
    ),
    Dependency(
        id="lima",
        title="Lima",
        purpose="Runs the small Linux virtual machine that holds the deployment's only "
        "Docker engine. Docker Desktop is not used.",
        need=Need.CHOICE,
        needed_for="the observability tier and isolation tier 3",
        check_by_hand="limactl --version",
        check=_lima,
        setup=(Setup("brew install lima", offered=True),),
        then="Without Homebrew, follow https://lima-vm.io/docs/installation/.",
    ),
    Dependency(
        id="vm",
        title="The kit's virtual machine: Docker Engine, Docker Compose and gVisor",
        purpose="Inside the Lima virtual machine, Docker Engine and Compose run the trace stack "
        "(collector, Tempo, Grafana). gVisor sandboxes tool calls at isolation tier 3. "
        "The kit installs all three when it creates the virtual machine.",
        need=Need.CHOICE,
        needed_for="the observability tier and isolation tier 3",
        check_by_hand="arhugula observability vm status",
        check=_vm,
        setup=(Setup("arhugula observability vm create"),),
        then="During init, answering `kit` at question 11 does the same.",
    ),
)


def report(machine: Machine, home: Home) -> list[tuple[Dependency, State]]:
    return [(dependency, dependency.check(machine, home)) for dependency in DEPENDENCIES]


def _label(index: int) -> str:
    return f"D{index}"


def _print_row(index: int, dependency: Dependency, state: State, out: Callable[[str], None]) -> None:
    word = "ok" if state.ready else {Need.REQUIRED: "MISSING", Need.CHOICE: "absent", Need.ADVISORY: "low"}[dependency.need]
    out(f"  {word:7}  {_label(index):3} {dependency.title}: {state.detail}")


def _print_guide(dependency: Dependency, out: Callable[[str], None]) -> None:
    """The guided message for a dependency that is not in place."""
    out(f"           what it is for: {dependency.purpose}")
    out(f"           needed for:     {dependency.needed_for}")
    joiner = "         then: " if dependency.in_order else "           or: "
    for position, setup in enumerate(dependency.setup):
        out(f"           {'set it up:     ' if position == 0 else joiner} {setup.command}")
    if dependency.then:
        out(f"           note:           {dependency.then}")
    if dependency.check_by_hand:
        out(f"           check by hand:  {dependency.check_by_hand}")


def run_stage(
    machine: Machine,
    home: Home,
    *,
    offer: bool,
    resurvey: Callable[[], Machine],
    out: Callable[[str], None] = print,
    confirm: Callable[[str], bool] | None = None,
) -> Machine:
    """Print every dependency, guide the operator through each missing one, and re-check.

    With `offer`, each offered setup command is proposed once and runs only on a yes.
    Returns the machine as surveyed after any setup ran. Raises when a required
    dependency is still missing.
    """
    out("\nDependencies (what this deployment needs on the machine):")
    for index, dependency in enumerate(DEPENDENCIES, start=1):
        state = dependency.check(machine, home)
        _print_row(index, dependency, state, out)
        if state.ready:
            continue
        _print_guide(dependency, out)
        for setup in dependency.setup:
            runnable = offer and setup.offered and proc.which(setup.command.split()[0]) is not None
            if not runnable or confirm is None or not confirm(f"Run `{setup.command}` now?"):
                continue
            code = subprocess.call(setup.command, shell=True)
            if code != 0:
                out(f"           `{setup.command}` exited {code}; nothing else was changed")
            machine = resurvey()
            state = dependency.check(machine, home)
            _print_row(index, dependency, state, out)
            if state.ready:
                break
    missing = [
        (index, dependency)
        for index, dependency in enumerate(DEPENDENCIES, start=1)
        if dependency.need is Need.REQUIRED and not dependency.check(machine, home).ready
    ]
    if missing:
        raise KitError(
            Exit.PRECONDITION,
            "init cannot continue until these are in place: "
            + "; ".join(f"{_label(index)} {dependency.title}" for index, dependency in missing),
            fix="follow the `set it up` lines above, then run init again",
        )
    return machine


def as_json(machine: Machine, home: Home) -> list[dict[str, Any]]:
    """The dependencies as data, for an agent to relay through its own surface."""
    return [
        {
            "id": dependency.id,
            "title": dependency.title,
            "purpose": dependency.purpose,
            "need": dependency.need.value,
            "needed_for": dependency.needed_for,
            "ready": state.ready,
            "detail": state.detail,
            "check_by_hand": dependency.check_by_hand,
            "setup": [setup.command for setup in dependency.setup],
            "then": dependency.then,
        }
        for dependency, state in report(machine, home)
    ]


def markdown() -> str:
    """The dependency section of docs/install.md: every dependency and its setup by hand."""
    lines: list[str] = []
    for index, dependency in enumerate(DEPENDENCIES, start=1):
        lines += [
            f"### {_label(index)}: {dependency.title}",
            "",
            f"{dependency.purpose}",
            "",
            f"- Needed for: {dependency.needed_for} ({dependency.need.value}).",
        ]
        if dependency.check_by_hand:
            lines.append(f"- Check: `{dependency.check_by_hand}`")
        if dependency.setup:
            lines += ["- Set it up:", "", "  ```sh"]
            lines += [f"  {setup.command}" for setup in dependency.setup[:1]]
            lines += ["  ```"]
            for setup in dependency.setup[1:]:
                lines += ["", "  Then:" if dependency.in_order else "  Or:", "", "  ```sh", f"  {setup.command}", "  ```"]
        if dependency.then:
            lines += ["", f"  {dependency.then}"]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
