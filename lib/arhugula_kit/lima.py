"""The Lima virtual machine that provides the deployment's only Docker engine.

Docker Desktop is never started or addressed. Every Docker command the kit runs is
`limactl shell <instance> <docker ...>`, executed inside the VM.

[LAW:single-enforcer] `Engine.docker` is the one place a Docker command line is built, so
"which Docker" has exactly one answer.
"""

from __future__ import annotations

import json
import os
import platform
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from arhugula_kit import proc
from arhugula_kit.errors import Exit, KitError

__all__ = [
    "MINIMUM_VERSION",
    "Engine",
    "Instance",
    "Mount",
    "VmRef",
    "candidate_homes",
    "create",
    "find",
    "host_arch",
    "instances",
    "probe_engine",
    "socket_path_budget",
    "version",
]

MINIMUM_VERSION = (2, 0, 0)
"""The oldest Lima the kit's VM profile loads on (`minimumLimaVersion` in the profile)."""

# macOS limits a UNIX socket path to 104 bytes, and Lima keeps its sockets in the
# instance directory; this is the longest socket name it creates there.
_UNIX_PATH_MAX = 104
_LONGEST_SOCKET = "ssh.sock.1234567890123456"


def host_arch() -> str:
    """This machine's CPU architecture in Lima's spelling (`aarch64` or `x86_64`)."""
    machine = platform.machine()
    return {"arm64": "aarch64", "amd64": "x86_64"}.get(machine, machine)


def version() -> tuple[int, ...] | None:
    """The installed Lima version, or None when `limactl` is absent or silent."""
    outcome = proc.run(["limactl", "--version"], timeout=30)
    words = outcome.stdout.split()
    if not outcome.ok or not words:
        return None
    try:
        return tuple(int(part) for part in words[-1].split("-")[0].split("."))
    except ValueError:
        return None


def socket_path_budget(lima_home: Path, name: str) -> int:
    """How many bytes are left for Lima's longest socket path; negative means too long."""
    return _UNIX_PATH_MAX - 1 - len(str(lima_home / name / _LONGEST_SOCKET).encode())


@dataclass(frozen=True)
class Mount:
    """A host directory shown inside the VM, read-only."""

    location: Path  # on the host
    mount_point: str  # inside the VM; fixed, so files in the VM never carry a host path


@dataclass(frozen=True)
class VmRef:
    """Which Lima instance a deployment uses, before anyone has looked for it."""

    lima_home: Path
    name: str
    kit_owned: bool  # the kit created it and may delete it

    @property
    def start_command(self) -> str:
        return f"LIMA_HOME={self.lima_home} limactl start {self.name}"


@dataclass(frozen=True)
class Instance:
    lima_home: Path
    name: str
    status: str  # Running | Stopped | ...
    vm_type: str
    arch: str  # aarch64 | x86_64, as Lima reports it
    cpus: int
    memory_bytes: int
    mounts: tuple[Mount, ...] = ()

    @property
    def running(self) -> bool:
        return self.status == "Running"

    @property
    def native(self) -> bool:
        """Whether the guest runs on this machine's own CPU architecture (no emulation)."""
        return self.arch == host_arch()

    def limactl(self, *words: str, timeout: float | None = 300) -> proc.Outcome:
        return proc.run(
            ["limactl", *words], env={"LIMA_HOME": str(self.lima_home)}, timeout=timeout
        )

    def shell(self, *words: str, timeout: float | None = 300, stdin: str | None = None) -> proc.Outcome:
        """Run a command inside the VM. The working directory is the VM user's home."""
        return proc.run(
            ["limactl", "shell", "--workdir", "/", self.name, *words],
            env={"LIMA_HOME": str(self.lima_home)},
            timeout=timeout,
            stdin=stdin,
        )

    def start(self) -> None:
        proc.require(
            self.limactl("start", self.name, "--tty=false", timeout=900),
            f"starting the Lima instance {self.name}",
            fix=f"LIMA_HOME={self.lima_home} limactl start {self.name}",
        )

    def stop(self) -> None:
        proc.require(self.limactl("stop", self.name, timeout=300), f"stopping {self.name}")

    def delete(self) -> None:
        proc.require(
            self.limactl("delete", "--force", self.name, timeout=300), f"deleting {self.name}"
        )

    def remount(self, mounts: tuple[Mount, ...]) -> None:
        """Point a stopped instance's mounts at new host directories (after `relocate`)."""
        wanted = json.dumps(
            [
                {"location": str(m.location), "mountPoint": m.mount_point, "writable": False}
                for m in mounts
            ]
        )
        proc.require(
            self.limactl("edit", "--tty=false", "--set", f".mounts = {wanted}", self.name),
            f"updating the mounts of {self.name}",
        )

    def refreshed(self) -> Instance:
        found = find(VmRef(self.lima_home, self.name, kit_owned=False))
        if found is None:
            raise KitError(
                Exit.PRECONDITION,
                f"the Lima instance {self.name} no longer exists under {self.lima_home}",
            )
        return found


def candidate_homes(configured: str | None) -> tuple[Path, ...]:
    """Where Lima instances may live: the configured home, $LIMA_HOME, then Lima's default."""
    raw = [configured, os.environ.get("LIMA_HOME"), str(Path.home() / ".lima")]
    seen: list[Path] = []
    for item in raw:
        if item and Path(item).is_dir() and Path(item) not in seen:
            seen.append(Path(item))
    return tuple(seen)


def instances(lima_home: Path) -> tuple[Instance, ...]:
    """The instances under one Lima home. Refuses when Lima cannot be asked.

    "Lima did not answer" is never reported as "no instance": a caller that is about to
    move or delete a VM's disk must not take a failed listing for an empty one.
    """
    outcome = proc.require(
        proc.run(["limactl", "list", "--json"], env={"LIMA_HOME": str(lima_home)}, timeout=60),
        f"listing the Lima instances under {lima_home}",
        fix="check that Lima is installed and on PATH: limactl --version",
    )
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
                arch=row.get("arch", ""),
                cpus=int(row.get("cpus", 0)),
                memory_bytes=int(row.get("memory", 0)),
                mounts=tuple(
                    Mount(Path(m["location"]), m.get("mountPoint", m["location"]))
                    for m in (row.get("config") or {}).get("mounts") or ()
                ),
            )
        )
    return tuple(found)


def find(ref: VmRef) -> Instance | None:
    """The instance a reference names, or None when it does not exist.

    A Lima home that does not exist holds no instance, and that needs no Lima to know.
    """
    if not ref.lima_home.is_dir() or not any(ref.lima_home.iterdir()):
        return None
    return next((i for i in instances(ref.lima_home) if i.name == ref.name), None)


def create(ref: VmRef, profile: Path, *, log: Path) -> Instance:
    """Create and start an instance from a profile file. Takes several minutes the first time."""
    ref.lima_home.mkdir(parents=True, exist_ok=True)
    outcome = proc.run(
        ["limactl", "start", f"--name={ref.name}", "--tty=false", str(profile)],
        env={"LIMA_HOME": str(ref.lima_home)},
        timeout=2700,
    )
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(outcome.stdout + outcome.stderr, encoding="utf-8")
    proc.require(
        outcome,
        f"creating the Lima instance {ref.name}",
        fix=f"read {log}, then run `arhugula observability vm delete` and create it again",
    )
    created = find(ref)
    if created is None:
        raise KitError(Exit.EXTERNAL_TOOL, f"limactl reported success but lists no {ref.name}")
    return created


@dataclass(frozen=True)
class Engine:
    """A Docker engine that answered inside a running Lima instance."""

    instance: Instance
    docker_words: tuple[str, ...]  # ("docker",) for a rootless engine, ("sudo", "docker") otherwise
    server_version: str
    runtimes: tuple[str, ...]
    compose_version: str  # "" when the Compose plugin is missing

    @property
    def has_gvisor(self) -> bool:
        return "runsc" in self.runtimes

    def docker(
        self,
        *words: str,
        env: Mapping[str, str] | None = None,
        timeout: float | None = 600,
        stdin: str | None = None,
    ) -> proc.Outcome:
        """Run `docker <words>` inside the VM, with `env` set for that one command."""
        pairs = [f"{key}={value}" for key, value in (env or {}).items()]
        prefix = (*self.docker_words[:-1], "env", *pairs) if pairs else self.docker_words[:-1]
        return self.instance.shell(*prefix, "docker", *words, timeout=timeout, stdin=stdin)


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
        compose = instance.shell(*docker_words, "compose", "version", "--short", timeout=60)
        return Engine(
            instance=instance,
            docker_words=docker_words,
            server_version=str(info.get("ServerVersion", "")),
            runtimes=tuple(sorted((info.get("Runtimes") or {}).keys())),
            compose_version=compose.stdout.strip() if compose.ok else "",
        )
    return None
