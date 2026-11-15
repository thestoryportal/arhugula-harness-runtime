"""The harness daemon: one long-lived process per target, reachable over a Unix socket."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from arhugula_kit import common, render
from arhugula_kit.deploy import Deployment
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.layout import Home

__all__ = ["log_path", "pid_of", "pidfile", "running", "socket_path", "start", "stop"]


def _label(target: render.Target) -> str:
    return target.name or "default"


def socket_path(home: Home, target: render.Target) -> Path:
    return home.run / f"{_label(target)}.sock"


def pidfile(home: Home, target: render.Target) -> Path:
    """The pidfile the runtime itself writes (`pidfile_path` in the generated config)."""
    return home.run / f"{_label(target)}.pid"


def log_path(home: Home, target: render.Target) -> Path:
    return home.logs / f"daemon-{_label(target)}.log"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def pid_of(home: Home, target: render.Target) -> int | None:
    """The live daemon's pid for a target, or None. A stale pidfile counts as not running."""
    try:
        pid = int(pidfile(home, target).read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None
    return pid if _alive(pid) and socket_path(home, target).exists() else None


def running(home: Home) -> list[int]:
    """The pids of every live daemon of this deployment."""
    found: list[int] = []
    for path in home.run.glob("*.pid") if home.run.is_dir() else ():
        try:
            pid = int(path.read_text(encoding="utf-8").strip())
        except ValueError:
            continue
        if _alive(pid) and path.with_suffix(".sock").exists():
            found.append(pid)
    return found


def start(deployment: Deployment, target: render.Target, *, wait_seconds: float = 60) -> int:
    home = deployment.home
    existing = pid_of(home, target)
    if existing is not None:
        raise KitError(Exit.PRECONDITION, f"the daemon for {target.label} is already running (pid {existing})")
    home.run.mkdir(parents=True, exist_ok=True)
    home.logs.mkdir(parents=True, exist_ok=True)
    socket = socket_path(home, target)
    if socket.exists():
        socket.unlink()
    # Started the same way as a one-shot run: with the project's import path and the
    # skill-activation hook, so a workflow behaves the same through the daemon.
    argv, extra = common.harness_command(
        deployment, target, ["daemon", "--config", target.config_file, "--socket-path", socket]
    )
    with log_path(home, target).open("ab") as log:
        child = subprocess.Popen(
            argv,
            env={**os.environ, **extra},
            cwd=target.repository,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if child.poll() is not None:
            tail = "\n".join(log_path(home, target).read_text(errors="replace").splitlines()[-8:])
            raise KitError(
                Exit.RUNTIME_REFUSED,
                f"the daemon exited at once (code {child.returncode}):\n{tail}",
                fix=f"read {log_path(home, target)}",
            )
        if socket.exists():
            return child.pid
        time.sleep(0.2)
    child.terminate()
    raise KitError(
        Exit.RUNTIME_REFUSED,
        f"the daemon did not open its socket within {wait_seconds:.0f} s",
        fix=f"read {log_path(home, target)}",
    )


def stop(deployment: Deployment, target: render.Target, *, wait_seconds: int = 30) -> bool:
    """Ask the daemon to drain and exit through the runtime's own shutdown tool."""
    home = deployment.home
    if pid_of(home, target) is None:
        return False
    done = subprocess.run(
        [str(home.harness_shutdown), "--pidfile-path", str(pidfile(home, target)), "--wait", str(wait_seconds)],
        cwd=target.repository,
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        raise KitError(
            Exit.RUNTIME_REFUSED,
            f"harness-shutdown exited {done.returncode}: {(done.stderr or done.stdout).strip()}",
        )
    return True
