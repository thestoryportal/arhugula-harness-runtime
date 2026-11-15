"""Run external commands and report what happened.

[LAW:effects-at-boundaries] Every subprocess the kit starts goes through `run`, which
returns the outcome as a value. Callers decide what an exit status means; nothing here
swallows one.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from arhugula_kit.errors import Exit, KitError

__all__ = ["Outcome", "require", "run", "which"]


@dataclass(frozen=True)
class Outcome:
    argv: tuple[str, ...]
    code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.code == 0

    def last_lines(self, count: int = 6) -> str:
        text = (self.stderr.strip() or self.stdout.strip()).splitlines()
        return "\n".join(text[-count:])


def which(command: str) -> Path | None:
    found = shutil.which(command)
    return Path(found) if found else None


def run(
    argv: Sequence[str | Path],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = 120,
    stdin: str | None = None,
) -> Outcome:
    """Run to completion and capture output. A missing program or a timeout is an outcome too."""
    words = tuple(str(word) for word in argv)
    merged = {**os.environ, **env} if env is not None else None
    try:
        done = subprocess.run(
            words, cwd=cwd, env=merged, timeout=timeout, input=stdin, capture_output=True, text=True
        )
    except FileNotFoundError:
        return Outcome(words, 127, "", f"{words[0]}: command not found")
    except subprocess.TimeoutExpired as expired:
        out = expired.stdout if isinstance(expired.stdout, str) else ""
        return Outcome(words, 124, out, f"{words[0]}: no result after {timeout:.0f} s")
    return Outcome(words, done.returncode, done.stdout, done.stderr)


def require(outcome: Outcome, what: str, *, fix: str | None = None) -> Outcome:
    """The outcome when the command succeeded, else the kit's external-tool failure."""
    if not outcome.ok:
        raise KitError(
            Exit.EXTERNAL_TOOL,
            f"{what} failed (exit {outcome.code}): {' '.join(outcome.argv)}\n{outcome.last_lines()}",
            fix=fix,
        )
    return outcome
