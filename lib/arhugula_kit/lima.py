"""The Lima virtual machine that provides the deployment's only Docker engine.

Docker Desktop is never started or addressed. Every Docker command the kit runs is
`limactl shell <instance> <docker ...>`, executed inside the VM.

[LAW:single-enforcer] `Engine.docker` is the one place a Docker command line is built, so
"which Docker" has exactly one answer.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from arhugula_kit import proc
from arhugula_kit.errors import Exit, KitError

__all__ = ["Engine", "Instance", "candidate_homes", "instances", "probe_engine"]


@dataclass(frozen=True)
class Instance:
    lima_home: Path
    name: str
    status: str  # Running | Stopped | ...
    vm_type: str
    cpus: int
    memory_bytes: int

    @property
    def running(self) -> bool:
        return self.status == "Running"

    def limactl(self, *words: str, timeout: float | None = 300) -> proc.Outcome:
        return proc.run(
            ["limactl", *words], env={"LIMA_HOME": str(self.lima_home)}, timeout=timeout
        )

    def shell(self, *words: str, timeout: float | None = 300) -> proc.Outcome:
        """Run a command inside the VM."""
        return self.limactl("shell", self.name, *words, timeout=timeout)

    def start(self) -> None:
        proc.require(
            self.limactl("start", self.name, "--tty=false", timeout=900),
            f"starting the Lima instance {self.name}",
            fix=f"LIMA_HOME={self.lima_home} limactl start {self.name}",
        )

    def stop(self) -> None:
        proc.require(self.limactl("stop", self.name, timeout=300), f"stopping {self.name}")

    def refreshed(self) -> Instance:
        for candidate in instances(self.lima_home):
            if candidate.name == self.name:
                return candidate
        raise KitError(
            Exit.PRECONDITION,
            f"the Lima instance {self.name} no longer exists under {self.lima_home}",
        )


def candidate_homes(configured: str | None) -> tuple[Path, ...]:
    """Where Lima instances may live: the configured home, $LIMA_HOME, then Lima's default."""
    raw = [configured, os.environ.get("LIMA_HOME"), str(Path.home() / ".lima")]
    seen: list[Path] = []
    for item in raw:
        if item and Path(item).is_dir() and Path(item) not in seen:
            seen.append(Path(item))
    return tuple(seen)


def instances(lima_home: Path) -> tuple[Instance, ...]:
    """The instances under one Lima home; empty when `limactl` is absent or lists none."""
    outcome = proc.run(
        ["limactl", "list", "--json"], env={"LIMA_HOME": str(lima_home)}, timeout=60
    )
    if not outcome.ok:
        return ()
    found: list[Instance] = []
    for line in outcome.stdout.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        found.append(
            Instance(
                lima_home=lima_home,
                name=row["name"],
                status=row.get("status", "Unknown"),
                vm_type=row.get("vmType", ""),
                cpus=int(row.get("cpus", 0)),
                memory_bytes=int(row.get("memory", 0)),
            )
        )
    return tuple(found)


@dataclass(frozen=True)
class Engine:
    """A Docker engine that answered inside a running Lima instance."""

    instance: Instance
    docker_words: tuple[str, ...]  # ("docker",) for a rootless engine, ("sudo", "docker") otherwise
    server_version: str
    runtimes: tuple[str, ...]

    @property
    def has_gvisor(self) -> bool:
        return "runsc" in self.runtimes

    def docker(self, *words: str, timeout: float | None = 600) -> proc.Outcome:
        return self.instance.shell(*self.docker_words, *words, timeout=timeout)

    def compose(self, project_dir: str, *words: str, timeout: float | None = 900) -> proc.Outcome:
        return self.docker("compose", "--project-directory", project_dir, *words, timeout=timeout)


def probe_engine(instance: Instance) -> Engine | None:
    """The Docker engine inside a running instance, or None when none answers.

    The user's rootless engine is asked first, then the system engine through sudo; the
    one that answers is the one every later command uses.
    """
    for docker_words in (("docker",), ("sudo", "-n", "docker")):
        outcome = instance.shell(*docker_words, "info", "--format", "{{json .}}", timeout=90)
        if not outcome.ok:
            continue
        try:
            info = json.loads(outcome.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            continue
        return Engine(
            instance=instance,
            docker_words=docker_words,
            server_version=str(info.get("ServerVersion", "")),
            runtimes=tuple(sorted((info.get("Runtimes") or {}).keys())),
        )
    return None
