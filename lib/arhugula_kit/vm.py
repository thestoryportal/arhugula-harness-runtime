"""The deployment's virtual machine: which Lima instance it is, and its Docker engine.

The default for every operator is the kit's own VM: created under `<home>/lima`, built
for this machine's CPU, with Docker Engine, Compose and gVisor installed by the profile.
An instance the operator already had is the alternative. Docker Desktop is never used.

[LAW:single-enforcer] `engine` is the one path from a deployment to a Docker engine. The
trace stack and isolation tier 3 both go through it, so "is the VM usable" is decided once.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from arhugula_kit import lima
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.layout import KIT_ROOT, KIT_VM_NAME, Home
from arhugula_kit.spec import Engine

__all__ = [
    "LOGS_IN_KIT_VM",
    "PROJECT_IN_KIT_VM",
    "create",
    "emulation_refusal",
    "engine",
    "kit_ref",
    "logs_dir",
    "preconditions",
    "project_dir",
    "ref_of",
]

PROJECT_IN_KIT_VM = "/arhugula/observability"
LOGS_IN_KIT_VM = "/arhugula/logs"


def kit_ref(home: Home) -> lima.VmRef:
    return lima.VmRef(home.lima, KIT_VM_NAME, kit_owned=True)


def ref_of(answer: Mapping[str, Any], home: Home) -> lima.VmRef | None:
    """The VM an `observability` answer names; None when the deployment has no engine."""
    match Engine(answer["engine"]):
        case Engine.NONE:
            return None
        case Engine.KIT:
            return kit_ref(home)
        case Engine.EXISTING:
            return lima.VmRef(Path(answer["lima_home"]), answer["instance"], kit_owned=False)


def _mounts(home: Home) -> tuple[lima.Mount, ...]:
    return (
        lima.Mount(home.observability, PROJECT_IN_KIT_VM),
        lima.Mount(home.logs, LOGS_IN_KIT_VM),
    )


def project_dir(ref: lima.VmRef, home: Home) -> str:
    """Where the Compose project is inside the VM. An existing instance sees the host path."""
    return PROJECT_IN_KIT_VM if ref.kit_owned else str(home.observability)


def logs_dir(ref: lima.VmRef, home: Home) -> str:
    return LOGS_IN_KIT_VM if ref.kit_owned else str(home.logs)


def emulation_refusal(instance: lima.Instance) -> KitError:
    """Why an instance built for another CPU architecture is not used, and both ways out."""
    return KitError(
        Exit.PRECONDITION,
        f"the Lima instance {instance.name} holds a {instance.arch} guest and this machine "
        f"is {lima.host_arch()}. Lima can only run it by emulating the other CPU, which "
        "needs an extra package and is many times slower, so the kit does not use it",
        fix="use the kit's own VM, which is built for this machine: `arhugula observability "
        "vm create`. To run the other instance anyway, install Lima's extra guest agents "
        "(`brew install lima-additional-guestagents`) and start it yourself",
    )


def preconditions(home: Home) -> None:
    """What must hold before the kit's VM can be created; refuses with the fix."""
    found = lima.version()
    if found is None:
        raise KitError(Exit.PRECONDITION, "Lima is not installed (`limactl` is not on PATH)",
                       fix="brew install lima")
    if found < lima.MINIMUM_VERSION:
        wanted = ".".join(str(part) for part in lima.MINIMUM_VERSION)
        raise KitError(
            Exit.PRECONDITION,
            f"Lima {'.'.join(str(p) for p in found)} is too old for the kit's VM profile "
            f"(it needs {wanted})",
            fix="brew upgrade lima",
        )
    budget = lima.socket_path_budget(home.lima, KIT_VM_NAME)
    if budget < 0:
        raise KitError(
            Exit.PRECONDITION,
            f"the deployment home's path is {-budget} character(s) too long for the VM: "
            f"macOS limits a socket path to 104 bytes and Lima keeps its sockets under "
            f"{home.lima / KIT_VM_NAME}",
            fix="move the deployment to a shorter path with `arhugula relocate <new-home>`",
        )


def _profile(home: Home) -> Path:
    """Render the kit's VM profile for this home and return the file Lima reads."""
    text = (KIT_ROOT / "observability" / "lima" / "arhugula.yaml.tmpl").read_text(encoding="utf-8")
    for token, value in home.substitutions().items():
        text = text.replace(token, value)
    target = home.observability / "lima" / "arhugula.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def create(home: Home, *, out: Callable[[str], None]) -> lima.Engine:
    """Create the kit's VM and prove its Docker engine, Compose and gVisor answer."""
    ref = kit_ref(home)
    if lima.find(ref) is not None:
        raise KitError(Exit.PRECONDITION, f"the VM {ref.name} already exists under {ref.lima_home}",
                       fix="arhugula observability vm status")
    preconditions(home)
    for mount in _mounts(home):
        mount.location.mkdir(parents=True, exist_ok=True)
    profile = _profile(home)
    out(f"  creating the VM {ref.name} under {ref.lima_home} from {profile}")
    out("  this downloads an Ubuntu image and installs Docker and gVisor: allow 5 to 10 minutes")
    lima.create(ref, profile, log=home.logs / "vm-create.log")
    return _proven(ref, home, start=False)


def _proven(ref: lima.VmRef, home: Home, *, start: bool) -> lima.Engine:
    instance = lima.find(ref)
    if instance is None:
        raise KitError(
            Exit.PRECONDITION,
            f"no Lima instance {ref.name!r} under {ref.lima_home}",
            fix="arhugula observability vm create"
            if ref.kit_owned
            else "check that the volume holding that Lima home is mounted, or choose the "
            "kit's own VM with `arhugula observability vm create`",
        )
    if not instance.native:
        raise emulation_refusal(instance)
    if not instance.running:
        if not start:
            raise KitError(
                Exit.PRECONDITION, f"the Lima instance {instance.name} is stopped",
                fix="arhugula observability up",
            )
        # A relocated home leaves the kit's VM pointing at the old directories.
        if ref.kit_owned and instance.mounts != _mounts(home):
            instance.remount(_mounts(home))
        instance.start()
        instance = instance.refreshed()
    found = lima.probe_engine(instance)
    if found is None:
        raise KitError(
            Exit.EXTERNAL_TOOL,
            f"no Docker engine answers inside {instance.name}",
            fix=f"LIMA_HOME={instance.lima_home} limactl shell {instance.name} docker info",
        )
    if not found.compose_version:
        raise KitError(
            Exit.EXTERNAL_TOOL,
            f"the Docker engine inside {instance.name} has no Compose plugin",
            fix="install the Docker Compose plugin inside the VM",
        )
    return found


def engine(answer: Mapping[str, Any], home: Home, *, start: bool) -> lima.Engine:
    """The deployment's Docker engine, starting its VM when asked. Refuses with the fix."""
    ref = ref_of(answer, home)
    if ref is None:
        raise KitError(
            Exit.PRECONDITION,
            "this deployment has no virtual machine, so it has no Docker engine",
            fix="arhugula observability vm create",
        )
    return _proven(ref, home, start=start)
