"""The kit's failure type and its exit codes.

Exit codes are a contract (documented in docs/operate.md): 0 success; 1 a harness workflow
did not complete; 2 usage; 3 a precondition the operator can fix (preflight, missing
answer, unknown name); 4 the installed runtime refused something; 5 an external tool
(uv, git, limactl, docker, a provider CLI) failed; 6 the kit's own invariant broke.
"""

from __future__ import annotations

from enum import IntEnum


class Exit(IntEnum):
    OK = 0
    WORKFLOW = 1
    USAGE = 2
    PRECONDITION = 3
    RUNTIME_REFUSED = 4
    EXTERNAL_TOOL = 5
    INTERNAL = 6


class KitError(Exception):
    """A failure the operator sees as one message plus, where there is one, the fix."""

    def __init__(self, exit_code: Exit, message: str, *, fix: str | None = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.message = message
        self.fix = fix
