"""What this machine has: the facts init's defaults and preflight checks are computed from.

[LAW:effects-at-boundaries] All probing of the machine happens here, once, and is handed
on as one immutable value. Questions and checks are then pure functions of it.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
from dataclasses import dataclass
from pathlib import Path

from arhugula_kit import lima, proc, providers

__all__ = ["Machine", "checkout_above", "checkouts_inside", "port_listening", "survey"]

OLLAMA_DEFAULT_HOST = "http://127.0.0.1:11434"


@dataclass(frozen=True)
class Machine:
    system: str
    arch: str
    git: Path | None
    uv: Path | None
    python312: str  # the uv-managed CPython 3.12 version, or "" when none
    limactl: Path | None
    provider_states: tuple[providers.ProviderState, ...]
    ollama_host: str
    ollama_models: tuple[str, ...] | None
    lima_instances: tuple[lima.Instance, ...]
    time_machine_destinations: tuple[str, ...]

    def state_of(self, name: str) -> providers.ProviderState:
        for state in self.provider_states:
            if state.provider.name == name:
                return state
        raise KeyError(name)

    @property
    def usable_providers(self) -> tuple[str, ...]:
        return tuple(s.provider.name for s in self.provider_states if s.usable)


def checkout_above(path: Path) -> Path | None:
    """The nearest directory at or above `path` that holds a `.git`, if any.

    The runtime refuses a state root with a git checkout above it (`inside-checkout`).
    """
    here = path.resolve()
    for directory in (here, *here.parents):
        if (directory / ".git").exists():
            return directory
    return None


def checkouts_inside(path: Path, *, allowed: tuple[str, ...]) -> tuple[Path, ...]:
    """Direct children of `path` that are git checkouts, other than the allowed names."""
    if not path.is_dir():
        return ()
    return tuple(
        child
        for child in sorted(path.iterdir())
        if child.name not in allowed and (child / ".git").exists()
    )


def port_listening(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((host, port)) == 0


def free_gib(path: Path) -> float:
    """Free space on the filesystem holding the nearest existing ancestor of `path`."""
    here = path
    while not here.exists():
        here = here.parent
    return shutil.disk_usage(here).free / 2**30


def _python312() -> str:
    outcome = proc.run(["uv", "python", "find", "3.12"], timeout=60)
    if not outcome.ok:
        return ""
    version = proc.run([outcome.stdout.strip(), "--version"], timeout=20)
    return version.stdout.strip().removeprefix("Python ") if version.ok else ""


def _time_machine() -> tuple[str, ...]:
    outcome = proc.run(["tmutil", "destinationinfo"], timeout=20)
    if not outcome.ok:
        return ()
    return tuple(
        line.split(":", 1)[1].strip()
        for line in outcome.stdout.splitlines()
        if line.strip().startswith("Mount Point")
    )


def survey(*, ollama_host: str = OLLAMA_DEFAULT_HOST, lima_home: str | None = None) -> Machine:
    """Probe the machine. Reads only: nothing is started, written or signed in."""
    host = os.environ.get("OLLAMA_HOST_URL", ollama_host)
    found: list[lima.Instance] = []
    if proc.which("limactl") is not None:
        for home in lima.candidate_homes(lima_home):
            found.extend(lima.instances(home))
    return Machine(
        system=platform.system(),
        arch=platform.machine(),
        git=proc.which("git"),
        uv=proc.which("uv"),
        python312=_python312() if proc.which("uv") else "",
        limactl=proc.which("limactl"),
        provider_states=tuple(
            providers.check(provider, ollama_host=host) for provider in providers.CATALOGUE
        ),
        ollama_host=host,
        ollama_models=providers.ollama_models(host),
        lima_instances=tuple(found),
        time_machine_destinations=_time_machine(),
    )
