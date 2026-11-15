"""Small helpers every verb module shares."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path

from arhugula_kit import render
from arhugula_kit.deploy import Deployment
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.verbs import Arg

__all__ = ["PROJECT_ARG", "exec_logged", "resolve_manifest", "say", "table", "target_of"]

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


def exec_logged(
    program: Path,
    words: Sequence[str | Path],
    *,
    cwd: Path,
    log_dir: Path,
    label: str,
    env: dict[str, str] | None = None,
) -> int:
    """Run a runtime tool attached to this terminal, copying its stderr to a log file.

    stdin and stdout stay the terminal's, so a gate can ask and the operator can answer.
    stderr is copied byte for byte as it arrives, so a prompt without a newline still
    appears at once. The log file is what `arhugula logs` and the logs pipeline read.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    log_path = log_dir / f"{label}-{stamp}-{os.getpid()}.log"
    argv = [str(program), *(str(word) for word in words)]
    with log_path.open("wb") as log:
        log.write((" ".join(argv) + "\n").encode())
        child = subprocess.Popen(argv, cwd=cwd, stderr=subprocess.PIPE, env={**os.environ, **(env or {})})
        assert child.stderr is not None
        stream = child.stderr

        def copy() -> None:
            while chunk := os.read(stream.fileno(), 65536):
                sys.stderr.buffer.write(chunk)
                sys.stderr.buffer.flush()
                log.write(chunk)
                log.flush()

        copier = threading.Thread(target=copy, daemon=True)
        copier.start()
        code = child.wait()
        copier.join()
        log.write(f"exit: {code}\n".encode())
    return code
