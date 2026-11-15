"""Call the installed runtime: its bridge operations and its own command-line tools."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from arhugula_kit import proc
from arhugula_kit.errors import Exit, KitError
from arhugula_kit.layout import KIT_ROOT, Home

__all__ = ["Refusal", "ask", "call", "exec_tool", "require_installed", "run_tool"]


@dataclass(frozen=True)
class Refusal:
    """The runtime's typed refusal: its discriminator and its own message."""

    kind: str
    message: str


def require_installed(home: Home) -> None:
    if not home.python.is_file() or not home.harness.is_file():
        raise KitError(
            Exit.PRECONDITION,
            f"no harness environment at {home.env}",
            fix=f"run {home.kit / 'init'}",
        )


def ask(home: Home, operation: str, **arguments: Any) -> Any | Refusal:
    """Run one bridge operation; the runtime's answer or its typed refusal."""
    require_installed(home)
    outcome = proc.run(
        [home.python, "-m", "arhugula_kit.bridge", operation],
        env={"PYTHONPATH": str(KIT_ROOT / "lib")},
        stdin=json.dumps(arguments),
        cwd=home.upstream,
        timeout=300,
    )
    try:
        reply = json.loads(outcome.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise KitError(
            Exit.INTERNAL,
            f"the runtime bridge operation `{operation}` gave no answer "
            f"(exit {outcome.code}):\n{outcome.last_lines(12)}",
        ) from None
    if reply["ok"]:
        return reply["value"]
    return Refusal(reply["kind"], reply["message"])


def call(home: Home, operation: str, **arguments: Any) -> Any:
    """Run one bridge operation and fail with the runtime's own words when it refuses."""
    match ask(home, operation, **arguments):
        case Refusal(kind=kind, message=message):
            raise KitError(Exit.RUNTIME_REFUSED, f"the runtime refused ({kind}): {message}")
        case value:
            return value


def run_tool(
    program: Path, words: Sequence[str | Path], *, cwd: Path, timeout: float | None = 900
) -> proc.Outcome:
    """Run one of the runtime's tools and capture its output."""
    return proc.run([program, *words], cwd=cwd, timeout=timeout)


def exec_tool(program: Path, words: Sequence[str | Path], *, cwd: Path) -> int:
    """Run one of the runtime's tools attached to this terminal and return its exit code.

    The operator answers gates and sees output directly; the kit adds nothing in between.
    """
    return subprocess.call([str(program), *(str(word) for word in words)], cwd=cwd, env=os.environ)
