"""Small helpers every verb module shares."""

from __future__ import annotations

import fcntl
import os
import pty
import subprocess
import sys
import tarfile
import termios
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from arhugula_kit import render
from arhugula_kit.deploy import Deployment
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.layout import KIT_ROOT
from arhugula_kit.verbs import Arg

__all__ = [
    "PROJECT_ARG", "exec_logged", "harness_command", "python_paths",
    "resolve_manifest", "say", "table", "target_of", "write_private_archive",
]

PROJECT_ARG = Arg(
    ("--project",),
    "the attached project to act on (default: the current project; `default` for the "
    "deployment default)",
    {"metavar": "NAME"},
)


def say(text: str = "") -> None:
    print(text, flush=True)


def table(rows: Sequence[Sequence[str]], *, header: Sequence[str]) -> None:
    """Print rows in aligned columns under a header."""
    widths = [max(len(str(row[i])) for row in (header, *rows)) for i in range(len(header))]
    for row in (header, *rows):
        say("  ".join(str(cell).ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip())


def target_of(deployment: Deployment, project: str | None) -> render.Target:
    """The target a `--project` value names; `default` is the deployment default."""
    return deployment.target("" if project == "default" else project)


def resolve_manifest(deployment: Deployment, target: render.Target, text: str) -> Path:
    """Find a manifest by the name the operator typed.

    Looked for, in order: the path as typed; the target's repository; its `workflows/`
    directory; the upstream checkout; upstream's `examples/`.
    """
    given = Path(text).expanduser()
    home = deployment.home
    candidates = [
        given if given.is_absolute() else Path.cwd() / given,
        target.repository / given,
        target.repository / "workflows" / given,
        home.upstream / given,
        home.upstream / "examples" / given,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    looked = "\n  ".join(str(c) for c in dict.fromkeys(candidates))
    raise KitError(
        Exit.PRECONDITION,
        f"no workflow manifest named {text!r}. Looked in:\n  {looked}",
        fix="arhugula workflow list",
    )


def write_private_archive(archive: Path, add: Callable[[tarfile.TarFile], None]) -> None:
    """Write a gzip tar archive that is its owner's alone from its first byte.

    An archive of state or memory holds private data. A write that fails leaves no
    partial archive, and an existing archive is never overwritten.
    """
    if archive.exists():
        raise KitError(Exit.PRECONDITION, f"{archive} already exists")
    partial = archive.with_name(archive.name + ".partial")
    handle = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(handle, "wb") as raw, tarfile.open(fileobj=raw, mode="w:gz") as tar:
            add(tar)
        partial.replace(archive)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise


def python_paths(deployment: Deployment, target: render.Target) -> list[str]:
    """Directories the runtime must import from: the project's validators/ and skills/
    directories, then any the operator added."""
    conventional = [target.repository / "validators", target.repository / "skills"]
    return [str(p) for p in conventional if p.is_dir()] + list(deployment.spec.python_paths)


def harness_command(
    deployment: Deployment, target: render.Target, words: Sequence[str | Path]
) -> tuple[list[str], dict[str, str]]:
    """The runtime's CLI for a target, as argv and extra environment.

    [LAW:single-enforcer] A one-shot run, a resume and the daemon are all started through
    here, so each gets the project's import path and, when one is set, the
    skill-activation hook. A workflow behaves the same whichever way it is started.
    """
    paths = python_paths(deployment, target)
    hook = deployment.spec.skill_hook
    if hook:
        argv = [str(deployment.home.python), "-m", "arhugula_kit.hookrun", hook, *map(str, words)]
        paths = [str(KIT_ROOT / "lib"), *paths]
    else:
        argv = [str(deployment.home.harness), *map(str, words)]
    return argv, ({"PYTHONPATH": os.pathsep.join(paths)} if paths else {})


def exec_logged(
    argv: Sequence[str],
    *,
    cwd: Path,
    log_dir: Path,
    label: str,
    env: dict[str, str] | None = None,
) -> int:
    """Run a runtime tool attached to this terminal, copying its stderr to a log file.

    stdin and stdout stay the terminal's. stderr is where the runtime prints its progress
    and asks at an approval gate, and the runtime asks only when stderr is a terminal. So
    when this process has a terminal, the child's stderr is a pseudo-terminal that is
    copied, byte for byte as it arrives, to the real one and to the log; without a
    terminal it is a pipe, and the runtime answers a gate as it does for any unattended
    run. The log file is what `arhugula logs` and the logs pipeline read.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    log_path = log_dir / f"{label}-{stamp}-{os.getpid()}.log"
    # A run log can quote prompts and tool output: it is its owner's alone.
    os.close(os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    argv = list(argv)
    attended = sys.stderr.isatty()
    if attended:
        reader, child_stderr = pty.openpty()
        fcntl.ioctl(child_stderr, termios.TIOCSWINSZ, fcntl.ioctl(2, termios.TIOCGWINSZ, b"\0" * 8))
    else:
        reader, child_stderr = os.pipe()
    with log_path.open("wb") as log:
        log.write((" ".join(argv) + "\n").encode())
        try:
            child = subprocess.Popen(argv, cwd=cwd, stderr=child_stderr, env={**os.environ, **(env or {})})
        except BaseException:
            os.close(reader)
            raise
        finally:
            os.close(child_stderr)

        def copy() -> None:
            while True:
                try:
                    chunk = os.read(reader, 65536)
                except OSError:  # a pseudo-terminal reports its closed far end as an error
                    break
                if not chunk:
                    break
                sys.stderr.buffer.write(chunk)
                sys.stderr.buffer.flush()
                log.write(chunk.replace(b"\r\n", b"\n"))
                log.flush()

        copier = threading.Thread(target=copy, daemon=True)
        copier.start()
        while True:
            try:
                code = child.wait()
                break
            except KeyboardInterrupt:
                # Ctrl-C reaches the child too (same terminal). It is the runtime's to
                # handle: it drains and exits, and this process waits for that.
                continue
        copier.join()
        os.close(reader)
        log.write(f"exit: {code}\n".encode())
    # A child ended by a signal reports as the shell does: 128 plus the signal number.
    return code if code >= 0 else 128 - code
