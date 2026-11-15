"""The trace stack: OpenTelemetry Collector, Tempo and Grafana, in the deployment's VM.

The stack is upstream's own Compose project (`deploy/self-hosted-local`, copied from the
pinned checkout) with the kit's additions merged over it: dashboards, alert rules, a logs
pipeline, and the Tempo setting that TraceQL metrics need. It runs in the Docker engine
of the deployment's Lima VM. Docker Desktop is never used.

[LAW:one-source-of-truth] `<home>/observability` is rendered from the pinned upstream
files and the kit's files on every `up`. Nobody edits the rendered copy.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
import shutil
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from arhugula_kit import deploy, detect, lima, vm
from arhugula_kit.deploy import Deployment
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.layout import KIT_ROOT, STACK_PORTS, Home

__all__ = [
    "GRAFANA_URL",
    "PORTS",
    "TEMPO_URL",
    "StackStatus",
    "collected_logs",
    "down",
    "engine_answer",
    "is_up",
    "render_stack",
    "status",
    "up",
]

PROJECT = "arhugula-observability"
PORTS: Mapping[str, int] = STACK_PORTS
GRAFANA_URL = f"http://127.0.0.1:{STACK_PORTS['Grafana']}"
TEMPO_URL = f"http://127.0.0.1:{STACK_PORTS['Tempo']}"
OTLP_PORT = STACK_PORTS["OTLP gRPC"]
SECRET_IN_VM = "/var/lib/arhugula/grafana-admin-password"
COLLECTED_LOGS_IN_CONTAINER = "/var/lib/arhugula-collector/run-logs.jsonl"
READY_DEADLINE_SECONDS = 300

# The kit replaces upstream's collector config with its own, which repeats upstream's
# traces pipeline. This is the upstream file the kit's copy was written against.
UPSTREAM_COLLECTOR_SHA256 = "0b621dd737918022e83adb060c1af9893a1755dcb35c606755d9fd1f75c3956f"


def engine_answer(deployment: Deployment) -> dict[str, Any]:
    """The deployment's `observability` answer in the shape `vm.engine` reads."""
    return asdict(deployment.spec.observability)


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _sync(wanted: Mapping[Path, bytes], root: Path) -> None:
    """Make `root` hold exactly `wanted` (paths relative to it), changing files in place.

    The directories are never removed and recreated: a running container has them
    mounted, and a recreated directory is a different one that the container never sees.
    """
    root.mkdir(parents=True, exist_ok=True)
    for relative, content in wanted.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_bytes() != content:
            target.write_bytes(content)
    for existing in sorted(root.rglob("*"), reverse=True):
        if existing.is_file() and existing.relative_to(root) not in wanted:
            existing.unlink()


# Each service reads these files once, when it starts. Compose does not restart a
# container because a mounted file's content changed, so `up` does.
SERVICE_FILES: Mapping[str, str] = {
    "tempo": "tempo.yaml",
    "otel-collector": "otel-collector.yaml",
    "grafana": "grafana",
}


def _digest(path: Path) -> str:
    """One hash over a file, or over every file under a directory."""
    files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
    seen = hashlib.sha256()
    for file in files:
        seen.update(str(file.relative_to(path.parent)).encode() + b"\0" + file.read_bytes() + b"\0")
    return seen.hexdigest()


def _service_digests(home: Home) -> dict[str, str]:
    return {service: _digest(home.observability / name) for service, name in SERVICE_FILES.items()}


def _loaded_file(home: Home) -> Path:
    return home.run / "observability-loaded.json"


def _loaded_digests(home: Home) -> dict[str, str]:
    """The configuration each running service was last started with; empty when unknown.

    It is written only after a start succeeded, so a start that failed part-way is not
    mistaken for "the containers already have this configuration".
    """
    try:
        return dict(json.loads(_loaded_file(home).read_text(encoding="utf-8")))
    except FileNotFoundError:
        return {}


def render_stack(home: Home) -> list[str]:
    """Write the Compose project under `<home>/observability`; return any warnings."""
    upstream = home.upstream / "deploy" / "self-hosted-local"
    kit = KIT_ROOT / "observability"
    out = home.observability
    warnings: list[str] = []

    _copy(upstream / "compose.yaml", out / "compose.yaml")
    _copy(kit / "stack" / "compose.kit.yaml", out / "compose.kit.yaml")

    collector = (upstream / "otel-collector.yaml").read_bytes()
    if hashlib.sha256(collector).hexdigest() != UPSTREAM_COLLECTOR_SHA256:
        warnings.append(
            "upstream's otel-collector.yaml differs from the one the kit's collector "
            "config was written against; compare them before relying on the traces pipeline"
        )
    _copy(kit / "stack" / "otel-collector.yaml", out / "otel-collector.yaml")

    tempo = (upstream / "tempo.yaml").read_text(encoding="utf-8")
    clash = [key for key in ("metrics_generator:", "overrides:", "query_frontend:") if f"\n{key}" in f"\n{tempo}"]
    if clash:
        raise KitError(
            Exit.INTERNAL,
            f"upstream's tempo.yaml now declares {', '.join(clash)} itself; the kit's "
            "addendum would declare it twice",
            fix="this is a kit defect at this pin; please file an issue",
        )
    addendum = (kit / "stack" / "tempo.addendum.yaml").read_text(encoding="utf-8")
    (out / "tempo.yaml").write_text(tempo.rstrip("\n") + "\n" + addendum, encoding="utf-8")

    upstream_provisioning = upstream / "grafana" / "provisioning"
    grafana: dict[Path, bytes] = {
        Path("provisioning") / source.relative_to(upstream_provisioning): source.read_bytes()
        for source in sorted(upstream_provisioning.rglob("*"))
        if source.is_file()
    }
    grafana[Path("provisioning/dashboards/arhugula.yaml")] = (
        kit / "stack" / "grafana-dashboards.yaml"
    ).read_bytes()
    for rule in sorted((kit / "alerting").glob("*.yaml")):
        grafana[Path("provisioning/alerting") / rule.name] = rule.read_bytes()
    for dashboard in sorted((kit / "dashboards").glob("*.json")):
        json.loads(dashboard.read_text(encoding="utf-8"))
        grafana[Path("dashboards") / dashboard.name] = dashboard.read_bytes()
    _sync(grafana, out / "grafana")
    return warnings


def _password(home: Home) -> str:
    """The Grafana admin password: generated once, kept in `<home>/secrets`, mode 0600."""
    path = home.grafana_password
    if not path.is_file():
        home.secrets.mkdir(mode=0o700, exist_ok=True)
        home.secrets.chmod(0o700)
        path.touch(mode=0o600)
        path.write_text(secrets.token_urlsafe(24) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path.read_text(encoding="utf-8").strip()


def _place_secret(engine: lima.Engine, password: str) -> None:
    """Put the password where the VM's Docker engine can mount it, in a root-only directory.

    Grafana runs as its own user inside the container and must be able to read the file,
    so the file is 0644; the directory around it is 0700 root, so only the engine reaches it.
    """
    directory = str(Path(SECRET_IN_VM).parent)
    made = engine.instance.shell("sudo", "-n", "install", "-d", "-m", "0700", directory)
    wrote = engine.instance.shell(
        "sudo", "-n", "sh", "-c", f"umask 022 && cat > {SECRET_IN_VM}", stdin=password + "\n"
    )
    if not (made.ok and wrote.ok):
        raise KitError(
            Exit.EXTERNAL_TOOL,
            f"could not place the Grafana password inside {engine.instance.name}:\n"
            f"{(wrote if made.ok else made).last_lines()}",
        )


def _compose(
    engine: lima.Engine, ref: lima.VmRef, home: Home, *words: str, timeout: float | None = 900
) -> Any:
    project = vm.project_dir(ref, home)
    return engine.docker(
        "compose",
        "--project-name", PROJECT,
        "--project-directory", project,
        "-f", f"{project}/compose.yaml",
        "-f", f"{project}/compose.kit.yaml",
        *words,
        env={
            "R420_GRAFANA_ADMIN_PASSWORD_FILE": SECRET_IN_VM,
            "ARHUGULA_LOGS_DIR": vm.logs_dir(ref, home),
        },
        timeout=timeout,
    )


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as reply:
            return 200 <= reply.status < 300
    except (urllib.error.URLError, OSError):
        return False


def _containers(engine: lima.Engine) -> list[tuple[str, str]]:
    """(service, state) for each container of the stack; empty when it is down.

    Asked of Docker by the project's label, so it answers before the project is rendered.
    """
    outcome = engine.docker(
        "ps", "--all", "--filter", f"label=com.docker.compose.project={PROJECT}",
        "--format", '{{.Label "com.docker.compose.service"}}\t{{.State}}', timeout=120,
    )
    if not outcome.ok:
        raise KitError(Exit.EXTERNAL_TOOL, f"`docker ps` failed:\n{outcome.last_lines()}")
    return sorted(tuple(line.split("\t", 1)) for line in outcome.stdout.splitlines() if "\t" in line)


def _ref(deployment: Deployment) -> lima.VmRef | None:
    return vm.ref_of(engine_answer(deployment), deployment.home)


def _wait_ready(out: Callable[[str], None]) -> None:
    """Wait until Grafana, Tempo and the OTLP port answer on loopback, or fail naming which."""
    probes: dict[str, Callable[[], bool]] = {
        f"Grafana ({GRAFANA_URL})": lambda: _http_ok(f"{GRAFANA_URL}/api/health"),
        f"Tempo ({TEMPO_URL})": lambda: _http_ok(f"{TEMPO_URL}/ready"),
        f"OTLP gRPC (127.0.0.1:{OTLP_PORT})": lambda: detect.port_listening(OTLP_PORT),
    }
    deadline = time.monotonic() + READY_DEADLINE_SECONDS
    waiting = list(probes)
    while waiting and time.monotonic() < deadline:
        waiting = [name for name in waiting if not probes[name]()]
        if waiting:
            time.sleep(2)
    if waiting:
        raise KitError(
            Exit.EXTERNAL_TOOL,
            f"the stack started but did not answer within {READY_DEADLINE_SECONDS} s: "
            + ", ".join(waiting),
            fix="arhugula observability status",
        )
    for name in probes:
        out(f"  ready: {name}")


def up(deployment: Deployment, *, out: Callable[[str], None] = print) -> Deployment:
    """Start the VM (creating the kit's VM when it does not exist yet) and the stack."""
    home = deployment.home
    ref = _ref(deployment)
    if ref is None:
        raise KitError(
            Exit.PRECONDITION,
            "this deployment has no virtual machine for the stack to run in",
            fix="arhugula observability vm create",
        )
    out("\nObservability stack:")
    home.logs.mkdir(parents=True, exist_ok=True)
    for warning in render_stack(home):
        out(f"  warning: {warning}")
    out(f"  rendered the Compose project at {home.observability}")
    if ref.kit_owned and lima.find(ref) is None:
        engine = vm.create(home, out=out)
    else:
        engine = vm.engine(engine_answer(deployment), home, start=True)
    out(f"  Docker {engine.server_version}, Compose {engine.compose_version} in {engine.instance.name}")

    project = vm.project_dir(ref, home)
    seen = engine.instance.shell("test", "-f", f"{project}/compose.yaml")
    if not seen.ok:
        raise KitError(
            Exit.PRECONDITION,
            f"{engine.instance.name} cannot see {home.observability} (looked for {project})",
            fix=f"mount that directory read-only in the instance, or use the kit's own VM: "
            "`arhugula observability vm create`",
        )
    was_running = bool(_containers(engine))
    if not was_running:
        busy = [f"{name} {port}" for name, port in PORTS.items() if detect.port_listening(port)]
        if busy:
            raise KitError(
                Exit.PRECONDITION,
                f"loopback port(s) already in use by something else: {', '.join(busy)}",
                fix="find the owner with `lsof -nP -iTCP -sTCP:LISTEN` and stop it",
            )
    _place_secret(engine, _password(home))
    started = _compose(engine, ref, home, "up", "--detach", "--remove-orphans", timeout=1800)
    if not started.ok:
        raise KitError(Exit.EXTERNAL_TOOL, f"`docker compose up` failed:\n{started.last_lines(12)}")
    rendered, loaded = _service_digests(home), _loaded_digests(home)
    changed = [service for service in SERVICE_FILES if was_running and loaded.get(service) != rendered[service]]
    if changed:
        restarted = _compose(engine, ref, home, "restart", *changed, timeout=300)
        if not restarted.ok:
            raise KitError(Exit.EXTERNAL_TOOL, f"could not restart {', '.join(changed)}:\n{restarted.last_lines()}")
        out(f"  restarted {', '.join(changed)} to load changed configuration")
    _wait_ready(out)
    home.run.mkdir(parents=True, exist_ok=True)
    _loaded_file(home).write_text(json.dumps(rendered), encoding="utf-8")
    out(f"  Grafana: {GRAFANA_URL}  (user `admin`; password in {home.grafana_password})")
    if not deployment.spec.observability.enabled:
        deployment = deploy.apply(
            deployment,
            replace(deployment.spec, observability=replace(deployment.spec.observability, enabled=True)),
        )
    return deployment


def down(
    deployment: Deployment,
    *,
    stop_vm: bool,
    delete_data: bool,
    out: Callable[[str], None] = print,
) -> Deployment:
    """Stop the stack and turn the tier off. Traces and Grafana data are kept unless `delete_data`.

    The tier stays off until `up`: a later `upgrade`, `relocate` or re-verify does not
    start a stack the operator took down.
    """
    home = deployment.home
    ref = _ref(deployment)
    instance = lima.find(ref) if ref is not None else None
    if ref is None or instance is None:
        out("the stack is not set up; nothing to stop")
        return deployment
    if instance.running:
        engine = vm.engine(engine_answer(deployment), home, start=False)
        if (home.observability / "compose.yaml").is_file():
            words = ["down", "--remove-orphans"] + (["--volumes"] if delete_data else [])
            stopped = _compose(engine, ref, home, *words)
            if not stopped.ok:
                raise KitError(Exit.EXTERNAL_TOOL, f"`docker compose down` failed:\n{stopped.last_lines(12)}")
        _loaded_file(home).unlink(missing_ok=True)
        out("the stack is down" + ("; its stored traces and Grafana data are deleted" if delete_data else ""))
    else:
        out(f"the VM {instance.name} is already stopped, so the stack is down")
        if delete_data:
            raise KitError(
                Exit.PRECONDITION,
                "the stored data lives inside the stopped VM and was not deleted",
                fix="arhugula observability up, then arhugula observability down --delete-data",
            )
    if stop_vm and instance.running:
        instance.stop()
        out(f"the VM {instance.name} is stopped")
    if deployment.spec.observability.enabled:
        deployment = deploy.apply(
            deployment,
            replace(deployment.spec, observability=replace(deployment.spec.observability, enabled=False)),
        )
        out("the observability tier is off; `arhugula observability up` turns it on again")
    return deployment


def is_up(deployment: Deployment) -> bool:
    """Whether any container of the stack is running."""
    ref = _ref(deployment)
    instance = lima.find(ref) if ref is not None else None
    if ref is None or instance is None or not instance.running:
        return False
    engine = lima.probe_engine(instance)
    if engine is None:
        return False
    return any(state == "running" for _, state in _containers(engine))


@dataclass(frozen=True)
class StackStatus:
    vm: str
    engine: str
    containers: tuple[tuple[str, str], ...]
    ports: tuple[tuple[str, int, bool], ...]
    newest_trace: str  # as Tempo reports it; "" when Tempo does not answer or holds none


def _newest_trace() -> str:
    """The most recently started trace Tempo holds from the last day, in words."""
    now = int(time.time())
    query = f"{TEMPO_URL}/api/search?limit=200&start={now - 86400}&end={now + 60}"
    try:
        with urllib.request.urlopen(query, timeout=10) as reply:
            traces = json.load(reply).get("traces", [])
    except (urllib.error.URLError, OSError, ValueError):
        return ""
    if not traces:
        return ""
    newest = max(traces, key=lambda trace: int(trace["startTimeUnixNano"]))
    started = int(newest["startTimeUnixNano"]) / 1e9
    name = newest.get("rootTraceName", "?")
    return f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(started))}  {name}  {newest['traceID']}"


def status(deployment: Deployment) -> StackStatus:
    home = deployment.home
    ref = _ref(deployment)
    ports = tuple((name, port, detect.port_listening(port)) for name, port in PORTS.items())
    if ref is None:
        return StackStatus("none configured (`arhugula observability vm create`)", "", (), ports, "")
    instance = lima.find(ref)
    if instance is None:
        return StackStatus(f"{ref.name}: not created under {ref.lima_home}", "", (), ports, "")
    described = (
        f"{instance.name}: {instance.status}, {instance.vm_type}, {instance.arch}, "
        f"{instance.cpus} CPU, {instance.memory_bytes // 2**30} GiB, LIMA_HOME={instance.lima_home}"
    )
    if not instance.running:
        return StackStatus(described, "", (), ports, "")
    engine = lima.probe_engine(instance)
    if engine is None:
        return StackStatus(described, "no Docker engine answers", (), ports, "")
    return StackStatus(
        described,
        f"Docker {engine.server_version}, Compose {engine.compose_version or 'missing'}, "
        f"gVisor {'runsc' if engine.has_gvisor else 'missing'}",
        tuple(_containers(engine)),
        ports,
        _newest_trace(),
    )


def collected_logs(deployment: Deployment) -> str:
    """The logs pipeline's output file, read out of the collector's container.

    Returns "" only when the collector runs and has not written the file yet.
    """
    home = deployment.home
    ref = _ref(deployment)
    if ref is None:
        raise KitError(Exit.PRECONDITION, "the stack is not set up", fix="arhugula observability up")
    engine = vm.engine(engine_answer(deployment), home, start=False)
    listed = engine.docker(
        "ps", "--quiet", "--filter", f"label=com.docker.compose.project={PROJECT}",
        "--filter", "label=com.docker.compose.service=otel-collector", timeout=60,
    )
    if not listed.ok:
        raise KitError(Exit.EXTERNAL_TOOL, f"`docker ps` failed:\n{listed.last_lines()}")
    container = listed.stdout.strip()
    if not container:
        raise KitError(Exit.PRECONDITION, "the collector is not running", fix="arhugula observability up")
    # `docker cp` to stdout is a tar stream; the collector image has no shell to `cat` with.
    try:
        copied = subprocess.run(
            ["limactl", "shell", "--workdir", "/", engine.instance.name, *engine.docker_words,
             "cp", f"{container}:{COLLECTED_LOGS_IN_CONTAINER}", "-"],
            env={**os.environ, "LIMA_HOME": str(engine.instance.lima_home)},
            capture_output=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise KitError(Exit.EXTERNAL_TOOL, "reading the collected logs took more than 120 s") from None
    if copied.returncode != 0:
        message = copied.stderr.decode(errors="replace")
        if "Could not find the file" in message or "no such file or directory" in message.lower():
            return ""
        raise KitError(Exit.EXTERNAL_TOOL, f"could not read the collected logs:\n{message[-600:]}")
    with tarfile.open(fileobj=io.BytesIO(copied.stdout)) as archive:
        member = archive.extractfile(archive.getmembers()[0])
        return member.read().decode("utf-8", errors="replace") if member else ""
